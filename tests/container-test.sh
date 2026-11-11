#!/bin/sh
# End-to-end test meant to run as root inside a throwaway container or VM:
#
#   docker run --rm --cap-add LINUX_IMMUTABLE -v "$PWD":/src:ro debian:stable-slim sh /src/tests/container-test.sh
#
# It installs python3 if missing, installs selfctl, runs a real 20 second
# block against example.com and checks that it is enforced and then undone.
set -eu

if ! command -v python3 >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -qq && apt-get install -y -qq python3 >/dev/null
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y -q python3 >/dev/null
    elif command -v apk >/dev/null 2>&1; then
        apk add --no-cache -q python3
    elif command -v pacman >/dev/null 2>&1; then
        pacman -Sy --noconfirm python >/dev/null
    elif command -v zypper >/dev/null 2>&1; then
        zypper -q install -y python3 >/dev/null
    fi
fi

fail() { echo "FAIL: $*" >&2; exit 1; }
blocked() { python3 -c 'import socket,sys
a={i[4][0] for i in socket.getaddrinfo(sys.argv[1], 443)}
sys.exit(0 if a <= {"0.0.0.0", "::"} else 1)' "$1" 2>/dev/null; }

. /etc/os-release
echo "== $PRETTY_NAME, $(python3 --version)"

cp -r /src /tmp/src
cp /etc/hosts /tmp/hosts.before
sh /tmp/src/install.sh
python3 -B -m unittest discover -s /tmp/src/tests 2>&1 | tail -n 3

selfctl doctor || true
selfctl start 20s example.com --yes
grep -q "^0.0.0.0 www.example.com$" /etc/hosts || fail "hosts entry missing"
blocked example.com || fail "example.com still resolves"

# tamper: put the original file back; the daemon must undo that
chattr -i /etc/hosts 2>/dev/null || true   # no-op in containers: the lock is skipped there
cat /tmp/hosts.before > /etc/hosts
sleep 4
grep -q "^0.0.0.0 example.com$" /etc/hosts || fail "daemon did not repair hosts"

selfctl add example.org
grep -q "^0.0.0.0 example.org$" /etc/hosts || fail "add did not work"
selfctl stop 2>/dev/null && fail "stop must not exist"

sleep 22
python3 -c 'import sys; sys.exit(open("/etc/hosts").read() != open("/tmp/hosts.before").read())' \
    || fail "hosts not restored after the block"
[ ! -e /var/lib/linux-selfcontrol/state.json ] || fail "state not removed"
selfctl status
echo "PASS: $PRETTY_NAME"

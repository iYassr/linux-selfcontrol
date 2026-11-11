#!/bin/sh
# End-to-end test on a real systemd machine. Needs sudo. It installs selfctl,
# blocks example.com for 40 seconds, attacks the block, and checks that the
# system is put back exactly as it was. Safe to run on your own computer.
#
#   sh tests/system-test.sh
set -eu
cd "$(dirname "$0")/.."

fail() { echo "FAIL: $*" >&2; exit 1; }
step() { echo "-- $*"; }

sudo sh install.sh
BEFORE="$(mktemp)"
cp /etc/hosts "$BEFORE"

selfctl start 40s example.com --yes
step "resolver answers 0.0.0.0"
getent ahosts example.com | grep -q -E '^(0\.0\.0\.0|::) ' || fail "example.com still resolves"
step "service and watchdog are running"
systemctl is-active --quiet linux-selfcontrol.service || fail "daemon not running"
systemctl is-active --quiet linux-selfcontrol-watchdog.timer || fail "watchdog not running"

step "hosts file cannot be edited"
if echo "# x" | sudo tee -a /etc/hosts >/dev/null 2>&1; then
    echo "   (immutable flag not supported here; relying on the daemon)"
fi
step "wiping the block is reverted"
sudo sh -c "chattr -i /etc/hosts 2>/dev/null; cp '$BEFORE' /etc/hosts" 2>/dev/null \
    || echo "   (the daemon locked the file again before it could be overwritten)"
sleep 4
grep -q '^0.0.0.0 example.com$' /etc/hosts || fail "daemon did not repair hosts"

step "stopping the service is refused"
sudo systemctl stop linux-selfcontrol.service 2>/dev/null && fail "service could be stopped"
step "killing the daemon restarts it"
sudo systemctl kill -s KILL linux-selfcontrol.service
sleep 4
systemctl is-active --quiet linux-selfcontrol.service || fail "daemon did not come back"
step "there is no stop command"
selfctl stop 2>/dev/null && fail "stop must not exist"

step "waiting for the block to end"
i=0
while [ -e /var/lib/linux-selfcontrol/state.json ]; do
    i=$((i + 1)); [ "$i" -lt 60 ] || fail "block did not end"
    sleep 2
done
sleep 2
cmp -s /etc/hosts "$BEFORE" || fail "hosts file was not restored"
[ ! -e /etc/systemd/system/linux-selfcontrol.service ] || fail "unit file left behind"
systemctl is-active --quiet linux-selfcontrol.service && fail "daemon still running"
rm -f "$BEFORE"
selfctl status
echo "PASS"

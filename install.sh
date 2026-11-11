#!/bin/sh
# Linux SelfControl installer.
#
#   sudo ./install.sh                 install from this checkout
#   sudo ./install.sh --uninstall     remove (refused while a block is active)
#   curl -fsSL https://raw.githubusercontent.com/iYassr/linux-selfcontrol/main/install.sh | sudo sh
#
# Environment: PREFIX (default /usr/local), DESTDIR (for packagers),
#              SELFCTL_REF (branch or tag to download, default main)
set -eu

REPO="iYassr/linux-selfcontrol"
PREFIX="${PREFIX:-/usr/local}"
DESTDIR="${DESTDIR:-}"
REF="${SELFCTL_REF:-main}"

BIN="$DESTDIR$PREFIX/bin/selfctl"
SHARE="$DESTDIR$PREFIX/share/linux-selfcontrol"
DESKTOP="$DESTDIR$PREFIX/share/applications/linux-selfcontrol.desktop"
ICON="$DESTDIR$PREFIX/share/icons/hicolor/scalable/apps/linux-selfcontrol.svg"
STATE="/var/lib/linux-selfcontrol/state.json"

say() { printf '%s\n' "$*"; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }

if [ -z "$DESTDIR" ] && [ "$(id -u)" -ne 0 ]; then
    fail "run this as root:  sudo sh install.sh"
fi

if [ "${1:-}" = "--uninstall" ]; then
    if [ -z "$DESTDIR" ] && [ -e "$STATE" ]; then
        fail "a block is active. Uninstall after it has ended ('selfctl status')."
    fi
    rm -f "$BIN" "$DESKTOP" "$ICON"
    rm -rf "$SHARE"
    say "Linux SelfControl removed. Your custom lists in ~/.config/selfctl were left alone."
    exit 0
fi

command -v python3 >/dev/null 2>&1 || fail "python3 is required (install it with your package manager)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' \
    || fail "Python 3.7 or newer is required"

# Use the checkout next to this script, or download one.
SRC=""
case "$0" in
    */*) [ -f "$(dirname "$0")/selfctl" ] && SRC="$(cd "$(dirname "$0")" && pwd)" ;;
    *) [ -f "./selfctl" ] && [ -d "./lists" ] && SRC="$(pwd)" ;;
esac
TMP=""
if [ -z "$SRC" ]; then
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    URL="https://github.com/$REPO/archive/$REF.tar.gz"
    say "Downloading $URL"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$URL" -o "$TMP/src.tar.gz"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$TMP/src.tar.gz" "$URL"
    else
        fail "curl or wget is required to download the source"
    fi
    tar -xzf "$TMP/src.tar.gz" -C "$TMP"
    SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    [ -f "$SRC/selfctl" ] || fail "download did not contain selfctl"
fi

install -d -m 0755 "$(dirname "$BIN")" "$SHARE/lists" "$(dirname "$DESKTOP")" "$(dirname "$ICON")"
install -m 0755 "$SRC/selfctl" "$BIN"
for list in "$SRC"/lists/*.txt; do
    install -m 0644 "$list" "$SHARE/lists/"
done
install -m 0644 "$SRC/assets/linux-selfcontrol.desktop" "$DESKTOP"
install -m 0644 "$SRC/assets/icon.svg" "$ICON"

if [ -z "$DESTDIR" ]; then
    say "Installed selfctl $("$BIN" version | cut -d' ' -f2) to $BIN"
    say ""
    say "  selfctl            guided menu"
    say "  selfctl doctor     check this system"
    case ":$PATH:" in
        *":$PREFIX/bin:"*) ;;
        *) say ""; say "note: $PREFIX/bin is not in your PATH" ;;
    esac
fi

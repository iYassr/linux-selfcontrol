#!/usr/bin/env python3
"""Regenerate the README screenshots from selfctl's real output.

    python3 tools/screenshots.py

Each image is selfctl's actual terminal output (same functions, same text)
drawn as an SVG, so the pictures cannot drift from the program.
"""
import contextlib
import html
import importlib.machinery
import importlib.util
import io
import os
import re
import shutil
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "assets")

sandbox = tempfile.mkdtemp(prefix="selfctl-shots-")
os.makedirs(os.path.join(sandbox, "etc"))
open(os.path.join(sandbox, "etc/hosts"), "w").write("127.0.0.1 localhost\n")
os.environ.update(SELFCTL_ROOT=sandbox, SELFCTL_CONFIG=os.path.join(sandbox, "cfg"),
                  FORCE_COLOR="1", SELFCTL_CLOCK_SYNCED="0")
os.environ.pop("NO_COLOR", None)
sys.dont_write_bytecode = True
loader = importlib.machinery.SourceFileLoader("selfctl", os.path.join(REPO, "selfctl"))
spec = importlib.util.spec_from_loader("selfctl", loader)
s = importlib.util.module_from_spec(spec)
loader.exec_module(s)

FG, BG, BAR = "#d5dbe6", "#0e131d", "#161d2b"
COLORS = {"31": "#ff6b81", "32": "#5eead4", "33": "#f7c873", "36": "#67c7ff"}
DIM = "#6f7a90"
CW, LH, PAD, TOP = 8.43, 20, 18, 40
SGR = re.compile(r"\x1b\[([0-9;]*)m")


def segments(line):
    """Yield (column, text, colour, bold) runs for one ANSI line."""
    col, colour, is_bold, pos = 0, FG, False, 0
    for m in list(SGR.finditer(line)) + [None]:
        text = line[pos:m.start()] if m else line[pos:]
        if text:
            yield col, text, colour, is_bold
            col += len(text)
        if m is None:
            break
        pos = m.end()
        for code in (m.group(1) or "0").split(";"):
            if code in ("0", ""):
                colour, is_bold = FG, False
            elif code == "1":
                is_bold = True
            elif code == "2":
                colour = DIM
            elif code in COLORS:
                colour = COLORS[code]


def svg(name, title, lines):
    width = max(64, max(len(SGR.sub("", l)) for l in lines) + 2)
    w = int(width * CW + 2 * PAD)
    h = int(TOP + len(lines) * LH + PAD)
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
        'role="img" aria-label="%s">' % (w, h, w, h, html.escape(title)),
        '<rect width="%d" height="%d" rx="10" fill="%s"/>' % (w, h, BG),
        '<path d="M0 10a10 10 0 0 1 10-10h%d a10 10 0 0 1 10 10v20H0z" fill="%s"/>' % (w - 20, BAR),
        '<circle cx="18" cy="15" r="5.5" fill="#ff5f57"/><circle cx="36" cy="15" r="5.5" fill="#febc2e"/>'
        '<circle cx="54" cy="15" r="5.5" fill="#28c840"/>',
        '<text x="%d" y="19.5" text-anchor="middle" fill="%s" font-family="system-ui,-apple-system,'
        'Segoe UI,sans-serif" font-size="12">%s</text>' % (w // 2, DIM, html.escape(title)),
        '<g font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,\'DejaVu Sans Mono\',\'Liberation Mono\','
        'monospace" font-size="14" xml:space="preserve">',
    ]
    for row, line in enumerate(lines):
        y = TOP + row * LH + 14
        for col, text, colour, is_bold in segments(line):
            if not text.strip():
                continue
            for i, ch in enumerate(text):
                if ch == "✔":            # drawn, so it never depends on a fallback font
                    x = PAD + (col + i) * CW
                    out.append('<path d="M%.1f %d l3 3.5 l5.5 -8.5" fill="none" stroke="%s" stroke-width="2" '
                               'stroke-linecap="round" stroke-linejoin="round"/>' % (x + 0.5, y - 5, colour))
            text = text.replace("✔", " ")
            xs = " ".join("%.1f" % (PAD + (col + i) * CW) for i in range(len(text.rstrip(" "))))
            out.append('<text x="%s" y="%d" fill="%s"%s>%s</text>' % (
                xs, y, colour, ' font-weight="700"' if is_bold else "", html.escape(text.rstrip(" "))))
    out.append("</g></svg>")
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("wrote", os.path.relpath(path, REPO))


def captured(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue().rstrip("\n").split("\n")


def prompt(cmd):
    return s.c("32", "❯ ") + s.bold(cmd)


lists = s.available_lists()
items = [(n, lists[n]["title"], "%d sites" % len(lists[n]["domains"])) for n in sorted(lists)]
items.append(("+custom", "Other sites…", "type your own"))
svg("menu.svg", "selfctl", s.checklist_frame(
    "What do you want to block?", items, 7, {"social", "video"},
    "↑/↓ move   space select   a all   enter continue   q quit"))

svg("duration.svg", "selfctl", s.choice_frame(
    "For how long?", s.DURATION_CHOICES, 3, "↑/↓ move   enter select   q quit"))

# A real block inside the sandbox, 47 minutes into a 2 hour run.
names, extra, hostnames = s.resolve_targets(["social", "video"])
state = s.apply_request({"action": "start", "seconds": 7200, "domains": hostnames, "labels": names})
guards = [("hosts file", True), ("locked", True), ("daemon", True), ("watchdog", True)]
start = ([prompt("selfctl start 2h social video")]
         + s.confirm_lines(names, extra, hostnames, 7200)
         + ["  Start the block? [y/N] y"]
         + s.status_lines(state, guards))
svg("start.svg", "selfctl start", start)

state["last_boottime"] -= 47 * 60
state["end_wall"] -= 47 * 60
svg("status.svg", "selfctl status", [prompt("selfctl status")] + s.status_lines(state, guards))

svg("lists.svg", "selfctl lists", [prompt("selfctl lists")] + captured(s.cmd_lists, []))

# Transcript of the tamper test run on a live Omarchy system (see README).
D = s.dim
svg("tamper.svg", "trying to cheat", [
    prompt("echo '# oops' | sudo tee -a /etc/hosts"),
    "tee: /etc/hosts: Operation not permitted",
    "",
    prompt("sudo chattr -i /etc/hosts && sudo cp hosts.backup /etc/hosts"),
    prompt("sleep 3; selfctl check example.com"),
    "",
    "  " + s.red("● blocked ") + " example.com" + D("      # the daemon put it all back"),
    "",
    prompt("sudo systemctl stop linux-selfcontrol"),
    "Failed to stop linux-selfcontrol.service: Operation refused",
    "",
    prompt("sudo systemctl kill -s KILL linux-selfcontrol; sleep 2"),
    prompt("systemctl is-active linux-selfcontrol"),
    "active" + D("                       # restarted after one second"),
    "",
    prompt("sudo rm /var/lib/linux-selfcontrol/state.json"),
    "rm: cannot remove '/var/lib/linux-selfcontrol/state.json': Operation not permitted",
    "",
    prompt("selfctl stop"),
    s.red("error: ") + "there is no way to stop a block early. That is the point.",
])

shutil.rmtree(sandbox, ignore_errors=True)

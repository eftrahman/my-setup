#!/usr/bin/env python3
"""Now-playing module and controls for Waybar (MPRIS through playerctl).

  MediaBar.py watch            stream Waybar JSON for the title
  MediaBar.py button prev|next print the button glyph, or nothing when idle
  MediaBar.py toggle|next|prev|forward|back   control the player being shown

Browsers with Plasma integration expose one video as two players; the helper
shows it once and always controls the player that is displayed.
"""

import html
import json
import os
import signal
import subprocess
import sys
import time

STATE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "mediabar-player")
SIGNAL = signal.SIGRTMIN + 9  # refreshes the prev/next buttons ("signal": 9)
MAX_TITLE = 22
FIELDS = ("playerInstance", "status", "title", "artist", "album")
FORMAT = "\t".join("{{%s}}" % field for field in FIELDS)
BROWSERS = ("chromium", "chrome", "firefox", "brave", "vivaldi", "microsoft-edge")


def playerctl(*args):
    try:
        return subprocess.run(["playerctl", *args], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def players():
    found = []
    for line in playerctl("-a", "metadata", "--format", FORMAT).splitlines():
        values = line.split("\t")
        if len(values) < len(FIELDS):
            continue
        player = dict(zip(FIELDS, values))
        if player["title"].strip() and player["status"] in ("Playing", "Paused"):
            found.append(player)
    integrated = {p["title"] for p in found if p["playerInstance"].startswith("plasma-browser-integration")}
    return [p for p in found
            if not (p["playerInstance"].startswith(BROWSERS) and p["title"] in integrated)]


def current():
    """The playing player; otherwise the one shown last; otherwise any paused one."""
    found = players()
    try:
        with open(STATE, encoding="utf-8") as handle:
            last = handle.read().strip()
    except OSError:
        last = ""
    if not found:
        return None
    chosen = min(found, key=lambda p: (p["status"] != "Playing", p["playerInstance"] != last))
    if chosen["playerInstance"] != last:
        try:
            with open(STATE, "w", encoding="utf-8") as handle:
                handle.write(chosen["playerInstance"])
        except OSError:
            pass
    return chosen


def render(player):
    if not player:
        return {"text": "", "tooltip": "", "class": "stopped"}
    playing = player["status"] == "Playing"
    title = " ".join(player["title"].split())
    short = title if len(title) <= MAX_TITLE else title[:MAX_TITLE - 1].rstrip() + "…"
    details = [title, player["artist"], player["album"], player["playerInstance"].split(".")[0]]
    tip = "\n".join(html.escape(d) for d in details if d.strip())
    return {
        "text": f"{'󰏤' if playing else '󰐊'}  {html.escape(short)}",
        "tooltip": f"{tip}\n\nClick: {'pause' if playing else 'play'}  •  Scroll: seek 5 s",
        "class": "playing" if playing else "paused",
    }


def watch():
    shown = None
    while True:
        try:
            follow = subprocess.Popen(["playerctl", "-a", "-F", "metadata", "--format", FORMAT],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except OSError:
            return 0
        for _line in follow.stdout:
            time.sleep(0.1)  # metadata arrives in bursts when a track changes
            output = render(current())
            if output == shown:
                continue
            visibility = shown is None or bool(shown["text"]) != bool(output["text"])
            shown = output
            print(json.dumps(output), flush=True)
            if visibility:
                subprocess.run(["pkill", f"-{int(SIGNAL)}", "-x", "waybar"], check=False)
        follow.wait()
        time.sleep(2)


def control(action):
    player = current()
    if player:
        playerctl("-p", player["playerInstance"], *{
            "toggle": ["play-pause"], "next": ["next"], "prev": ["previous"],
            "forward": ["position", "5+"], "back": ["position", "5-"]}[action])


def main():
    args = sys.argv[1:]
    if args == ["watch"]:
        return watch()
    if args[:1] == ["button"] and args[1:] in (["prev"], ["next"]):
        print({"prev": "󰒮", "next": "󰒭"}[args[1]] if current() else "")
        return 0
    if len(args) == 1 and args[0] in ("toggle", "next", "prev", "forward", "back"):
        control(args[0])
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Now-playing module and controls for Waybar (MPRIS through playerctl).

  MediaBar.py watch            stream Waybar JSON for the title and progress
  MediaBar.py visualizer       stream animated bars (cava) while something plays
  MediaBar.py button prev|next print the button glyph, or nothing when idle
  MediaBar.py toggle|next|prev|forward|back   control the player being shown

Browsers with Plasma integration expose one video as two players; the helper
shows it once and always controls the player that is displayed.
"""

import ctypes
import html
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time

STATE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "mediabar-player")
SIGNAL = signal.SIGRTMIN + 9  # refreshes the prev/next buttons ("signal": 9)
MAX_TITLE = 22
FIELDS = ("playerInstance", "status", "title", "artist", "album", "position", "mpris:length")
FORMAT = "\t".join("{{%s}}" % field for field in FIELDS)
FOLLOW = "\t".join("{{%s}}" % field for field in FIELDS if field != "position")
PROGRESS_STEPS = 20  # matches #custom-media.p0 … .p20 in TechConsole.css
BARS, FPS = 12, 20
GLYPHS = "▁▂▃▄▅▆▇█"
GRADIENT = ((0x5E, 0xE7, 0xF7), (0xB9, 0x91, 0xFF))  # cyan -> violet
CAVA_CONFIG = f"""[general]
framerate = {FPS}
bars = {BARS}
sleep_timer = 3

[input]
method = pulse
source = {os.environ.get("MEDIABAR_SOURCE", "auto")}

[output]
method = raw
channels = mono
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = {len(GLYPHS) - 1}

[smoothing]
noise_reduction = 70
"""
BROWSERS = ("chromium", "chrome", "firefox", "brave", "vivaldi", "microsoft-edge")


LIBC = ctypes.CDLL(None)


def die_with_parent():
    LIBC.prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG: no orphans when the bar goes away


def emit(text):
    try:
        print(text, flush=True)
    except OSError:  # Waybar closed the pipe
        os._exit(0)


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


def number(text):
    try:
        return max(0, int(float(text)))
    except ValueError:
        return 0


def clock(microseconds):
    seconds = microseconds // 1_000_000
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


def render(player):
    if not player:
        return {"text": "", "tooltip": "", "class": "stopped"}
    playing = player["status"] == "Playing"
    title = " ".join(player["title"].split())
    short = title if len(title) <= MAX_TITLE else title[:MAX_TITLE - 1].rstrip() + "…"
    details = [title, player["artist"], player["album"], player["playerInstance"].split(".")[0]]
    tip = "\n".join(html.escape(d) for d in details if d.strip())
    position, length = number(player["position"]), number(player["mpris:length"])
    classes = ["playing" if playing else "paused"]
    if 0 < length < 86_400_000_000:  # live streams report none, or an absurd length
        position = min(position, length)
        tip += f"\n{clock(position)} / {clock(length)}"
        classes.append(f"p{round(position / length * PROGRESS_STEPS)}")
    return {
        "text": f"{'󰏤' if playing else '󰐊'}  {html.escape(short)}",
        "tooltip": f"{tip}\n\nClick: {'pause' if playing else 'play'}  •  Scroll: seek 5 s",
        "class": classes,
    }


def follow(events):
    """Put an event on the queue whenever any player changes."""
    while True:
        try:
            proc = subprocess.Popen(["playerctl", "-a", "-F", "metadata", "--format", FOLLOW],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, preexec_fn=die_with_parent)
        except OSError:
            return
        for _line in proc.stdout:
            events.put(True)
        proc.wait()
        time.sleep(2)


def changes(idle_timeout):
    """Yield the current player on every change, and every 2 s while it plays."""
    events = queue.Queue()
    threading.Thread(target=follow, args=(events,), daemon=True).start()
    player = current()
    while True:
        yield player
        playing = player and player["status"] == "Playing"
        try:
            events.get(timeout=2 if playing and idle_timeout else None)
            time.sleep(0.1)  # metadata arrives in bursts when a track changes
            while not events.empty():
                events.get_nowait()
        except queue.Empty:
            pass
        player = current()


def watch():
    shown = None
    for player in changes(idle_timeout=True):
        output = render(player)
        if output == shown:
            continue
        visibility = shown is None or bool(shown["text"]) != bool(output["text"])
        shown = output
        emit(json.dumps(output))
        if visibility:
            subprocess.run(["pkill", f"-{int(SIGNAL)}", "-x", "waybar"], check=False)


def bar_color(index):
    ratio = index / (BARS - 1)
    return "#" + "".join(f"{round(a + (b - a) * ratio):02x}" for a, b in zip(*GRADIENT))


def visualizer():
    config = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), f"mediabar-cava-{os.getppid()}.conf")
    colors = [bar_color(i) for i in range(BARS)]
    cava = None

    def pump(proc):
        last = None
        for line in proc.stdout:
            if line == last or cava is not proc:
                continue
            last = line
            levels = [min(number(v), len(GLYPHS) - 1) for v in line.strip().split(";") if v][:BARS]
            emit("".join(f"<span foreground='{c}'>{GLYPHS[v]}</span>" for c, v in zip(colors, levels)))

    for player in changes(idle_timeout=False):
        playing = bool(player) and player["status"] == "Playing"
        if cava and cava.poll() is not None:
            cava = None
        if playing and not cava:
            try:
                with open(config, "w", encoding="utf-8") as handle:
                    handle.write(CAVA_CONFIG)
                cava = subprocess.Popen(["cava", "-p", config], stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, preexec_fn=die_with_parent)
            except OSError:
                return
            threading.Thread(target=pump, args=(cava,), daemon=True).start()
        elif not playing:
            if cava:
                proc, cava = cava, None
                proc.terminate()
                proc.wait()
            emit("")  # hides the module


def control(action):
    player = current()
    if player:
        playerctl("-p", player["playerInstance"], *{
            "toggle": ["play-pause"], "next": ["next"], "prev": ["previous"],
            "forward": ["position", "5+"], "back": ["position", "5-"]}[action])


def main():
    args = sys.argv[1:]
    if args in (["watch"], ["visualizer"]):
        die_with_parent()
    if args == ["watch"]:
        return watch()
    if args == ["visualizer"]:
        return visualizer()
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

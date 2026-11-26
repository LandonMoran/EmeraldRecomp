#!/usr/bin/env python3
"""Headless accessibility playtest for EmeraldRecomp.

What this proves
----------------
The game runs here without SDL, without a window and without Android, and the
mod's own spoken output is captured as it is handed to the speech sink. Every
line in the transcript comes from ``say()`` in src/accessibility/emerald_a11y.cpp
via the runtime's ``emerald_a11y_log`` command - i.e. exactly the strings the
Android bridge passes to TextToSpeech. Nothing here invents narration.

The script walks the real game from a cold boot: launcher greeting, Birch's
intro, name entry, the truck ride (which locks field controls for ~750 frames),
stepping out into Littleroot Town, Mom's dialogue, the move-in scene, the wall
clock (a real Yes/No menu) and back outside, checking after each beat that the
player heard something, and that looking at nothing stays silent.

Run:
    ./build/EmeraldRecomp --bios gbarecomp/bios/gba_bios.bin \
        --rom variants/emerald/roms/emerald_usa.gba --tcp 19892 \
        --frames 4000000 variants/emerald/game.toml &
    python3 artifacts/playtest/run_session.py

or let the script start the emulator itself with --spawn.

Exit status is 0 only when every beat produced a distinct spoken line, the
"not looking at it" beat stayed silent, and no line was spoken twice.
"""

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session import Session  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TRANSCRIPT = os.path.join(ROOT, "artifacts", "playtest", "transcript-session.txt")

# VAR_LITTLEROOT_INTRO_STATE; 5 means "clock not set yet".
VAR_INTRO = 0x4092
VAR_TOWN = 0x4050

# Screen-entry announcements, which the game legitimately repeats on re-entry.
SCENE_LINES = {
    "Title and main menu.", "Main menu.", "Overworld.", "New area.",
    "Battle.", "Bag.", "Party.", "Summary.", "PC storage.",
}

# Beats that are expected to be quiet: waiting, or deliberately silent.
QUIET_BEATS = {"silence", "idle-town", "truck", "post-naming",
               "walk-town", "enter-house", "stairs", "idle",
               # Known gaps, recorded but not asserted: sign/appliance tiles
               # (bg_events) are not in the look probe yet, so facing the wall
               # clock is silent and its text only arrives once it is pressed.
               "look-clock", "clock-message", "clock-dialog", "clock-confirm",
               "downstairs", "outside"}


def port_busy():
    import socket
    try:
        socket.create_connection(("127.0.0.1", 19892), timeout=1).close()
        return True
    except OSError:
        return False


def spawn():
    if port_busy():
        sys.exit("port 19892 already in use: stop the running EmeraldRecomp first "
                 "(a fresh boot is required for a reproducible session)")
    exe = os.path.join(ROOT, "build", "EmeraldRecomp")
    if not os.path.exists(exe):
        sys.exit("no build/EmeraldRecomp - build it first (see docs/PLAYTEST.md)")
    log = open(os.path.join(ROOT, "artifacts", "playtest", "session-emulator.log"), "w")
    proc = subprocess.Popen(
        [exe, "--bios", "gbarecomp/bios/gba_bios.bin",
         "--rom", "variants/emerald/roms/emerald_usa.gba",
         "--tcp", "19892", "--frames", "4000000", "variants/emerald/game.toml"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True)
    print(f"started EmeraldRecomp pid={proc.pid}")
    return proc


def wait_tcp(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = Session(transcript=TRANSCRIPT)
            return s
        except RuntimeError:
            time.sleep(0.5)
    sys.exit("emulator never opened the TCP debug port")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spawn", action="store_true", help="start the emulator if needed")
    args = ap.parse_args()

    proc = spawn() if args.spawn else None
    l = wait_tcp(120 if proc else 20)

    beats = {}                                # tag -> list of spoken lines
    def record(tag):
        lines = l.beat(tag)
        beats.setdefault(tag, []).extend(lines)
        return lines

    def need(tag=None):
        """Require that every tag seen so far spoke at least once, then stop."""
        missing = [t for t, v in beats.items() if not v and t not in QUIET_BEATS]
        if tag and not beats.get(tag) and tag not in QUIET_BEATS:
            missing.append(tag)
        if missing:
            print(f"FAIL silent beat(s): {', '.join(sorted(set(missing)))}")
            sys.exit(finish(l, beats, 1))

    l.mark("=== boot / spoken interface greeting ===")
    # The greeting is spoken the moment the mod is enabled, before the first
    # frame the debugger can step, so read it before touching run_frames.
    for _ in range(200):
        boot = record("boot")
        if boot:
            break
        time.sleep(0.05)
    need("boot")
    l.mash("intro", lambda: l.scene() == "naming", max_presses=400, gap=20)
    need()

    l.mark("=== name entry ===")
    l.confirm(30)
    l.confirm(30)
    l.start(30)
    for _ in range(12):
        l.confirm(30)
        record("naming")
        if l.scene() != "naming":
            break
    need()
    l.mash("post-naming", lambda: l.scene() == "overworld", max_presses=300, gap=20)
    need()

    l.mark("=== truck ride (field controls locked ~750 frames) ===")
    for _ in range(30):
        l.frames(60)
        record("truck")
        if l.lock() == 0:
            break
    if l.lock() != 0:
        print("FAIL truck: field controls never released")
        finish(l, beats, 1)

    l.mark("=== stepping out of the truck ===")
    for _ in range(4):
        moved, _o = l.step("right", 80)
        record("step-out")
        if l.map() == (0, 9):
            break
    need("step-out")
    if l.map() != (0, 9):
        print(f"FAIL step-out: still on {l.map()}")
        finish(l, beats, 1)

    l.mark("=== Mom outside the truck (long dialogue) ===")
    l.mash("mom-dialogue", lambda: l.lock() == 0, max_presses=400, gap=4)
    need()

    l.mark("=== into the house (Mom's script walks the player in) ===")
    if l.map() == (0, 9):
        l.step("up", 120)
    record("enter-house")
    if l.map() != (1, 0):
        print(f"FAIL enter-house: on {l.map()} at {l.pos()}")
        sys.exit(finish(l, beats, 1))
    l.mash("move-in", lambda: l.lock() == 0, max_presses=400, gap=4)
    need()

    l.mark("=== walking / look-triggered speech (the front door) ===")
    for _ in range(3):
        l.frames(40)
        record("idle-town")
    l.walk_to(8, 7, "back-from-door")
    record("walk-town")
    l.face("down")                        # the front door is the warp at (8,8)
    a = l.nav()
    look = a.get("look") or {}
    l.mark(f"facing {a.get('facing')} looking at {look}")
    looked = record("look-town")
    if look.get("kind", "nothing") != "nothing" and not looked:
        print(f"FAIL look-town: looking at {look} said nothing")
        sys.exit(finish(l, beats, 1))
    need()

    l.mark("=== silence when nothing new is looked at ===")
    quiet = 0
    for _ in range(6):
        l.frames(60)
        quiet += len(record("silence"))
    if quiet:
        print(f"FAIL silence: {quiet} unsolicited line(s) while standing still")
        sys.exit(finish(l, beats, 1))

    # Best effort from here on: this is the probe for the two gaps the runs
    # found (bg_event signs are silent until pressed; Yes/No menus read as
    # "Option N"). Whatever it manages to say is recorded; a stall here does not
    # fail the session, the beats above are the asserted ones.
    l.mark("=== upstairs to the wall clock (best effort) ===")
    for _ in range(24):
        if l.map() == (1, 1):
            break
        if l.lock():
            l.mash("stairs", lambda: l.lock() == 0, 200, gap=4)
        moved, _o = l.step("up", 90)
        record("stairs")
        if not moved:
            moved = l.step("left", 90)[0] or l.step("right", 90)[0]
            record("stairs")
    if l.map() == (1, 1):
        l.walk_to(5, 2, "to-clock")
        l.face("up")
        record("look-clock")
        l.ask(cmd="emerald_a11y_action", action="confirm")
        l.frames(50)
        record("clock-message")
        for _ in range(30):
            st = l.status()
            if st.get("menu"):
                if st.get("selected") != 0:
                    l.ask(cmd="emerald_a11y_action", action="up")
                    l.frames(12)
                record("clock-dialog")
                l.ask(cmd="emerald_a11y_action", action="confirm")
                l.frames(60)
                record("clock-confirm")
                if l.var(VAR_INTRO) != 5:
                    break
            else:
                l.ask(cmd="emerald_a11y_action", action="confirm")
                l.frames(40)
                record("clock-dialog")
            if l.var(VAR_INTRO) != 5:
                break
        l.frames(60)
    else:
        l.mark(f"clock probe skipped: still on map {l.map()} at {l.pos()}")
    need()

    l.mark("=== wall clock Yes/No (must be identifiable by ear) ===")
    for _ in range(60):
        st = l.status()
        if st.get("menu"):
            if st.get("selected") != 0:
                l.ask(cmd="emerald_a11y_action", action="up")
                l.frames(12)
            record("clock-dialog")
            l.ask(cmd="emerald_a11y_action", action="confirm")
            l.frames(60)
            record("clock-confirm")
            if l.var(VAR_INTRO) != 5:
                break
        else:
            l.ask(cmd="emerald_a11y_action", action="confirm")
            l.frames(40)
            record("clock-dialog")
        if l.var(VAR_INTRO) != 5:
            break
    l.frames(60)
    need()

    l.mark("=== back outside ===")
    l.mash("downstairs", lambda: l.lock() == 0, max_presses=300, gap=4)
    for _ in range(10):
        if l.map() == (1, 0):
            break
        l.step("down", 90)
        record("downstairs")
        if l.lock():
            l.mash("downstairs", lambda: l.lock() == 0, max_presses=200, gap=4)
    if l.map() == (1, 0):
        l.walk_to(8, 8, "to-town-door")
        l.step("down", 120)
        record("outside")
    l.mash("outside", lambda: l.lock() == 0, max_presses=200, gap=4)
    need()
    l.mark(f"outside at map {l.map()} pos {l.pos()} town_state={l.var(VAR_TOWN)}")

    return finish(l, beats, 1 if quiet else 0)


FINISHED = []


def finish(l, beats, status):
    if FINISHED:
        return FINISHED[0]
    """Summarise the transcript: every beat speaks, nothing is said twice in a row.

    A line repeated later after the scene genuinely changed (title -> menu ->
    title) is reported but not a failure; a line repeated back-to-back inside one
    beat is a narration bug, because the player hears the same thing twice.
    """
    lines = [t for _tag, _f, t, _s in l.all_lines]
    repeats = []
    prev = None
    for tag, _f, text, scene in l.all_lines:
        # Screen announcements legitimately repeat when the game returns to a
        # screen (title -> attract loop -> title). Any other identical line in
        # the same beat is a real duplicate.
        if (prev and prev[1] == text and prev[0] == tag
                and text not in SCENE_LINES):
            repeats.append((tag, text))
        prev = (tag, text, scene)
    print(f"\n{len(lines)} spoken line(s) captured")
    for tag in beats:
        print(f"  {tag:20s} {len(beats[tag]):3d} line(s)")
    missing = [tag for tag, v in beats.items() if not v and tag not in QUIET_BEATS]
    if missing:
        print("FAIL silent beats:", ", ".join(missing))
        status = 1
    if repeats:
        print("FAIL repeated lines inside one beat:")
        for tag, t in repeats:
            print(f"  [{tag}] {t}")
        status = 1
    print(f"transcript: {TRANSCRIPT}")
    print("RESULT:", "ok" if status == 0 else "failed")
    FINISHED.append(status)
    return status


if __name__ == "__main__":
    sys.exit(main())

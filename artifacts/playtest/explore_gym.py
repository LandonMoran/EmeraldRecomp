"""Step on every Mauville gym floor switch, guided only by trying steps.

The gym is a toggle maze: each switch flips which energy beams block which
tiles, so no static map can say what is open. A player with only the spoken
output does what this script does — tries a step, notices when it does not
happen, tries another way, and retries earlier ground after a switch flips the
beams.

Every move is checked against the player's own position, and the two entrance
tiles are never stepped on, so an exploration cannot walk back out of the gym.

    python3 artifacts/playtest/explore_gym.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pad import Pad  # noqa: E402

REPORTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
SWITCHES = {(0, 15): "Switch 1", (4, 12): "Switch 2", (3, 9): "Switch 3", (8, 9): "Switch 4"}
EXIT_TILES = {(4, 19), (5, 19), (4, 20), (5, 20)}
ORDER = ["up", "right", "down", "left"]
DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
OPPOSITE = {"right": "left", "left": "right", "up": "down", "down": "up"}
STEP_LIMIT = 500


def pos(p):
    return tuple(p.ask(cmd="emerald_dev_state").get("pos") or ())


def flag(p):
    """Barrier parity, as far as the spoken layer exposes it: each press flips."""
    return (p.ask(cmd="emerald_dev_state").get("puzzle") or {}).get("changes", 0) & 1


def settle(p):
    for _ in range(8):
        state = p.ask(cmd="emerald_dev_state")
        if not state.get("controls_locked") and not state.get("message_box"):
            return
        p.frames(30)


def try_step(p, direction):
    before = pos(p)
    p.step(direction)
    p.frames(6)
    settle(p)
    p.flush_speech(direction)   # keep a transcript of what the mod announced
    after = pos(p)
    return after if after != before else None


def main():
    p = Pad(os.path.join(REPORTS, "mauville-explore.txt"))
    log = []

    def note(text):
        print(text, flush=True)
        log.append(text)

    start = pos(p)
    hits = {}
    steps = 0
    note(f"start {start} barriers {flag(p)}")

    stack = [start]
    tried = set()
    while stack and steps < STEP_LIMIT:
        cur = pos(p)
        if stack[-1] != cur:            # never trust the stack over the game
            stack = [cur]
        key = flag(p)
        options = [d for d in ORDER if (cur, key, d) not in tried]
        if not options:
            stack.pop()
            if not stack:
                note(f"explored everything reachable, {steps} steps")
                break
            target = stack[-1]
            back = next((d for d, (dx, dy) in DELTA.items()
                         if (cur[0] + dx, cur[1] + dy) == target), None)
            if back is None:
                continue
            nxt = try_step(p, back)
            steps += 1
            if nxt is None:
                note(f"back {cur} -> {target} blocked, exploring from here")
                stack = [cur]        # the beams moved; re-explore from this pocket
            continue

        direction = options[0]
        tried.add((cur, key, direction))
        ahead = (cur[0] + DELTA[direction][0], cur[1] + DELTA[direction][1])
        if ahead in EXIT_TILES:
            note(f"{cur} {direction} is the way out, skipped")
            continue
        nxt = try_step(p, direction)
        steps += 1
        if nxt is None:
            note(f"{cur} {direction} blocked")
            if cur in SWITCHES and SWITCHES[cur] not in hits:
                hits[SWITCHES[cur]] = cur
            continue
        if cur in SWITCHES and SWITCHES[cur] not in hits:
            hits[SWITCHES[cur]] = cur
            note(f"stepped on {SWITCHES[cur]} at {cur}")
        pressed = False
        if nxt in SWITCHES and SWITCHES[nxt] not in hits:
            hits[SWITCHES[nxt]] = nxt
            note(f"stepped on {SWITCHES[nxt]} at {nxt}")
            pressed = True
        if pressed:
            # A press flips the beams, which can seal the tile behind us. Step
            # straight back the way we came while it is still open.
            back = OPPOSITE[direction]
            if try_step(p, back) == cur:
                stack = [cur]
                steps += 1
            else:
                note(f"could not step back from {nxt}")
                stack.append(nxt)
            if len(hits) == len(SWITCHES):
                note(f"all four switches pressed after {steps} steps")
                break
            continue
        stack.append(nxt)

    for name, tile in SWITCHES.items():
        note(f"{name} {tile}: {'pressed' if name in hits else 'NOT reached'}")
    note(f"{steps} steps, ended at {pos(p)}")

    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, "mauville-explore.md"), "w", encoding="utf-8") as fh:
        fh.write("# Mauville gym exploration\n\n")
        for line in log:
            fh.write(f"- {line}\n")
        fh.write("\n## What the mod said\n\n")
        for line in p.lines:
            fh.write(f"    {line}\n")


if __name__ == "__main__":
    main()

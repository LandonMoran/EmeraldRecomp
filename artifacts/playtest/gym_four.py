"""Press all four Mauville Gym plates in the one order the simulation allows.

`gym_sim.py` proves the maze is a two-layout alternation and that the only
four-press order reaching switch 4 is 1 -> 2 -> 3 -> 4: pressing switch 1 opens
the y=15 passage, switch 2 (at 4,12) flips the layout so the climb to the top
half opens, switch 3 (3,9) flips it again so the y=9 corridor east opens, and
switch 4 at (8,9) is the fourth press - which lands the maze back on the even
layout.

Leaving the gym makes MauvilleCity_OnTransition clear
FLAG_MAUVILLE_GYM_BARRIERS_STATE and zero VAR_MAUVILLE_GYM_STATE, so the route
starts by stepping out and back in: trainers stay beaten, the puzzle resets.

    python3 artifacts/playtest/gym_four.py --checkpoint mauville-three-plates
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from checkpoints import Checkpoints, variable_ids  # noqa: E402
from pad import Pad  # noqa: E402

REPORTS = os.path.join(HERE, "reports")
GYM = (10, 0)
ROUTE = [("up", 4), ("left", 4), ("right", 4), ("up", 6), ("left", 1), ("right", 5)]


class Shim:
    """Give Checkpoints the Pad's own socket - the server serves one client."""

    def __init__(self, pad):
        self.p = pad

    def ask(self, **kw):
        return self.p.ask(**kw)


def settle(p, log):
    for i in range(40):
        st = p.ask(cmd="emerald_dev_state")
        scene = p.status().get("scene")
        if (not st.get("message_box") and not st.get("controls_locked")
                and scene in ("overworld", "menu")):
            break
        p.confirm(40)
        p.flush_speech("settle%d" % i)
    log.append("settle done, scene %s" % p.status().get("scene"))


def fight_if_needed(p, tag, log):
    """Press A through trainer dialogue, the battle itself and the aftermath.

    A sight line first locks control for the intro lines (scene still
    ``overworld``), so waiting for ``scene == battle`` alone walks into a locked
    field and every step after it is refused.
    """
    presses = 0
    while presses < 300:
        st = p.ask(cmd="emerald_dev_state")
        scene = p.status().get("scene")
        if (scene == "overworld" and not st.get("message_box")
                and not st.get("controls_locked")):
            break
        p.confirm(40)
        p.flush_speech("%s-b%d" % (tag, presses))
        presses += 1
    if presses:
        log.append("[%s] A x%d to clear dialogue/battle (scene %s)"
                   % (tag, presses, p.status().get("scene")))


def move(p, d, tag, log):
    moved, o = p.step(d)
    p.flush_speech(tag)
    if not moved:
        moved, o = p.step(d)
        p.flush_speech(tag + "b")
    st = p.status()
    msg = st.get("message") or st.get("status") or ""
    log.append("%-14s %s -> (%d,%d) %s %s"
               % (tag, d, o["x"] - 7, o["y"] - 7,
                  "moved" if moved else "BLOCKED", msg))
    fight_if_needed(p, tag, log)
    return moved, o


def map_id(p):
    return tuple(p.map())


def tile(p):
    """Real map tile: the object coords carry MAP_OFFSET (7) padding."""
    o = p.obj()
    return (o["x"] - 7, o["y"] - 7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default="mauville-three-plates")
    ap.add_argument("--report", default="mauville-four-plates")
    args = ap.parse_args()

    os.makedirs(REPORTS, exist_ok=True)
    report = os.path.join(REPORTS, args.report + ".txt")
    p = Pad(transcript=report)
    cps = Checkpoints(conn=Shim(p))
    log = []

    cps.load(args.checkpoint)
    settle(p, log)
    log.append("loaded %s at %s" % (args.checkpoint, map_id(p)))

    # 1. leave the gym so the city transition zeroes the puzzle.
    # From (7,12) the odd layout only opens the pocket column x=5, so go left
    # twice first, then straight down through the door at y=20.
    log.append("start tile %s" % (tile(p),))
    for d, n in (("left", 3), ("down", 9)):
        for i in range(n):
            if map_id(p) != GYM:
                break
            move(p, d, "exit-%s%d" % (d, i), log)
    log.append("outside: map %s at %s" % (map_id(p), tile(p)))

    # 2. walk back in - trainers stay beaten, the maze is back to state 0
    for i in range(6):
        if map_id(p) == GYM:
            break
        move(p, "up", "enter%d" % i, log)
    log.append("inside: map %s at %s" % (map_id(p), tile(p)))

    # the warp drops us on the door tile (4,20); the route starts at (4,19)
    for i in range(3):
        if tile(p) == (4, 19):
            break
        move(p, "up", "prep%d" % i, log)
    log.append("route start %s" % (tile(p),))

    # 3. the one order the simulation found
    tag = 0
    for d, n in ROUTE:
        for _ in range(n):
            tag += 1
            move(p, d, "s%02d" % tag, log)

    st = p.ask(cmd="emerald_dev_state")
    vars_by_name, _ = variable_ids()
    state = p.ask(cmd="emerald_dev_var", id=vars_by_name["VAR_MAUVILLE_GYM_STATE"]).get("value")
    log.append("final: pos %s state %d" % ((st.get("pos") or {}), state))
    log.append("last speech: %s" % p.status().get("message"))

    with open(os.path.join(REPORTS, args.report + ".log"), "w") as fh:
        fh.write("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()

"""Petalburg, walked at frame speed: held direction runs instead of one poll per tile.

The room-by-room walker spends most of its time asking the mod whether the player
is free. The gym is a corridor (x 9..16) with rooms off to the left and Norman's
room at the top, so the route is a handful of straight runs; walking each run with
one held direction cuts a 116-tile walk down to a few seconds per leg.

    python3 artifacts/playtest/petalburg_fast.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402
from gym_walker import DIRS, here, live_grid, people, route  # noqa: E402

REPORT = os.path.join(HERE, "reports", "petalburg-walk.txt")
GOAL = (4, 3)
LOG = os.path.join(HERE, "reports", "petalburg-walk.log")


def runs(steps):
    """Collapse a step list into (direction, count) legs."""
    out = []
    for d in steps:
        if out and out[-1][0] == d:
            out[-1] = (d, out[-1][1] + 1)
        else:
            out.append((d, 1))
    return out


def main():
    p = Pad(transcript=REPORT)
    fh = open(LOG, "w")

    def say(t):
        print(t, flush=True)
        fh.write(t + "\n")
        fh.flush()

    say("start %s" % (here(p),))
    for leg in range(40):
        if here(p) == GOAL:
            break
        grid = live_grid(p, 24, 126)
        plan = route(here(p), GOAL, grid, people(p) - {GOAL})
        if plan is None:
            say("no route from %s" % (here(p),))
            break
        d, n = runs(plan)[0]
        before = here(p)
        p.walk(d, n, tag="leg%02d" % leg)
        p.flush_speech("leg%02d-%s%d" % (leg, d, n))
        after = here(p)
        say("leg %d: %s x%d %s -> %s" % (leg, d, n, before, after))
        if p.status().get("scene") == "battle":
            fight_if_needed(p, "fight%02d" % leg, fh)
            p.flush_speech("fight%02d" % leg)
            for i in range(10):
                if p.status().get("scene") != "battle":
                    break
                p.confirm(40)
            say("leg %d: fought, at %s" % (leg, here(p)))
        elif after == before:
            say("leg %d: did not move, stopping" % leg)
            break

    if here(p) == GOAL:
        say("at Norman, talking")
        p.action("north", 12)
        for i in range(4):
            p.confirm(40)
            p.flush_speech("talk%d" % i)
            if p.status().get("scene") == "battle":
                break
        for rnd in range(10):
            if p.status().get("scene") != "battle":
                break
            fight_if_needed(p, "norman%d" % rnd, fh)
            p.flush_speech("norman%d" % rnd)
            for i in range(6):
                if p.status().get("scene") != "battle":
                    break
                p.confirm(40)
        for i in range(25):
            p.confirm(40)
            p.flush_speech("prize%d" % i)
        say("final %s scene %s" % (here(p), p.status().get("scene")))
    else:
        say("stopped at %s, not at Norman" % (here(p),))
    fh.close()


if __name__ == "__main__":
    main()

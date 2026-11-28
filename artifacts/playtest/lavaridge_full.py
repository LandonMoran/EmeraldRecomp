"""One uninterrupted walk from the gym entrance to Flannery's room.

No reloading, no splicing transcripts: the checkpoint is loaded once, the route
is walked, trainer ambushes are fought as they happen, and the detour around
Kindler Danielle (who ends up standing on the pit at 1F (5,2)) is taken
automatically when the planned route stalls there. Every utterance the mod makes
is written to the transcript with the step that produced it.

    python3 artifacts/playtest/lavaridge_full.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402
from lavaridge_route import ROUTE, REMAINDER, FLOOR  # noqa: E402

REPORT = os.path.join(HERE, "reports", "lavaridge-full-walk.txt")


class Shim:
    def __init__(self, p):
        self.p = p

    def ask(self, **kw):
        return self.p.ask(**kw)


def at(p):
    o = p.obj()
    return (FLOOR.get(tuple(p.map()), str(tuple(p.map()))), o["x"] - 7, o["y"] - 7)


def free(p):
    st = p.ask(cmd="emerald_dev_state")
    return (p.status().get("scene") == "overworld" and not st.get("message_box")
            and not st.get("controls_locked"))


def settle(p, log, limit=30):
    for _ in range(limit):
        if free(p):
            return True
        p.confirm(30)
    log.append("settle gave up")
    return False


def clear_battle(p, log, tag):
    for i in range(10):
        if free(p):
            return
        fight_if_needed(p, tag, log)
        p.flush_speech("%s-%d" % (tag, i))


def walk(p, route, tag, log):
    """Walk the list; returns how many steps were completed."""
    done = 0
    for i, (direction, floor, x, y) in enumerate(route):
        want = (floor, x, y)
        ok = False
        for attempt in range(3):
            p.step(direction)
            p.flush_speech("%s%02d-%s" % (tag, i, direction))
            settle(p, log)
            if not free(p):
                clear_battle(p, log, "fight%s%02d" % (tag, i))
                settle(p, log)
            if at(p) == want:
                ok = True
                break
        if not ok:
            log.append("%s%02d %s: wanted %s, at %s" % (tag, i, direction, want, at(p)))
            return done
        done += 1
    return done


def main():
    p = Pad(transcript=REPORT)
    log = []
    Checkpoints(conn=Shim(p)).load("lavaridge-gym")
    settle(p, log)
    log.append("start at %s" % (at(p),))
    done = walk(p, ROUTE, "walk", log)
    log.append("route leg: %d of %d steps, at %s" % (done, len(ROUTE), at(p)))
    if at(p) != ("1F", 13, 10):
        # The only planned interruption: Danielle's ambush leaves her standing on
        # the pit the route falls through.
        here = at(p)
        done2 = walk(p, REMAINDER, "det", log)
        log.append("detour leg: %d of %d steps, at %s" % (done2, len(REMAINDER), at(p)))
    log.append("finished at %s, scene %s" % (at(p), p.status().get("scene")))
    with open(REPORT + ".log", "w") as fh:
        fh.write("\n".join(log) + "\n")
    print("\n".join(log[-3:]))


if __name__ == "__main__":
    main()

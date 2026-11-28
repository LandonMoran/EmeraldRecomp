"""Walk the Lavaridge gym route the game actually has, one spoken cue at a time.

The route comes from the level's own data: collision from the engine's working
grid, pits as one-way drops straight down, geysers as a lift to the tile one east
of the vent, and the jump-south ledges (metatile behavior 0x3b) that are the only
way into the basement box holding the geyser for Flannery's room. Every step is
recorded with what the mod said about it.

    python3 artifacts/playtest/lavaridge_route.py --checkpoint lavaridge-gym
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402

REPORT = os.path.join(HERE, "reports", "lavaridge-walk.txt")

# (direction, floor, x, y) - the tile the step should leave us standing on.
ROUTE = [
    ("left", "1F", 12, 17), ("left", "1F", 11, 17), ("up", "1F", 11, 16),
    ("left", "1F", 10, 16), ("left", "1F", 9, 16),
    ("up", "1F", 9, 15), ("up", "1F", 9, 14), ("up", "1F", 9, 13),
    ("up", "1F", 9, 12), ("up", "1F", 9, 11), ("up", "1F", 9, 10),
    ("up", "1F", 9, 9),
    ("left", "B1F", 8, 9),                      # fall through the pit
    ("down", "B1F", 8, 10), ("down", "B1F", 8, 11), ("down", "B1F", 8, 12),
    ("down", "B1F", 8, 13), ("down", "B1F", 8, 14), ("down", "B1F", 8, 15),
    ("down", "B1F", 8, 16), ("down", "B1F", 8, 17),
    ("left", "B1F", 7, 17), ("left", "B1F", 6, 17), ("left", "B1F", 5, 17),
    ("left", "B1F", 4, 17), ("left", "B1F", 3, 17),
    ("up", "B1F", 3, 16), ("up", "B1F", 3, 15), ("up", "B1F", 3, 14),
    ("left", "B1F", 2, 14),
    ("left", "1F", 2, 14),                      # geyser up
    ("up", "1F", 2, 13), ("up", "1F", 2, 12), ("up", "1F", 2, 11),
    ("up", "1F", 2, 10),
    ("left", "1F", 1, 10),
    ("left", "B1F", 0, 10),                     # fall through the pit
    ("up", "B1F", 0, 9), ("up", "B1F", 0, 8), ("up", "B1F", 0, 7),
    ("up", "1F", 1, 6),                         # geyser up
    ("up", "1F", 1, 5), ("up", "1F", 1, 4), ("up", "1F", 1, 3),
    ("up", "1F", 1, 2),
    ("right", "1F", 2, 2), ("right", "1F", 3, 2), ("right", "1F", 4, 2),
    ("right", "B1F", 5, 2),                     # fall through the pit
    ("right", "B1F", 6, 2),
    ("right", "1F", 8, 2),                      # geyser up
    ("down", "1F", 8, 3), ("down", "1F", 8, 4), ("down", "1F", 8, 5),
    ("right", "1F", 9, 5),
    ("down", "1F", 9, 6),
    ("right", "B1F", 10, 6),                    # fall through the pit
    ("down", "B1F", 10, 7), ("down", "B1F", 10, 8), ("down", "B1F", 10, 9),
    ("down", "B1F", 10, 11),                    # jump the ledge into the box
    ("down", "B1F", 10, 12),
    ("right", "B1F", 11, 12),
    ("right", "1F", 13, 12),                    # geyser into Flannery's room
    ("up", "1F", 13, 11), ("up", "1F", 13, 10),
]

REMAINDER = [
    ("down", "1F", 4, 3), ("left", "1F", 3, 3),
    ("left", "B1F", 2, 3), ("right", "B1F", 3, 3), ("right", "B1F", 4, 3),
    ("right", "B1F", 5, 3), ("up", "B1F", 5, 2), ("right", "B1F", 6, 2),
    ("right", "1F", 8, 2),
    ("down", "1F", 8, 3), ("down", "1F", 8, 4), ("down", "1F", 8, 5),
    ("right", "1F", 9, 5), ("down", "1F", 9, 6),
    ("right", "B1F", 10, 6),
    ("down", "B1F", 10, 7), ("down", "B1F", 10, 8), ("down", "B1F", 10, 9),
    ("down", "B1F", 10, 11), ("down", "B1F", 10, 12),
    ("right", "B1F", 11, 12),
    ("right", "1F", 13, 12),
    ("up", "1F", 13, 11), ("up", "1F", 13, 10),
]

FLOOR = {(4, 1): "1F", (4, 2): "B1F"}


class Shim:
    def __init__(self, p):
        self.p = p

    def ask(self, **kw):
        return self.p.ask(**kw)


def settle(p, limit=40):
    for _ in range(limit):
        st = p.ask(cmd="emerald_dev_state")
        if (not st.get("message_box") and not st.get("controls_locked")
                and p.status().get("scene") == "overworld"):
            return True
        p.confirm(30)
    return False


def at(p):
    o = p.obj()
    return (FLOOR.get(tuple(p.map()), str(tuple(p.map()))), o["x"] - 7, o["y"] - 7)


def walk(p, log, route=None):
    for i, (direction, floor, x, y) in enumerate(route or ROUTE):
        want = (floor, x, y)
        for attempt in range(3):
            p.step(direction)
            p.flush_speech(f"walk{i:02d}-{direction}")
            settle(p)
            if (p.status().get("scene") == "battle"
                    or p.ask(cmd="emerald_dev_state").get("controls_locked")):
                fight_if_needed(p, f"fight{i:02d}", log)
                settle(p)
            if at(p) == want:
                log.append(f"{i:02d} {direction} -> {want} ok")
                break
        else:
            log.append(f"{i:02d} {direction} -> wanted {want}, at {at(p)} STUCK")
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default="lavaridge-gym")
    ap.add_argument("--resume", action="store_true",
                    help="keep the current game state and walk the detour "
                         "around the buried trainer who now stands on (5,2)")
    args = ap.parse_args()
    p = Pad(transcript=REPORT)
    log = []
    route = REMAINDER if args.resume else ROUTE
    if not args.resume:
        Checkpoints(conn=Shim(p)).load(args.checkpoint)
    settle(p)
    log.append(f"start at {at(p)}")
    ok = walk(p, log, route)
    log.append(f"{'reached' if ok else 'stopped at'} {at(p)}, scene {p.status().get('scene')}")
    open(REPORT, "w").write("\n".join(log) + "\n")
    print("\n".join(log[-6:]))


if __name__ == "__main__":
    main()

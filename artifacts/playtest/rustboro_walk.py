"""Rustboro gym: walk in, beat the three trainers, beat Roxanne, record the lines.

No puzzle here - the gym is one room of rock formations - so the walk is plain
BFS on the room's own collision, with the trainers treated as obstacles until
their sight lines start the fight. Everything spoken goes to the transcript.

    python3 artifacts/playtest/rustboro_walk.py
"""

import json
import os
import struct
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402

ROOT = "third_party/pokeemerald"
REPORT = os.path.join(HERE, "reports", "rustboro-walk.txt")
DIRS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}
# People in the room: trainers who will start a fight, plus the guide.
NPCS = {(5, 13), (3, 9), (1, 6), (3, 18), (5, 2)}


class Shim:
    def __init__(self, p):
        self.p = p

    def ask(self, **kw):
        return self.p.ask(**kw)


def grid():
    layouts = json.load(open(os.path.join(ROOT, "data/layouts/layouts.json")))["layouts"]
    lay = next(x for x in layouts if x["name"] == "RustboroCity_Gym_Layout")
    raw = open(os.path.join(ROOT, lay["blockdata_filepath"]), "rb").read()
    w, h = lay["width"], lay["height"]

    def walkable(x, y):
        if not (0 <= x < w and 0 <= y < h):
            return False
        off = 2 * (x + w * y)
        return ((struct.unpack("<H", raw[off:off + 2])[0] >> 10) & 3) == 0

    return walkable


def route(start, goal, walkable):
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for name, (dx, dy) in DIRS.items():
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in prev or not walkable(*nxt) or nxt in NPCS:
                continue
            prev[nxt] = (cur, name)
            q.append(nxt)
    if goal not in prev:
        return None
    out, cur = [], goal
    while prev[cur] is not None:
        p, name = prev[cur]
        out.append(name)
        cur = p
    return list(reversed(out))


def free(p):
    st = p.ask(cmd="emerald_dev_state")
    return (p.status().get("scene") == "overworld" and not st.get("message_box")
            and not st.get("controls_locked"))


def main():
    p = Pad(transcript=REPORT)
    log = []
    if "--resume" not in sys.argv:
        Checkpoints(conn=Shim(p)).load("lavaridge-gym")
        for _ in range(30):
            if free(p):
                break
            p.confirm(30)
    # emerald_dev_warp refuses while the avatar is mid-script ("avatar flags
    # 0x01"), which a freshly loaded checkpoint is for a while. pad.force_map
    # writes the location and asks the game to load the map itself, which is the
    # same path without that gate.
    if "--resume" not in sys.argv:
        r = {}
        for i in range(6):
            r = p.ask(cmd="emerald_dev_warp", map_group=11, map_num=3, x=5, y=18,
                      facing="north")
            if r.get("ok"):
                break
            p.frames(40)
        log.append("dev warp: %s" % r)
        if not r.get("ok"):
            p.force_map(11, 3, 5, 18)
            log.append("force_map fallback used")
    for _ in range(40):
        if free(p):
            break
        p.confirm(30)
    o = p.obj()
    log.append("in the gym at (%d,%d)" % (o["x"] - 7, o["y"] - 7))

    walkable = grid()
    here = (o["x"] - 7, o["y"] - 7)
    steps = route(here, (5, 3), walkable)
    log.append("route %s: %s" % (len(steps) if steps else None, " ".join(steps or [])))
    for i, d in enumerate(steps or []):
        p.step(d)
        p.flush_speech("walk%02d-%s" % (i, d))
        for _ in range(20):
            if free(p):
                break
            p.confirm(30)
        if not free(p):
            fight_if_needed(p, "fight%02d" % i, log)
            p.flush_speech("fight%02d" % i)
            for _ in range(20):
                if free(p):
                    break
                p.confirm(30)
        o = p.obj()
        log.append("%02d %s -> (%d,%d)" % (i, d, o["x"] - 7, o["y"] - 7))

    # Roxanne is one tile north of (5,3).
    p.action("north", 12)
    for i in range(6):
        if free(p):
            p.confirm(40)
        p.confirm(40)
        p.flush_speech("talk%d" % i)
        if p.status().get("scene") == "battle":
            break
    for rnd in range(10):
        if free(p):
            break
        fight_if_needed(p, "roxanne%d" % rnd, log)
        p.flush_speech("roxanne%d" % rnd)
        for i in range(8):
            if free(p):
                break
            p.confirm(40)
            p.flush_speech("prize%d-%d" % (rnd, i))
    for i in range(20):
        if free(p):
            break
        p.confirm(40)
    p.flush_speech("end")

    with open(REPORT + ".log", "w") as fh:
        fh.write("\n".join(log) + "\n")
    print("\n".join(log[-4:]))


if __name__ == "__main__":
    main()

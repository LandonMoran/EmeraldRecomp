"""Walk a gym whose only trick is one-way ledges (Fortree), then take the leader.

Fortree's gym is a left-hand maze with three rows of south-jumping ledges across
the right-hand column. A ledge is solid in the collision data, so a plain BFS
cannot cross it; here an edge exists from the tile above a jump-south ledge to
the tile below it, which is what pressing south does.

    python3 artifacts/playtest/gym_ledge.py --layout FortreeCity_Gym_Layout \
        --group 12 --num 1 --start 15 23 --goal 15 3 --leader WINONA \
        --report artifacts/playtest/reports/fortree-walk.txt
"""

import argparse
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402
from gym_walker import here, people  # noqa: E402
from mapdata import Layout  # noqa: E402

JUMP_SOUTH = 0x3B
DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}


class Log:
    def __init__(self, fh):
        self.fh = fh

    def append(self, text):
        print(text, flush=True)
        self.fh.write(text + "\n")
        self.fh.flush()


def live_tiles(p, width, height):
    """(walkable, elevation) per tile, from the engine's padded backup buffer.

    Elevation is not a property of a tile you can compare to a constant: the
    engine refuses a step when the target's elevation differs from the tile the
    player is standing on, except across transition tiles (14, multi-level, and
    15, transition). Fortree's maze is built out of exactly those steps, so the
    graph has to be elevation-aware per edge.
    """
    import struct
    from gym_walker import read
    w, h, ptr = struct.unpack("<III", read(p, 0x03005DC0, 12))
    raw = read(p, ptr, 2 * w * h)
    v = struct.unpack("<%dH" % (w * h), raw)
    out = {}
    for y in range(height):
        for x in range(width):
            if x + 7 >= w or y + 7 >= h:
                out[(x, y)] = (False, 0)
                continue
            b = v[(y + 7) * w + (x + 7)]
            out[(x, y)] = (((b >> 10) & 3) == 0, (b >> 12) & 0xF)
    return out


def step_ok(tiles, a, b):
    ok, elev = tiles[b]
    if not ok:
        return False
    here_elev = tiles[a][1]
    return elev == here_elev or elev in (14, 15) or here_elev in (14, 15)


def plan(lay, start, goal, blocked=frozenset(), tiles=None, dir_block=frozenset()):
    w, h = lay.width, lay.height
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        x, y = cur
        for name, (dx, dy) in DIRS.items():
            nxt = (x + dx, y + dy)
            if not (0 <= nxt[0] < w and 0 <= nxt[1] < h) or nxt in prev:
                continue
            if nxt in blocked or (nxt[0], nxt[1], name) in dir_block:
                continue
            if step_ok(tiles, cur, nxt):
                prev[nxt] = (cur, name)
                q.append(nxt)
            elif (lay.behavior(*nxt) == JUMP_SOUTH and name == "south"
                  and step_ok(tiles, cur, (x, y + 2))
                  and (x, y + 2) not in prev
                  and (x, y + 2) not in blocked):
                prev[(x, y + 2)] = (cur, name)
                q.append((x, y + 2))
    if goal not in prev:
        return None
    out, cur = [], goal
    while prev[cur] is not None:
        cur, name = prev[cur]
        out.append(name)
    return list(reversed(out))


def drain(p, fh, tag):
    for i in range(25):
        st = p.ask(cmd="emerald_dev_state")
        if not st.get("message_box") and not st.get("controls_locked"):
            return
        p.confirm(40)
        p.flush_speech(tag + "-drain%d" % i)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", required=True)
    ap.add_argument("--group", type=int, required=True)
    ap.add_argument("--num", type=int, required=True)
    ap.add_argument("--start", type=int, nargs=2, required=True)
    ap.add_argument("--goal", type=int, nargs=2, required=True)
    ap.add_argument("--leader", required=True)
    ap.add_argument("--talk", default="north")
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    p = Pad(transcript=args.report)
    fh = open(args.report + ".log", "w")
    log = Log(fh)
    lay = Layout(args.layout)

    if args.checkpoint:
        class S:
            def __init__(self, p):
                self.p = p

            def ask(self, **kw):
                return self.p.ask(**kw)
        Checkpoints(conn=S(p)).load(args.checkpoint)
        drain(p, fh, "load")
    p.force_map(args.group, args.num, args.start[0], args.start[1])
    p.frames(90)
    drain(p, fh, "enter")
    log.append("start %s map %s" % (here(p), tuple(p.map())))

    goal = tuple(args.goal)
    extra = set()          # tiles always refused
    dir_block = set()      # (x, y, direction) refusals: ledges block one way only
    for attempt in range(30):
        if here(p) == goal:
            break
        tiles = live_tiles(p, lay.width, lay.height)
        steps = plan(lay, here(p), goal, (people(p) - {goal}) | extra,
                     tiles, dir_block)
        if steps is None:
            log.append("no route from %s" % (here(p),))
            break
        log.append("leg %d: %d steps" % (attempt, len(steps)))
        for i, d in enumerate(steps):
            before = here(p)
            p.ask(cmd="emerald_a11y_action", action=d)
            p.frames(56)
            p.flush_speech("s%03d-%s" % (i, d))
            if p.status().get("scene") == "battle":
                fight_if_needed(p, "fight%03d" % i, log)
                p.flush_speech("fight%03d" % i)
                drain(p, fh, "fight%03d" % i)
                break
            if here(p) == before:
                tx = before[0] + DIRS[d][0]
                ty = before[1] + DIRS[d][1]
                if (tx, ty) in people(p):
                    # someone in the way: talk to them
                    p.confirm(45)
                    p.flush_speech("talk%03d" % i)
                    if p.status().get("scene") == "battle":
                        fight_if_needed(p, "talkfight%03d" % i, log)
                        p.flush_speech("talkfight%03d" % i)
                        drain(p, fh, "talkfight%03d" % i)
                        break
                dir_block.add((tx, ty, d))
                log.append("step %d %s refused -> %s" % (i, d, (tx, ty)))
                break
            if False:
                # someone standing in the way: talk to them
                p.confirm(45)
                p.flush_speech("talk%03d" % i)
                if p.status().get("scene") == "battle":
                    fight_if_needed(p, "talkfight%03d" % i, log)
                    p.flush_speech("talkfight%03d" % i)
                    drain(p, fh, "talkfight%03d" % i)
                    break
        log.append("after leg %d: %s" % (attempt, here(p)))

    if here(p) == goal:
        p.action(args.talk, 12)
        for i in range(4):
            p.confirm(45)
            p.flush_speech("leader-talk%d" % i)
            if p.status().get("scene") == "battle":
                break
        for rnd in range(12):
            if p.status().get("scene") != "battle":
                break
            fight_if_needed(p, "%s%d" % (args.leader.lower(), rnd), log)
            p.flush_speech("%s%d" % (args.leader.lower(), rnd))
            for i in range(8):
                if p.status().get("scene") != "battle":
                    break
                p.confirm(45)
        for i in range(28):
            p.confirm(45)
            p.flush_speech("prize%d" % i)
        log.append("final %s scene %s" % (here(p), p.status().get("scene")))
    else:
        log.append("not at the goal: %s" % (here(p),))
    fh.close()


if __name__ == "__main__":
    main()

"""Walk a gym room to a tile using the game's own collision and the mod's speech.

Every gym left is the same shape of job: get into the room, walk to the leader
around whatever is standing in the way, fight what starts a fight, and record
what the mod said. Lavaridge needed a hand-built model because pits and ledges
rewrite the graph; a plain room does not, so this reads the live grid the puzzle
layer reads (gBackupMapLayout, padded by MAP_OFFSET) and the occupied tiles out of
the object table, then walks the shortest way.

    python3 artifacts/playtest/gym_walker.py --group 11 --num 3 --start 5 18 \
        --goal 5 3 --report reports/rustboro-walk.txt
    python3 artifacts/playtest/gym_walker.py ... --talk north --leader "ROXANNE"
"""

import argparse
import json
import os
import struct
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402

DIRS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}
GW, GH, OFF = 32, 33, 7          # gBackupMapLayout padding for a <=17x19 map


def read(conn, addr, n):
    cmd = ("read_rom" if 0x08000000 <= addr < 0x0A000000
           else ("read_iwram" if addr >= 0x03000000 else "read_ewram"))
    r = conn.ask(cmd=cmd, addr=addr, len=n)
    return bytes.fromhex(r["data"])


BACKUP = 0x03005DC0     # gBackupMapLayout: width, height, then the block pointer


def live_grid(p, width, height):
    """Collision straight from the engine's working copy of the map.

    The block pointer is read per map: hardcoding Lavaridge's made every other
    gym look like Lavaridge's basement.
    """
    head = read(p, BACKUP, 12)
    w, h, blocks = struct.unpack("<III", head)
    n = w * h * 2
    r = p.ask(cmd="read_ewram", addr=blocks, len=n)
    v = struct.unpack("<%dH" % (w * h), bytes.fromhex(r["data"]))
    return {(x, y) for y in range(height) for x in range(width)
            if 0 <= x + OFF < w and 0 <= y + OFF < h
            and ((v[(y + OFF) * w + (x + OFF)] >> 10) & 3) == 0}


def people(p):
    """Object tiles, converted to map tiles (object events are stored +7)."""
    return {(x - 7, y - 7) for x, y in p.npc_tiles()}


def free(p):
    st = p.ask(cmd="emerald_dev_state")
    return (p.status().get("scene") == "overworld" and not st.get("message_box")
            and not st.get("controls_locked"))


def settle(p, log, limit=25):
    for _ in range(limit):
        if free(p):
            return True
        p.confirm(30)
    return False


def here(p):
    o = p.obj()
    return (o["x"] - 7, o["y"] - 7)


def door_pairs(group, num, path="artifacts/puzzles/maps.json"):
    """Same-map warps: the tile you step on, and the tile you land on.

    Petalburg's gym is one map of rooms joined by door warps, and each warp
    names its destination as an index into the same map's warp list, so the
    pairing is right there in the data.
    """
    maps = json.load(open(path))["maps"]
    m = next(x for x in maps if x["group"] == group and x["num"] == num)
    warps = m["warps"]
    # maps.json names the map "PetalburgCity_Gym" but the warp says
    # "MAP_PETALBURG_CITY_GYM"; compare the letters only.
    me = m["name"].lower().replace("_", "")
    out = {}
    for w in warps:
        if w["dest_map"].lower().replace("map_", "").replace("_", "") != me:
            continue
        dest = warps[int(w["dest_warp_id"])]
        out[(w["x"], w["y"])] = (dest["x"], dest["y"])
    return out


def route(start, goal, walkable, blocked, doors=None):
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for name, (dx, dy) in DIRS.items():
            nxt = (cur[0] + dx, cur[1] + dy)
            # A gym door reads as solid in the collision data but the game
            # slides you through it, so door tiles are enterable.
            if nxt in prev or (nxt not in walkable and nxt not in (doors or {})):
                continue
            if nxt in blocked and nxt != goal:
                continue
            prev[nxt] = (cur, name)
            q.append(nxt)
            land = (doors or {}).get(nxt)
            if land and land not in prev and land in walkable and land != nxt:
                prev[land] = (cur, name)
                q.append(land)
    if goal not in prev:
        return None
    out, cur = [], goal
    while prev[cur] is not None:
        p, name = prev[cur]
        out.append(name)
        cur = p
    return list(reversed(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", type=int, required=True)
    ap.add_argument("--num", type=int, required=True)
    ap.add_argument("--start", type=int, nargs=2, default=None,
                    help="tile to force the map load at (omit to stay put)")
    ap.add_argument("--goal", type=int, nargs=2, required=True)
    ap.add_argument("--width", type=int, default=17)
    ap.add_argument("--height", type=int, default=19)
    ap.add_argument("--facing", default="north")
    ap.add_argument("--talk", default=None, help="face this way and press A at the goal")
    ap.add_argument("--leader", default=None, help="name to look for in the prize lines")
    ap.add_argument("--replan", action="store_true",
                    help="doors teleport, so re-plan after every step")
    ap.add_argument("--clear-rooms", action="store_true",
                    help="when the goal is unreachable, beat the nearest trainer")
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    p = Pad(transcript=args.report)
    log = []
    if args.start:
        p.force_map(args.group, args.num, args.start[0], args.start[1])
        settle(p, log)
    log.append("start %s on map %s" % (here(p), tuple(p.map())))

    walkable = live_grid(p, args.width, args.height)
    doors = door_pairs(args.group, args.num)
    log.append("same-map doors: %d" % len(doors))
    blocked = people(p)
    log.append("walkable %d tiles, %d occupied" % (len(walkable), len(blocked)))
    goal = tuple(args.goal)
    steps = route(here(p), goal, walkable, blocked - {goal}, doors)
    log.append("route: %s" % (" ".join(steps) if steps else None))
    if args.replan:
        done = 0
        while here(p) != goal and done < 220:
            blocked = people(p)
            plan = route(here(p), goal, walkable, blocked - {goal}, doors)
            if plan is None and args.clear_rooms:
                # A room's door only opens once its trainer is beaten, so when
                # the goal is walled off the nearest person is the way through.
                near = sorted(blocked, key=lambda t: abs(t[0] - here(p)[0])
                              + abs(t[1] - here(p)[1]))
                for cand in near[:3]:
                    plan = route(here(p), cand, walkable, blocked - {cand}, doors)
                    if plan is not None:
                        log.append("blocked; going to beat the trainer at %s" % (cand,))
                        goal_here = cand
                        break
                else:
                    log.append("stuck at %s, nothing reachable" % (here(p),))
                    break
            elif plan is None:
                log.append("no route from %s" % (here(p),))
                break
            d = plan[0]
            before = here(p)
            p.step(d)
            p.flush_speech("step%03d-%s" % (done, d))
            settle(p, log)
            if not free(p):
                fight_if_needed(p, "fight%03d" % done, log)
                p.flush_speech("fight%03d" % done)
                settle(p, log)
            if here(p) != before:
                log.append("%03d %s %s -> %s" % (done, d, before, here(p)))
            done += 1
        steps = []
    for i, d in enumerate(steps or []):
        p.step(d)
        p.flush_speech("walk%02d-%s" % (i, d))
        settle(p, log)
        if not free(p):
            fight_if_needed(p, "fight%02d" % i, log)
            p.flush_speech("fight%02d" % i)
            settle(p, log)
            blocked = people(p)
        log.append("%02d %s -> %s" % (i, d, here(p)))

    if args.talk and here(p) != goal:
        log.append("not at the goal (%s), not talking" % (here(p),))
    if args.talk and here(p) == goal:
        p.action(args.talk, 12)
        for i in range(4):
            p.confirm(40)
            p.flush_speech("talk%d" % i)
            if p.status().get("scene") == "battle" or not free(p):
                break
        for rnd in range(12):
            if free(p):
                break
            fight_if_needed(p, "leader%d" % rnd, log)
            p.flush_speech("leader%d" % rnd)
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

    with open(args.report + ".log", "w") as fh:
        fh.write("\n".join(log) + "\n")
    print("\n".join(log[-3:]))


if __name__ == "__main__":
    main()

"""Solve Mossdeep's rotating statues: measure the rotations, then search them.

Why a model and not a walk
--------------------------
The gym's nine floor switches each call ``moverotatingtileobjects``, which turns
a group of statue objects a quarter turn. A greedy walker cannot solve that: the
board it needs to reason about is invisible to it until it presses, and pressing
blindly only ever finds the next switch in the same room (the search bounced
between (6,7) and (8,6) for exactly this reason).

So this measures the mechanic instead. Standing on a switch fires it; the statue
objects then stand in different tiles, and an object's old and new tile are a
point pair of the quarter turn that group makes. Five presses - one per colour -
give the transform of every group. With the transforms known, the whole gym is a
graph whose state is ``(tile, rotations)``:

* ``walk``  - to a neighbouring tile, if the live collision says walkable and no
  statue stands on it *in that rotation*,
* ``warp``  - the panels, resolved through ``dest_warp_id`` (the same edges the
  walker uses),
* ``press`` - standing on a switch, ``rotations[i] += 1 mod 4``; that relabels
  every statue of group ``i``.

The route is then produced by a breadth-first search over that graph, and the
emulator only has to carry it out. If the search finds nothing, the output says
so with the state it exhausted.

    python3 artifacts/playtest/mossdeep_solve.py --measure   # 5 presses, prints transforms
    python3 artifacts/playtest/mossdeep_solve.py --plan      # search + walk it
"""

import argparse
import json
import math
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from gym_graph import DIRS, build_edges, drain, plan, settled, tiles_of  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402
from gym_walker import door_pairs, people  # noqa: E402
from live_behavior import live_behaviors  # noqa: E402

GROUP, NUM = 14, 0
WIDTH, HEIGHT = 26, 36
ENTRANCE = (6, 35)
GOAL = (23, 8)
SWITCHES = {
    "yellow_a": (2, 21), "yellow_b": (3, 30), "blue_a": (8, 10),
    "blue_b": (6, 7), "red": (8, 6), "purple_a": (23, 24),
    "purple_b": (23, 21), "green": (15, 34),
}


def statues():
    """The statue object tiles, from the map's own object table."""
    path = os.path.join(HERE, "..", "..", "third_party", "pokeemerald", "data",
                        "maps", "MossdeepCity_Gym", "map.json")
    with open(path) as fh:
        data = json.load(fh)
    return {(o["x"], o["y"]) for o in data["object_events"]
            if "STATUE" in o["graphics_id"]}


def fit_rotation(pairs):
    """Centre and direction of the quarter turn that maps the old tiles to the new.

    A 90 degree rotation about c sends p to c + R(p - c). Two pairs already
    determine c; four (a statue count) make it a least-squares fit, and the sign
    of the turn falls out of the cross product.
    """
    if len(pairs) < 2:
        return None
    best = None
    for sign in (1, -1):
        def rot(p):
            # screen coordinates: x east, y south
            return (p[1], -p[0]) if sign == 1 else (-p[1], p[0])

        # (I - R) c = q - R p for every pair; least squares with normal equations.
        m = ((1.0 - 0.0, -1.0 * sign), (1.0 * sign, 1.0 - 0.0))
        # M = I - R, written out for both signs
        m = ((1.0, -sign), (sign, 1.0))
        a11 = a12 = a22 = b1 = b2 = 0.0
        for pxy, qxy in pairs:
            rp = rot(pxy)
            rhs = (qxy[0] - rp[0], qxy[1] - rp[1])
            a11 += m[0][0] * m[0][0] + m[1][0] * m[1][0]
            a12 += m[0][0] * m[0][1] + m[1][0] * m[1][1]
            a22 += m[0][1] * m[0][1] + m[1][1] * m[1][1]
            b1 += m[0][0] * rhs[0] + m[1][0] * rhs[1]
            b2 += m[0][1] * rhs[0] + m[1][1] * rhs[1]
        det = a11 * a22 - a12 * a12
        if abs(det) < 1e-9:
            continue
        cx = (b1 * a22 - b2 * a12) / det
        cy = (a11 * b2 - a12 * b1) / det
        err = 0.0
        for pxy, qxy in pairs:
            rp = rot(pxy)
            err += (cx + rp[0] - qxy[0]) ** 2 + (cy + rp[1] - qxy[1]) ** 2
        if best is None or err < best["err"]:
            best = {"centre": (cx, cy), "sign": sign, "err": err}
    return best


def apply_turn(tile, centre, sign, times=1):
    x, y = tile[0] - centre[0], tile[1] - centre[1]
    for _ in range(times % 4):
        x, y = (y, -x) if sign == 1 else (-y, x)
    return (int(round(x + centre[0])), int(round(y + centre[1])))


def walk_to(p, target, log):
    """Walk to a tile, re-planning if a warp lands somewhere unexpected."""
    for _ in range(4):
        if settled(p) == target:
            return True
        tiles = tiles_of(p, WIDTH, HEIGHT)
        beh, _meta = live_behaviors(p, WIDTH, HEIGHT)
        edges = build_edges(tiles, beh, WIDTH, HEIGHT, door_pairs(GROUP, NUM))
        avoid = frozenset(people(p) - {target})
        route = plan(edges, settled(p), target, avoid, set(), True)
        if route is None:
            route = plan(edges, settled(p), target, avoid, set(), False)
        if route is None:
            return False
        for direction, kind in route:
            p.walk(direction, 1)
            p.frames(80 if kind != "walk" else 34)
            if p.status().get("scene") != "overworld":
                fight_if_needed(p, "measure-fight", [])
        p.frames(40)
    return settled(p) == target


def measure(p, log):
    """Press each colour once and read where the statues went.

    Statues are found by differencing the whole object table: the tiles that
    vanish and appear when a switch fires are that group's statues, whatever
    the map file called them. Pairing them nearest-first gives the quarter
    turn's point pairs.
    """
    p.force_map(GROUP, NUM, ENTRANCE[0], ENTRANCE[1])
    p.frames(160)
    drain(p, open(os.devnull, "w"), "reset")
    before_all = set(people(p))
    log("objects before: %s" % (sorted(before_all),))
    transforms = {}
    for name, sw in SWITCHES.items():
        if not walk_to(p, sw, log):
            log("%s: could not reach %s (at %s)" % (name, sw, settled(p)))
            continue
        p.frames(70)
        after_all = set(people(p))
        gone = sorted(before_all - after_all)
        came = sorted(after_all - before_all)
        pairs = []
        used = set()
        for b in gone:
            best = None
            for a in came:
                if a in used:
                    continue
                d = abs(a[0] - b[0]) + abs(a[1] - b[1])
                if best is None or d < best[1]:
                    best = (a, d)
            if best:
                pairs.append((b, best[0]))
                used.add(best[0])
        fit = fit_rotation(pairs) if len(pairs) >= 2 else None
        log("%s at %s: %d moved %s -> %s | fit %s" % (name, sw, len(pairs), gone, came, fit))
        if fit and fit["err"] <= 0.01 * max(1, len(pairs)):
            transforms[name] = {"switch": sw, "centre": fit["centre"],
                                "sign": fit["sign"], "members": gone,
                                "err": fit["err"]}
        before_all = after_all
    return transforms


def search(grid, warps, transforms, start_state, goal):
    """BFS over (tile, rotations). Returns the action plan or None."""
    names = sorted(transforms)
    switches = {transforms[n]["switch"]: n for n in names}
    start = (start_state, tuple([0] * len(names)))
    seen = {start}
    queue = deque([(start, [])])
    while queue:
        (state, plan_so_far) = queue.popleft()
        pos, rots = state
        if pos == goal:
            return plan_so_far
        occupied = set()
        for i, name in enumerate(names):
            t = transforms[name]
            for m in t["members"]:
                occupied.add(apply_turn(m, t["centre"], t["sign"], rots[i]))
        if pos in switches:
            n = names.index(switches[pos])
            new_rots = list(rots)
            new_rots[n] = (new_rots[n] + 1) % 4
            nxt = (pos, tuple(new_rots))
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, plan_so_far + [("press", switches[pos], n)]))
        for d, (dx, dy) in DIRS.items():
            nxt = (pos[0] + dx, pos[1] + dy)
            if nxt in occupied:
                continue
            if nxt in warps:
                land = warps[nxt]
                step = (land, rots)
                kind = "warp"
            else:
                if not grid.get(nxt, (False,))[0]:
                    continue
                step = (nxt, rots)
                kind = "walk"
            if step not in seen:
                seen.add(step)
                queue.append((step, plan_so_far + [("walk", d, nxt if kind == "walk" else land)]))
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--transforms", default=os.path.join(HERE, "mossdeep_rotations.json"))
    ap.add_argument("--report", default=os.path.join(HERE, "reports", "mossdeep-route.txt"))
    args = ap.parse_args()

    p = Pad(transcript=args.report)
    log_fh = open(args.report + ".log", "a")

    def log(text):
        print(text, flush=True)
        log_fh.write(text + "\n")
        log_fh.flush()

    transforms = {}
    if args.measure or not os.path.exists(args.transforms):
        p.force_map(GROUP, NUM, ENTRANCE[0], ENTRANCE[1])
        p.frames(150)
        transforms = measure(p, log)
        with open(args.transforms, "w") as fh:
            json.dump(transforms, fh, indent=1)
        log("transforms written: %d groups" % len(transforms))
    else:
        with open(args.transforms) as fh:
            transforms = json.load(fh)
    if not args.plan:
        log_fh.close()
        return

    grid = tiles_of(p, WIDTH, HEIGHT)
    warps = door_pairs(GROUP, NUM)
    here = settled(p)
    route = search(grid, warps, transforms, here, GOAL)
    log("search from %s: %s" % (here, "no route" if route is None else "%d actions" % len(route)))
    if route is None:
        log("board states exhausted without reaching %s" % (GOAL,))
        log_fh.close()
        return
    for action in route:
        if action[0] == "press":
            # Standing on the switch does not fire it again: step off and back on.
            live = tiles_of(p, WIDTH, HEIGHT)
            busy = people(p)
            here_now = settled(p)
            for d, (dx, dy) in DIRS.items():
                side = (here_now[0] + dx, here_now[1] + dy)
                if live.get(side, (False,))[0] and side not in busy:
                    p.walk(d, 1)
                    p.frames(40)
                    p.walk({"north": "south", "south": "north",
                            "east": "west", "west": "east"}[d], 1)
                    p.frames(80)
                    break
            log("pressed %s, now at %s" % (action[1], settled(p)))
        else:
            p.walk(action[1], 1)
            p.frames(40)
            if p.status().get("scene") != "overworld":
                fight_if_needed(p, "route-fight", [])
                drain(p, open(os.devnull, "w"), "route-fight")
        p.flush_speech("route")
    log("arrived %s (goal %s)" % (settled(p), GOAL))
    log_fh.close()


if __name__ == "__main__":
    main()

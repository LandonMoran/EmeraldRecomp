"""Walk Mossdeep Gym to Tate & Liza: switches turn the board, warps cross it.

The gym's mechanic is a rotating one. Five colour switches are coord events that
call ``moverotatingtileobjects``: a quarter turn of a group of statue objects.
The statues are objects, so they are *obstacles that move* - the same tile is
open in one rotation and walled in the next. Two consequences:

* A route is only valid for the rotation it was planned in. So this walks one
  step at a time, re-reading collision and object positions after every step,
  and presses a switch whenever the leaders are not reachable.
* A map reload puts the statues back where the map file says they are, which is
  why the shared walker's re-anchor is disabled here: re-anchoring is what it
  does when a step is refused, and doing it in this gym would undo the puzzle it
  had just solved.

A refused step right after a warp is the known post-transition state (the same
one Fortree shows after a map load), so it is retried before being believed.

    python3 artifacts/playtest/mossdeep_run.py --checkpoint sootopolis-cleared \
        --report artifacts/playtest/reports/mossdeep-walk.txt
"""

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from gym_graph import (DIRS, build_edges, drain, plan, settled, switch_route,  # noqa: E402
                       tiles_of)
from gym_walk import fight_if_needed  # noqa: E402
from gym_walker import door_pairs, here, people  # noqa: E402
from live_behavior import live_behaviors  # noqa: E402

GROUP, NUM = 14, 0
WIDTH, HEIGHT = 26, 36
ENTRANCE = (6, 35)
SWITCHES = [(2, 21), (8, 10), (6, 7), (15, 34), (23, 24), (23, 21), (8, 6), (3, 30)]
GOAL = (23, 8)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", required=True)
    ap.add_argument("--checkpoint", default="")
    ap.add_argument("--goal", default="%d,%d" % GOAL)
    ap.add_argument("--leader", default="TATE & LIZA")
    ap.add_argument("--talk", default="north")
    ap.add_argument("--rounds", type=int, default=240)
    ap.add_argument("--start", default="",
                    help="x,y to force the map to; omit to carry on from where the player is")
    args = ap.parse_args()
    goal = tuple(int(v) for v in args.goal.split(","))

    p = Pad(transcript=args.report)
    log_path = args.report + ".log"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    fh = open(log_path, "w")

    def log(text):
        print(text, flush=True)
        fh.write(text + "\n")
        fh.flush()

    if args.checkpoint:
        class S:
            def __init__(self, pad):
                self.pad = pad

            def ask(self, **kw):
                return self.pad.ask(**kw)

        Checkpoints(conn=S(p)).load(args.checkpoint)
        drain(p, fh, "load")
    if args.start:
        x, y = (int(v) for v in args.start.split(","))
        p.force_map(GROUP, NUM, x, y)
        p.frames(120)
        drain(p, fh, "enter")
    log("start %s" % (settled(p),))

    turns = 0
    refused = set()
    # The board is state: a rotation is identified by where the statues stand.
    # (state, switch) pairs already pressed are not pressed again - without that
    # the walker bounces between two rooms, pressing the same switch forever,
    # because the nearest switch is always the one it just used.
    pressed_from = set()
    for i in range(args.rounds):
        # A trainer's sight line locks the field *before* the battle scene
        # starts, so "overworld" alone is not "free to walk".
        st = p.ask(cmd="emerald_dev_state")
        if p.status().get("scene") != "overworld" or st.get("controls_locked"):
            fight_if_needed(p, "r%d" % i, [])
            p.flush_speech("r%d" % i)
            drain(p, fh, "r%d" % i)
            continue
        pos = settled(p)
        if pos == goal:
            log("at the leaders' tile after %d rounds" % i)
            break
        tiles = tiles_of(p, WIDTH, HEIGHT)
        beh, _meta = live_behaviors(p, WIDTH, HEIGHT)
        warps = door_pairs(GROUP, NUM)
        edges = build_edges(tiles, beh, WIDTH, HEIGHT, warps)
        blocked = frozenset(people(p) - {goal})
        steps = plan(edges, pos, goal, blocked, refused, True)
        if steps is None:
            steps = plan(edges, pos, goal, blocked, refused, False)
        if steps is None:
            state = frozenset(people(p))
            best = None
            for sw in SWITCHES:
                if sw in blocked or sw == pos or (state, sw) in pressed_from:
                    continue
                route = plan(edges, pos, sw, blocked, refused, True)
                if route is None:
                    route = plan(edges, pos, sw, blocked, refused, False)
                if route is not None and (best is None or len(route) < len(best[1])):
                    best = (sw, route)
            if best is None:
                # Every switch reachable in this rotation has been tried from it.
                log("no route and no untried switch from %s" % (pos,))
                break
            sw, route = best
            pressed_from.add((state, sw))
            steps = route
            log("board closed at %s: pressing switch %s (%d steps)" % (pos, sw, len(route)))
        direction, kind = steps[0]
        before = pos
        moved = False
        for attempt in range(4):
            if kind == "walk":
                p.walk(direction, 1)
                p.frames(30)
            else:
                p.walk(direction, 1)
                p.frames(90)
            p.flush_speech("%03d-%s-%s-a%d" % (i, direction, kind, attempt))
            if p.status().get("scene") != "overworld":
                fight_if_needed(p, "%03d-fight" % i, [])
                p.flush_speech("%03d-fight" % i)
                drain(p, fh, "%03d-fight" % i)
                moved = True
                break
            after = settled(p)
            if after != before:
                moved = True
                break
            # A step refused straight after a warp is the known post-transition
            # state; wait it out before deciding the tile is a wall.
            p.frames(50 + 40 * attempt)
        if not moved:
            refused.add((before, direction))
            log("%03d %s refused at %s" % (i, direction, before))
            if len(refused) > 40:
                log("too many refusals, stopping")
                break
            continue
        after = settled(p)
        log("%03d %s %s %s -> %s" % (i, direction, kind, before, after))
        if after != before and (after[0], after[1]) in SWITCHES:
            p.frames(80)
            drain(p, fh, "%03d-turn" % i)
            turns += 1
            log("switch %s pressed (turn %d)" % (after, turns))
        time.sleep(0.05)

    final = settled(p)
    log("final %s, switches pressed %d, refusals %d" % (final, turns, len(refused)))
    if final == goal:
        p.action(args.talk, 12)
        for i in range(6):
            p.confirm(50)
            p.flush_speech("leader%d" % i)
            if p.status().get("scene") == "battle":
                break
        for rnd in range(16):
            if p.status().get("scene") != "battle":
                break
            fight_if_needed(p, "leader-r%d" % rnd, [])
            p.flush_speech("leader-r%d" % rnd)
            for _ in range(10):
                if p.status().get("scene") != "battle":
                    break
                p.confirm(50)
                p.flush_speech("leader-tail")
        for i in range(30):
            p.confirm(50)
            p.flush_speech("prize%d" % i)
        log("after the fight: scene %s at %s" % (p.status().get("scene"), settled(p)))
    fh.close()


if __name__ == "__main__":
    main()

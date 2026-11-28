"""Press all four Mauville gym plates by planning over what the mod announces.

The gym is a toggle maze: every plate press flips which energy beams block which
tiles, so the graph to search is (tile, beam state). The mod now reports, for the
tile the player stands on, which of the four neighbours a step would be refused
by — the same fact it speaks as "Blocked east." — so a plan can be made without
guessing, and nothing is used that a player could not hear.

    python3 artifacts/playtest/plan_gym.py --checkpoint party-fight

It loads a checkpoint, walks into the gym, and then repeats: read the neighbours,
extend the known graph for the current beam state, walk to the nearest unpressed
plate the graph can reach, and if none is reachable, walk to the boundary of what
is known and step into the dark.
"""

import argparse
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import party  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from pad import Pad  # noqa: E402

REPORTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
PLATES = {(0, 15): "plate 1", (4, 12): "plate 2", (3, 9): "plate 3", (8, 9): "plate 4"}
DELTA = {"n": (0, -1), "e": (1, 0), "s": (0, 1), "w": (-1, 0)}
DIR = {"n": "up", "e": "right", "s": "down", "w": "left"}
OPPOSITE = {"n": "s", "e": "w", "s": "n", "w": "e"}
MOVE_LIMIT = 220
EXIT_TILES = {(4, 19), (5, 19), (4, 20), (5, 20)}   # the door back to the city


class Plan:
    def __init__(self):
        self.known = {}     # parity -> {(x, y): set(open dirs)}

    def graph(self, parity):
        return self.known.setdefault(parity, {})

    def observe(self, parity, tile, opens):
        self.graph(parity)[tile] = set(opens)

    def frontier(self, parity, start):
        """Nearest tile that has a neighbour we have not entered yet."""
        graph = self.graph(parity)
        seen = {start}
        queue = deque([(start, [])])
        while queue:
            tile, route = queue.popleft()
            opens = graph.get(tile)
            if opens is None:
                return route
            for d in opens:
                dx, dy = DELTA[d]
                nxt = (tile[0] + dx, tile[1] + dy)
                if nxt not in graph:
                    return route + [d]
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, route + [d]))
        return None

    def route_to(self, parity, start, goal):
        graph = self.graph(parity)
        seen = {start}
        queue = deque([(start, [])])
        while queue:
            tile, route = queue.popleft()
            if tile == goal:
                return route
            for d in sorted(graph.get(tile, ())):
                dx, dy = DELTA[d]
                nxt = (tile[0] + dx, tile[1] + dy)
                if nxt in seen or nxt not in graph:
                    continue
                seen.add(nxt)
                queue.append((nxt, route + [d]))
        return None


def state(p):
    return p.ask(cmd="emerald_dev_state")


def here(p):
    return tuple(state(p).get("pos") or ())


def opens_of(p):
    info = (state(p).get("puzzle") or {}).get("open") or {}
    return [d for d in "nesw" if info.get(d)]


def parity(p):
    return (state(p).get("puzzle") or {}).get("changes", 0) & 1


def free(p):
    d = state(p)
    return not d.get("controls_locked") and not d.get("message_box")


def settle(p, log, tag):
    """Press through a trainer's challenge or a script, boosting while fighting."""
    presses = 0
    while presses < 150:
        d = state(p)
        scene = p.status().get("scene")
        if scene != "battle" and free(p):
            return
        if scene == "battle":
            party.boost(p)
        p.action("confirm")
        p.frames(45)
        p.flush_speech(f"{tag}-{presses}")
        presses += 1
    log.append(f"[{tag}] settle hit its press limit")


def step(p, direction, log):
    before = here(p)
    p.step(direction)
    p.frames(6)
    p.flush_speech(direction)
    if not free(p):
        settle(p, log, direction)
    after = here(p)
    return after if after != before else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", default="party-fight")
    ap.add_argument("--report", default="mauville-plates")
    args = ap.parse_args()

    p = Pad(os.path.join(REPORTS, f"{args.report}.txt"))
    log = []

    def note(text):
        print(text, flush=True)
        log.append(text)

    ck = Checkpoints(conn=p)
    ck.load(args.checkpoint)
    p.frames(30)
    settle(p, log, "load")
    p.ask(cmd="emerald_dev_warp", map_group=10, map_num=0, x=4, y=19, facing="north")
    for _ in range(120):
        if (state(p).get("warp") or {}).get("done"):
            break
        p.frames(5)
    settle(p, log, "warp")
    if here(p) in EXIT_TILES:            # the warp lands us on the door tile
        step(p, "up", log)
    note(f"in the gym at {here(p)}, beams {parity(p)}")

    plan = Plan()
    pressed = {}
    moves = 0
    last_route = None
    while moves < MOVE_LIMIT:
        tile = here(p)
        par = parity(p)
        plan.observe(par, tile, opens_of(p))
        if tile in PLATES and PLATES[tile] not in pressed:
            pressed[PLATES[tile]] = tile
            note(f"pressed {PLATES[tile]} at {tile} (beams {par})")
            if len(pressed) == len(PLATES):
                note("all four plates pressed")
                break

        targets = [t for t in PLATES if t not in pressed.values()]
        route = None
        for goal in sorted(targets, key=lambda g: abs(g[0] - tile[0]) + abs(g[1] - tile[1])):
            route = plan.route_to(par, tile, goal)
            if route is not None:
                goal_name = PLATES[goal]
                break
        if route is None:
            route = plan.frontier(par, tile)
            goal_name = "unexplored ground"
        if not route:
            note(f"nothing reachable from {tile} with beams {par}; stopping")
            break

        map_now = tuple((state(p).get("puzzle") or {}).get("map") or ())
        if map_now != (10, 0):
            note(f"left the gym for map {map_now}; going back")
            p.ask(cmd="emerald_dev_warp", map_group=10, map_num=0, x=4, y=17, facing="north")
            for _ in range(120):
                if (state(p).get("warp") or {}).get("done"):
                    break
                p.frames(5)
            settle(p, log, "rewarp")
            plan = Plan()
            continue
        ahead = (tile[0] + DELTA[route[0]][0], tile[1] + DELTA[route[0]][1])
        if ahead in EXIT_TILES:
            plan.graph(par)[tile].discard(route[0])
            continue

        if route != last_route:
            note(f"from {tile} (beams {par}) toward {goal_name}: {''.join(route)}")
        last_route = route

        moved = step(p, DIR[route[0]], log)
        moves += 1
        if moved is None:
            note(f"{tile} {DIR[route[0]]} blocked, replanning")
            plan.graph(par)[tile].discard(route[0])
            continue
        if moved in PLATES and PLATES[moved] not in pressed:
            pressed[PLATES[moved]] = moved
            note(f"stepped on {PLATES[moved]} at {moved}")
            if len(pressed) == len(PLATES):
                note(f"all four plates pressed after {moves} moves")
                break

    for name, tile in PLATES.items():
        note(f"{name} {tile}: {'pressed' if name in pressed else 'NOT pressed'}")
    note(f"{moves} moves, ended at {here(p)}")

    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, f"{args.report}.md"), "w", encoding="utf-8") as fh:
        fh.write("# Mauville plates\n\n")
        for line in log:
            fh.write(f"- {line}\n")
        fh.write("\n## What the mod said\n\n")
        for line in p.lines:
            fh.write(f"    {line}\n")


if __name__ == "__main__":
    main()

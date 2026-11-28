"""One planner for the gyms whose floors are not plain: levels, warp panels, ice.

The three gyms left each break a different assumption of a plain BFS:

* Fortree is built from two floor heights. The engine refuses a step when the
  target's block elevation differs from the tile the player stands on, except
  across transition tiles (14 multi-level, 15 transition), and elevation 0 is
  ordinary ground that connects to either level.
* Mossdeep is warp panels: stepping on a panel moves you to the tile the map's
  own warp list pairs it with.
* Sootopolis is ice: one input slides you in that direction until something
  stops you (and thin ice breaks behind you).

So each of those becomes an edge in the graph, the behaviours come from the
running map (live_behavior.live_behaviors), and the executor re-reads the map
after anything that teleports or slides.

    python3 artifacts/playtest/gym_graph.py --group 12 --num 1 --layout \
        FortreeCity_Gym_Layout --start 15 23 --goal 15 3 --leader WINONA \
        --report artifacts/playtest/reports/fortree-walk.txt
"""

import argparse
import os
import struct
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402
from gym_walker import door_pairs, here, people, read  # noqa: E402
from live_behavior import live_behaviors  # noqa: E402

DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
MB_JUMP_SOUTH = 0x3B
MB_MOSSdeep_WARP = 0x0E
MB_ICE = 0x20
MB_THIN_ICE = 0x26
MB_CRACKED_ICE = 0x27
MB_SLIDE = {0x44: "east", 0x45: "west", 0x46: "north", 0x47: "south"}


class Log:
    def __init__(self, fh):
        self.fh = fh

    def append(self, text):
        print(text, flush=True)
        self.fh.write(text + "\n")
        self.fh.flush()


def tiles_of(p, width, height):
    """(walkable, elevation) per tile from the engine's padded backup buffer."""
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


def level_ok(tiles, a, b):
    """The engine's elevation rule, with 0 as ordinary ground."""
    walk, elev = tiles[b]
    if not walk:
        return False
    here_elev = tiles[a][1]
    if elev == here_elev or elev in (14, 15) or here_elev in (14, 15):
        return True
    return elev == 0 or here_elev == 0


def slide_from(tiles, beh, tile, d):
    """Where one input in direction d ends up, following ice and slide tiles."""
    x, y = tile
    dx, dy = DIRS[d]
    cur = tile
    for _ in range(60):
        nxt = (cur[0] + dx, cur[1] + dy)
        walk, _e = tiles.get(nxt, (False, 0))
        if not walk:
            break
        cur = nxt
        b = beh.get(cur, 0)
        if b in MB_SLIDE:
            d = MB_SLIDE[b]
            dx, dy = DIRS[d]
        # ice keeps sliding; anything else is where you stop
        if not (b in MB_SLIDE or b in (MB_ICE, MB_THIN_ICE, MB_CRACKED_ICE)):
            break
    return cur


def build_edges(tiles, beh, width, height, warps):
    """Adjacency: (from, dir) -> to, plus which dirs are warps or slides."""
    edges = {}
    for y in range(height):
        for x in range(width):
            frm = (x, y)
            if frm not in tiles or not tiles[frm][0]:
                continue
            for name, (dx, dy) in DIRS.items():
                nxt = (x + dx, y + dy)
                if not (0 <= nxt[0] < width and 0 <= nxt[1] < height):
                    continue
                if beh.get(frm) in MB_SLIDE or beh.get(frm) in (MB_ICE, MB_THIN_ICE):
                    # standing on a sliding tile: one input goes all the way
                    land = slide_from(tiles, beh, frm, name)
                    if land != frm:
                        edges[(frm, name)] = (land, "slide")
                    continue
                if nxt in warps and tiles.get(nxt, (False,))[0]:
                    edges[(frm, name)] = (warps[nxt], "warp")
                    continue
                if level_ok(tiles, frm, nxt):
                    edges[(frm, name)] = (nxt, "walk")
                elif beh.get(nxt) == MB_JUMP_SOUTH and name == "south":
                    land = (x, y + 2)
                    if level_ok(tiles, frm, land):
                        edges[(frm, name)] = (land, "jump")
    return edges


def plan(edges, start, goal, avoid=frozenset(), refused=frozenset(), forbid=True):
    """Dijkstra: an edge the game has refused is expensive, not forbidden.

    Forbidding them dead-ends the search on maps whose real rule we have not
    modelled; making them expensive routes around them when there is a choice
    and still lets the walker try the only way through when there is not.
    """
    import heapq
    dist = {start: 0}
    prev = {start: None}
    heap = [(0, start)]
    while heap:
        cost, cur = heapq.heappop(heap)
        if cur == goal:
            break
        if cost > dist.get(cur, 1 << 30):
            continue
        for name in DIRS:
            step = edges.get((cur, name))
            if not step:
                continue
            nxt, kind = step
            if nxt in prev or nxt in avoid:
                continue
            if forbid and (cur, name) in refused:
                continue
            w = 1
            if cost + w < dist.get(nxt, 1 << 30):
                dist[nxt] = cost + w
                prev[nxt] = (cur, name, kind)
                heapq.heappush(heap, (cost + w, nxt))
    if goal not in prev:
        return None
    out, cur = [], goal
    while prev[cur] is not None:
        cur, name, kind = prev[cur]
        out.append((name, kind))
    return list(reversed(out))


def drain(p, fh, tag):
    for i in range(30):
        st = p.ask(cmd="emerald_dev_state")
        if not st.get("message_box") and not st.get("controls_locked"):
            return
        p.confirm(40)
        p.flush_speech(tag + "-drain%d" % i)
        if p.status().get("scene") == "battle":
            return



def settled(p, tries=8):
    """The mod's position read lags a jump or warp; wait for two equal reads."""
    last = None
    for _ in range(tries):
        p.frames(18)
        h = here(p)
        if h == last:
            return h
        last = h
    return last


def press(p, d, log, fh, tag):
    """One edge attempt, as a real held-key walk.

    A single frame of input is dropped often enough to look like a wall, so the
    key is held; if something is still ahead, that is a person to talk to or a
    genuine wall.
    """
    before = settled(p)
    for _ in range(2):
        p.walk(d, 1)
        p.frames(26)
        if p.status().get("scene") == "battle":
            fight_if_needed(p, tag + "-fight", log)
            drain(p, fh, tag + "-fight")
            return settled(p), "battle"
        if settled(p) != before:
            p.flush_speech(tag + "-" + d)
            return settled(p), "moved"
    look = p.nav().get("look") or {}
    if look.get("kind") == "object":
        p.confirm(45)
        p.flush_speech(tag + "-talk")
        if p.status().get("scene") == "battle":
            fight_if_needed(p, tag + "-talkfight", log)
            drain(p, fh, tag + "-talkfight")
            return settled(p), "battle"
        p.confirm(45)
        p.frames(40)
        drain(p, fh, tag + "-talkdone")
        if settled(p) != before:
            return settled(p), "moved"
    return before, "blocked"


def explore(p, goal, log, fh, max_steps=500):
    """Depth-first over the real map, the game deciding what is an edge.

    Every accepted input is a walk, jump, slide or warp edge; a refused one is
    a wall. Backtracking is a real walk, so a dead end costs exactly the steps
    it took to reach.
    """
    tried = {}
    path = []
    visited = {here(p)}
    log.append("explore from %s to %s" % (here(p), goal))
    for step in range(max_steps):
        t = here(p)
        if t == goal:
            log.append("reached %s after %d steps" % (goal, step))
            return True
        tried.setdefault(t, set())
        order = sorted(DIRS, key=lambda d: (t[0] + DIRS[d][0] - goal[0]) ** 2 +
                       (t[1] + DIRS[d][1] - goal[1]) ** 2)
        moved = False
        for d in order:
            if d in tried[t]:
                continue
            if (t[0] + DIRS[d][0], t[1] + DIRS[d][1]) in visited and \
                    (t[0] + DIRS[d][0], t[1] + DIRS[d][1]) != goal:
                tried[t].add(d)
                continue
            tried[t].add(d)
            pos, how = press(p, d, log, fh, "e%03d-%s" % (step, d))
            pos = settled(p)
            if pos != t:
                log.append("edge %s %s %s %s" % (t, d, how, pos))
                if how == "battle":
                    log.append("battle took us to %s" % (pos,))
                path.append((t, d))
                visited.add(pos)
                moved = True
                break
        if moved:
            continue
        log.append("dead end at %s, backtracking" % (t,))
        while path:
            prev, d = path.pop()
            pos, how = press(p, OPPOSITE[d], log, fh, "b%03d" % step)
            pos = settled(p)
            log.append("back %s %s -> %s" % (d, how, pos))
            if pos == prev:
                break
        else:
            log.append("no way back and not at the goal")
            return False
    log.append("gave up at %s" % (here(p),))
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", type=int, required=True)
    ap.add_argument("--num", type=int, required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--start", type=int, nargs=2, required=True)
    ap.add_argument("--goal", type=int, nargs=2, required=True)
    ap.add_argument("--leader", required=True)
    ap.add_argument("--talk", default="north")
    ap.add_argument("--checkpoint", default="petalburg-cleared")
    ap.add_argument("--report", required=True)
    ap.add_argument("--explore", action="store_true")
    args = ap.parse_args()

    p = Pad(transcript=args.report)
    fh = open(args.report + ".log", "w")
    log = Log(fh)

    if args.checkpoint:
        class S:
            def __init__(self, pad):
                self.pad = pad

            def ask(self, **kw):
                return self.pad.ask(**kw)
        Checkpoints(conn=S(p)).load(args.checkpoint)
        drain(p, fh, "load")
    p.force_map(args.group, args.num, args.start[0], args.start[1])
    p.frames(90)
    drain(p, fh, "enter")
    log.append("start %s map %s" % (here(p), tuple(p.map())))

    goal = tuple(args.goal)
    if args.explore:
        if explore(p, goal, log, fh):
            pass
        fh.flush()
    refused = set()        # (tile, dir) the game refused, learned
    anchors = []           # tiles where the player object had to be respawned
    for attempt in range(40 if not args.explore else 0):
        if here(p) == goal:
            break
        tiles = tiles_of(p, args.width, args.height)
        beh, _meta = live_behaviors(p, args.width, args.height)
        warps = door_pairs(args.group, args.num)
        edges = build_edges(tiles, beh, args.width, args.height, warps)
        steps = plan(edges, here(p), goal, frozenset(people(p) - {goal}), refused, True)
        if steps is None:
            steps = plan(edges, here(p), goal, frozenset(people(p) - {goal}), refused, False)
        if steps is None:
            log.append("no route from %s (refused %d)" % (here(p), len(refused)))
            break
        log.append("attempt %d: %d steps" % (attempt, len(steps)))
        for i, (d, kind) in enumerate(steps):
            before = settled(p)
            moved = False
            for tryi in range(3):
                if kind == "walk":
                    p.walk(d, 1)
                    p.frames(26)
                else:
                    p.ask(cmd="emerald_a11y_action", action=d)
                    p.frames(72)
                p.flush_speech("%03d-%s-%s-t%d" % (i, d, kind, tryi))
                if p.status().get("scene") == "battle":
                    fight_if_needed(p, "fight%03d" % i, log)
                    p.flush_speech("fight%03d" % i)
                    drain(p, fh, "fight%03d" % i)
                    moved = True
                    break
                if settled(p) != before:
                    moved = True
                    break
            after = settled(p)
            if moved and after != before:
                log.append("%03d %s %s %s -> %s" % (i, d, kind, before, after))
                if kind != "walk":
                    p.frames(40)
                    drain(p, fh, "after%03d" % i)
            elif after == before:
                if (before[0] + DIRS[d][0], before[1] + DIRS[d][1]) in people(p):
                    p.confirm(45)
                    p.flush_speech("poke%03d" % i)
                    if p.status().get("scene") == "battle":
                        fight_if_needed(p, "pokefight%03d" % i, log)
                        drain(p, fh, "pokefight%03d" % i)
                else:
                    # The map says the tile is open but the game will not take
                    # the step: the player object is left in a stalled state by
                    # a turn taken mid-transition, and only a map load respawns
                    # it. Re-anchor on the tile we already stand on - the same
                    # dev warp the audit allows the tester's hands - and retry.
                    tx, ty = before[0] + DIRS[d][0], before[1] + DIRS[d][1]
                    if tiles.get((tx, ty), (False,))[0]:
                        log.append("%03d %s stalled at %s, re-anchoring" % (i, d, before))
                        p.force_map(args.group, args.num, before[0], before[1])
                        p.frames(110)
                        drain(p, fh, "anchor%03d" % i)
                        anchors.append(before)
                        p.walk(d, 1)
                        p.frames(60)
                        if settled(p) != before:
                            moved = True
                            log.append("%03d %s anchored %s -> %s" % (i, d, before, here(p)))
                    if not moved:
                        refused.add((before, d))
                        log.append("%03d %s refused at %s" % (i, d, before))
            if not moved:
                break
        log.append("after attempt %d: %s" % (attempt, here(p)))

    log.append("re-anchors: %d %s" % (len(anchors), anchors[:12]))
    if here(p) == goal:
        p.action(args.talk, 12)
        for i in range(4):
            p.confirm(45)
            p.flush_speech("leader%d" % i)
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
        for i in range(30):
            p.confirm(45)
            p.flush_speech("prize%d" % i)
        log.append("final %s scene %s" % (here(p), p.status().get("scene")))
    else:
        log.append("not at the goal: %s" % (here(p),))
    fh.close()


if __name__ == "__main__":
    main()

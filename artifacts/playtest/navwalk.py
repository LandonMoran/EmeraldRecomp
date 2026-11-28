"""Grid-learning walker for the playtest pad.

Why this exists
---------------
Three release items were recorded as blocked by the *walker*, not the game: the
Mart counter (a sign at (37,23) bounced the greedy walk between (37,24) and
(37,25)), Route 101's north exit (the opening is not the tile the planner
guessed), and grass (needs to wander until an encounter). A straight-line walk
cannot do any of those, and a BFS over tiles it has never stood on is a guess.

This module learns the map instead: every step either records a passable edge or
a wall, BFS runs over the edges it has proved, and when the target is not yet
reachable it walks to the proved tile nearest the target and probes the unknown
neighbour that points at it. Nothing is assumed about collision.

Same input path as the gym runs: one held pad direction per tile
(``pad.step``), position read until two consecutive reads agree
(``settled``).
"""

import sys

sys.path.insert(0, "artifacts/playtest")

DELTA = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}


def settled(p, tries=6, frames=14):
    """Position read that only returns once two consecutive reads agree."""
    last = None
    for _ in range(tries):
        o = p.obj()
        pos = (o["x"], o["y"])
        if pos == last:
            return pos
        last = pos
        p.frames(frames)
    return last


class Explorer:
    def __init__(self, p, tag="nav"):
        self.p = p
        self.tag = tag
        self.edges = {}          # (x, y) -> set(direction) proved passable
        self.walls = set()       # (x, y, direction) proved blocked
        self.seen = set()

    # -- bookkeeping -----------------------------------------------------
    def _pos(self):
        return settled(self.p)

    def _known_free(self, x, y):
        return self.edges.get((x, y), set())

    def _promising(self, x, y, direction):
        return (x, y, direction) not in self.walls

    # -- one measured step ----------------------------------------------
    def _battle_guard(self, tag):
        """A trainer sight line or a wild encounter owns the pad; clear it."""
        if self.p.scene() == "overworld":
            return False
        for i in range(60):
            if self.p.scene() == "overworld":
                return True
            self.p.confirm(80)
            self.p.flush_speech(f"{tag}battle{i}")
        return True

    def _pad_guard(self, tag):
        """A dialogue box owns the pad after a map load; press A until it is gone."""
        if self.p.scene() == "overworld":
            d = self.p.ask(cmd="emerald_dev_state")
            if not d.get("controls_locked") and not d.get("message_box"):
                return False
        for i in range(14):
            self.p.confirm(70)
            self.p.flush_speech(f"{tag}pad{i}")
            d = self.p.ask(cmd="emerald_dev_state")
            if (self.p.scene() == "overworld" and not d.get("controls_locked")
                    and not d.get("message_box")):
                self.p.say(tag, "cleared a dialogue that owned the pad")
                return True
        return True

    def probe(self, direction, tag=None):
        """Try one step. Returns (moved, pos). Records the edge or the wall."""
        tag = tag or self.tag
        self._pad_guard(tag)
        start = self._pos()
        moved, _ = self.p.step(direction)
        self.p.flush_speech(tag)
        if self._battle_guard(tag):
            self.p.say(tag, "a battle interrupted the walk and was cleared")
        pos = self._pos()
        sx, sy = start
        if pos != start:
            self.edges.setdefault(start, set()).add(direction)
            self.edges.setdefault(pos, set()).add(OPPOSITE[direction])
            self.p.say(tag, f"({sx},{sy}) -{direction}-> ({pos[0]},{pos[1]})")
            return True, pos
        self.walls.add((sx, sy, direction))
        self.p.say(tag, f"({sx},{sy}) {direction} blocked")
        return False, pos

    # -- path over proved edges only -------------------------------------
    def path(self, start, target):
        if start == target:
            return []
        frontier = [(start, [])]
        seen = {start}
        while frontier:
            (x, y), trail = frontier.pop(0)
            for d in self._known_free(x, y):
                nx, ny = x + DELTA[d][0], y + DELTA[d][1]
                if (nx, ny) in seen:
                    continue
                seen.add((nx, ny))
                step = trail + [d]
                if (nx, ny) == target:
                    return step
                frontier.append(((nx, ny), step))
        return None

    def distance_hint(self, target):
        tx, ty = target

        def score(tile):
            return abs(tile[0] - tx) + abs(tile[1] - ty)
        return score

    def nearest_proved(self, target):
        score = self.distance_hint(target)
        return min(self.edges.keys() or [self._pos()], key=score)

    def _retreat(self, target):
        """Step to any proved neighbour that still has an unknown side."""
        pos = self._pos()
        for d in sorted(self._known_free(pos[0], pos[1])):
            nx, ny = pos[0] + DELTA[d][0], pos[1] + DELTA[d][1]
            if any(self._promising(nx, ny, nd) for nd in DELTA):
                self.probe(d, f"{self.tag}retreat")
                return self._pos()
        return pos

    def goto(self, tx, ty, limit=200, stop_on_battle=True):
        """Walk to a tile, learning the grid as it goes."""
        target = (tx, ty)
        pos = self._pos()
        for _ in range(limit):
            if stop_on_battle and self.p.scene() != "overworld":
                self.p.say(self.tag, f"battle stopped the walk at ({pos[0]},{pos[1]})")
                return pos
            if pos == target:
                self.p.say(self.tag, f"arrived ({pos[0]},{pos[1]})")
                return pos
            trail = self.path(pos, target)
            if trail:
                moved, pos = self.probe(trail[0])
                continue
            # nothing proved reaches the target: extend the map toward it
            base = self.nearest_proved(target)
            if base != pos:
                trail = self.path(pos, base)
                if trail:
                    moved, pos = self.probe(trail[0])
                    continue
                self.p.say(self.tag, f"cannot reach the frontier from ({pos[0]},{pos[1]})")
                return pos
            # probe the unknown neighbour with the best aim at the target
            score = self.distance_hint(target)
            options = []
            for d, (dx, dy) in DELTA.items():
                nxt = (base[0] + dx, base[1] + dy)
                if self._promising(base[0], base[1], d):
                    options.append((score(nxt), d))
            if not options:
                # every neighbour here is proved: drop back to the next best
                # frontier tile instead of calling the target unreachable
                self.p.say(self.tag, f"({base[0]},{base[1]}) is fully known")
                if base == pos:
                    pos = self._retreat(target)
                continue
            options.sort()
            moved, pos = self.probe(options[0][1], f"{self.tag}probe")
        self.p.say(self.tag, f"limit at ({pos[0]},{pos[1]}) target {target}")
        return pos


def boundary_scan(p, tag="scan", y_hint=None):
    """Walk a row and report every tile whose neighbour leaves the map.

    A map edge in Emerald is a connection, so stepping into it changes map
    group/num instead of position; the walker reports which tile did it.
    """
    start = settled(p)
    mg, mn = p.map()
    p.say(tag, f"scan start ({start[0]},{start[1]}) map ({mg},{mn})")
    exp = Explorer(p, tag)
    found = []
    row = y_hint if y_hint is not None else start[1]
    for x in range(start[0] - 12, start[0] + 13):
        pos = exp.goto(x, row, limit=60)
        if p.map() != (mg, mn):
            found.append((pos, p.map()))
            p.say(tag, f"crossed at {pos} into {p.map()}")
            break
    p.say(tag, f"boundary scan found {found}")
    return found


def find_door(p, radius=14, tag="doorhunt"):
    """Breadth-first walk of everything reachable; report a tile with a door
    in front, using the mod's own bumper as ground truth (no coordinate
    arithmetic between warp tables and object events)."""
    exp = Explorer(p, tag)
    start = settled(p)
    queue = [start]
    seen = {start}
    while queue:
        tile = queue.pop(0)
        if p.map() != (0, 6) and p.map() != (0, 10):
            p.say(tag, f"left the street at {tile} into {p.map()}")
            return tile, p.map()
        if tile != settled(p):
            trail = exp.path(settled(p), tile)
            if not trail:
                continue
            for d in trail:
                exp.probe(d, f"{tag}back")
        look = p.nav().get("look") or {}
        if look.get("kind") == "door":
            p.say(tag, f"door in front of {tile} facing {look.get('dir')} at {look.get('x')},{look.get('y')}")
            return tile, look
        for d in DELTA:
            moved, pos = exp.probe(d, f"{tag}{tile[0]}_{tile[1]}{d[0]}")
            if moved:
                if pos not in seen and abs(pos[0] - start[0]) <= radius and abs(pos[1] - start[1]) <= radius:
                    seen.add(pos)
                    queue.append(pos)
                trail = exp.path(pos, tile)
                if trail:
                    for back in trail:
                        exp.probe(back, f"{tag}ret")
    return None, None

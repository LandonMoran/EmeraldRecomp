"""Offline collision grids from the imported layout data.

Why this exists
---------------
The playtest walker kept failing on city navigation because it learned walls by
bumping into them, and the object-event coordinate space (map tile + 7) differs
from the warp table's (map tile). Both facts are in the game data, so read them
instead of discovering them one bump at a time:

* a layout's ``map.bin`` is width*height little-endian u16 blocks, row-major,
  with no header (the file's first block is the first tile);
* each block is ``metatileId | collision << 10 | elevation << 12``;
* collision 0 is passable, anything else blocks.

Object-event coordinates carry a +7 border offset, so the map tile is
``(object_x - 7, object_y - 7)``.
"""

import json
import struct
from collections import deque

ROOT = "third_party/pokeemerald"
LAYOUTS = json.load(open(f"{ROOT}/data/layouts/layouts.json"))["layouts"]
BY_NAME = {l["name"]: l for l in LAYOUTS}
BY_ID = {l["id"]: l for l in LAYOUTS}

OFFSET = 7  # object-event coords -> map tiles
DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}


class Grid:
    def __init__(self, layout_name):
        lay = BY_NAME.get(layout_name) or BY_ID.get(layout_name)
        if lay is None:
            raise KeyError(layout_name)
        self.w, self.h = lay["width"], lay["height"]
        raw = open(f"{ROOT}/{lay['blockdata_filepath']}", "rb").read()
        expect = self.w * self.h * 2
        if len(raw) != expect:
            raise ValueError(
                f"{layout_name}: map.bin is {len(raw)} bytes, {self.w}x{self.h} "
                f"blocks need {expect}")
        self.blocks = list(struct.unpack("<%dH" % (self.w * self.h), raw))

    def block(self, x, y):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return None
        return self.blocks[y * self.w + x]

    def passable(self, x, y):
        b = self.block(x, y)
        return b is not None and ((b >> 10) & 3) == 0

    def elevation(self, x, y):
        b = self.block(x, y)
        return None if b is None else (b >> 12) & 0xF

    def metatile(self, x, y):
        b = self.block(x, y)
        return None if b is None else b & 0x3FF

    def ascii(self, x0, y0, x1, y1, marks=None):
        marks = marks or {}
        out = []
        for y in range(y0, y1 + 1):
            row = []
            for x in range(x0, x1 + 1):
                if (x, y) in marks:
                    row.append(marks[(x, y)])
                elif not self.passable(x, y):
                    row.append("#")
                else:
                    row.append(".")
            out.append(f"{y:3d} " + "".join(row))
        header = "    " + "".join(str(x // 10 % 10) for x in range(x0, x1 + 1))
        return "\n".join([header] + out)

    def path(self, start, goal, limit=4000, blocked=()):
        blocked = set(blocked)
        if not self.passable(*start):
            # allow the tile the player is standing on even if the grid disagrees
            pass
        q = deque([start])
        prev = {start: None}
        while q and len(prev) < limit:
            cur = q.popleft()
            if cur == goal:
                break
            for d, (dx, dy) in DIRS.items():
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt in prev:
                    continue
                if nxt in blocked:
                    continue
                if not self.passable(*nxt) and nxt != goal:
                    continue
                prev[nxt] = (cur, d)
                q.append(nxt)
        if goal not in prev:
            return None
        steps = []
        cur = goal
        while prev[cur]:
            cur, d = prev[cur]
            steps.append(d)
        return list(reversed(steps))


def obj_to_map(x, y):
    return (x - OFFSET, y - OFFSET)


def map_to_obj(x, y):
    return (x + OFFSET, y + OFFSET)


if __name__ == "__main__":
    import sys
    g = Grid(sys.argv[1] if len(sys.argv) > 1 else "MossdeepCity_Layout")
    print(g.ascii(0, 0, min(g.w - 1, 60), min(g.h - 1, 30)))


def npc_tiles(map_name):
    """Tiles occupied by object events on a map, as (x, y) map tiles.

    The collision grid says a tile is walkable even when a trainer is standing
    on it, so a BFS path can run straight through a person and the walker then
    stalls against them. Read the people from the map's object list instead.
    Those coordinates are already map tiles (the +7 engine offset applies only
    to the live player read), so they are used as they are.
    """
    import json as _json
    try:
        d = _json.load(open(f"{ROOT}/data/maps/{map_name}/map.json"))
    except FileNotFoundError:
        return set()
    return {(o["x"], o["y"]) for o in d.get("object_events", [])}

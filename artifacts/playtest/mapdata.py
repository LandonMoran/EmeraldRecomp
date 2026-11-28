"""Read a map layout straight out of the decomp data: collision + tall grass.

Used by the playtest harness to plan a walk to the nearest patch of tall grass
instead of bumping into hedges. Nothing here ships with the mod.
"""

import json
import os
import struct
from collections import deque

ROOT = "third_party/pokeemerald"
LAYOUTS = os.path.join(ROOT, "data/layouts/layouts.json")

MB_TALL_GRASS = 0x02
MB_LONG_GRASS = 0x03
GRASS_BEHAVIORS = (MB_TALL_GRASS, MB_LONG_GRASS)


def _attrs(tileset, secondary):
    """Tileset directories are snake_case, but the layout JSON names are not."""
    sub = "secondary" if secondary else "primary"
    snake = "".join("_" + c.lower() if c.isupper() else c for c in tileset).lstrip("_")
    for name in (snake, tileset):
        path = os.path.join(ROOT, "data/tilesets", sub, name, "metatile_attributes.bin")
        if os.path.exists(path):
            with open(path, "rb") as fh:
                return fh.read()
    raise FileNotFoundError(tileset)


class Layout:
    def __init__(self, name):
        with open(LAYOUTS) as fh:
            data = json.load(fh)["layouts"]
        lay = next(x for x in data if x["name"] == name)
        self.name = name
        self.width = lay["width"]
        self.height = lay["height"]
        with open(os.path.join(ROOT, lay["blockdata_filepath"]), "rb") as fh:
            self.blocks = fh.read()
        self.primary = _attrs(lay["primary_tileset"].replace("gTileset_", ""), False)
        self.secondary = _attrs(lay["secondary_tileset"].replace("gTileset_", ""), True)

    def block(self, x, y):
        if not (0 <= x < self.width and 0 <= y < self.height):
            return None
        off = 2 * (x + self.width * y)
        return struct.unpack("<H", self.blocks[off:off + 2])[0]

    def walkable(self, x, y):
        b = self.block(x, y)
        if b is None:
            return False
        if (b >> 10) & 3:
            return False
        return True

    def behavior(self, x, y):
        b = self.block(x, y)
        if b is None:
            return -1
        tid = b & 0x3FF
        if tid < 0x200:
            table, idx = self.primary, tid
        else:
            table, idx = self.secondary, tid - 0x200
        off = 2 * idx
        if off + 2 > len(table):
            return -1
        return struct.unpack("<H", table[off:off + 2])[0] & 0xFF

    def grass(self, x, y):
        return self.behavior(x, y) in GRASS_BEHAVIORS

    def grass_tiles(self):
        return [(x, y) for y in range(self.height) for x in range(self.width)
                if self.walkable(x, y) and self.grass(x, y)]

    def path(self, start, goals, blocked=frozenset()):
        """BFS over walkable tiles. Returns a list of 'up'/'down'/'left'/'right'.

        `blocked` holds tiles the walk already bounced off (a person standing
        in the way, a counter): static collision data cannot know about them.
        """
        goals = set(goals)
        if not goals:
            return []
        prev = {start: None}
        q = deque([start])
        hit = None
        while q:
            cur = q.popleft()
            if cur in goals:
                hit = cur
                break
            x, y = cur
            for dx, dy, name in ((0, -1, "up"), (0, 1, "down"), (-1, 0, "left"), (1, 0, "right")):
                nxt = (x + dx, y + dy)
                if nxt in prev or nxt in blocked or not self.walkable(*nxt):
                    continue
                prev[nxt] = (cur, name)
                q.append(nxt)
        if hit is None:
            return []
        steps = []
        cur = hit
        while prev[cur] is not None:
            cur, name = prev[cur]
            steps.append(name)
        steps.reverse()
        return steps


ROUTE101 = "Route101_Layout"

if __name__ == "__main__":
    lay = Layout(ROUTE101)
    g = lay.grass_tiles()
    print(f"{lay.name}: {lay.width}x{lay.height}, {len(g)} tall-grass tiles")
    print("first few:", g[:8])
    steps = lay.path((17, 25), g)
    print(f"path from (17,25) to grass: {len(steps)} steps -> {steps[:20]}")

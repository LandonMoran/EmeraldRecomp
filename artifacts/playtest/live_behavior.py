"""Metatile behaviours of the map that is actually loaded, straight from guest memory.

The ROM layout files say what a map looked like when it was built; the running
map can differ (door scripts swap metatiles, ice breaks, gates turn). This reads
the same chain the mod's puzzle layer reads:

    gMapHeader -> layout -> primary/secondary tileset -> attributes -> behaviour

    python3 artifacts/playtest/live_behavior.py --width 20 --height 25
"""

import argparse
import struct
import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad  # noqa: E402
from gym_walker import read  # noqa: E402

GMAPHEADER = 0x02037318


def live_behaviors(p, width, height):
    head = read(p, GMAPHEADER, 0x1C)
    layout = struct.unpack("<I", head[0:4])[0]
    # struct MapLayout: u32 width, u32 height, then border, map, primary, secondary
    w, h = struct.unpack("<II", read(p, layout, 8))
    blocks_ptr = struct.unpack("<I", read(p, layout + 12, 4))[0]
    primary = struct.unpack("<I", read(p, layout + 16, 4))[0]
    secondary = struct.unpack("<I", read(p, layout + 20, 4))[0]
    prim_attr = struct.unpack("<I", read(p, primary + 16, 4))[0]
    sec_attr = struct.unpack("<I", read(p, secondary + 16, 4))[0]
    blocks = read(p, blocks_ptr, 2 * w * h)
    blocks = struct.unpack("<%dH" % (w * h), blocks)
    prim = read(p, prim_attr, 0x200 * 2)
    sec = read(p, sec_attr, 0x200 * 2)
    out = {}
    meta = {}
    for y in range(height):
        for x in range(width):
            gy, gx = y, x
            if gx >= w or gy >= h:
                out[(x, y)] = -1
                continue
            b = blocks[gy * w + gx]
            tid = b & 0x3FF
            table = prim if tid < 0x200 else sec
            idx = tid if tid < 0x200 else tid - 0x200
            attr = table[idx * 2:idx * 2 + 2]
            out[(x, y)] = struct.unpack("<H", attr)[0] & 0xFF if len(attr) == 2 else -1
            meta[(x, y)] = (tid, (b >> 10) & 3, (b >> 12) & 0xF)
    return out, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    args = ap.parse_args()
    p = Pad()
    beh, meta = live_behaviors(p, args.width, args.height)
    for y in range(args.height):
        print("%2d " % y + " ".join("%02x" % (beh[(x, y)] & 0xFF) if beh[(x, y)] >= 0 else "--"
                                    for x in range(args.width)))


if __name__ == "__main__":
    main()

"""Simulate Mauville Gym's barrier function and search for a pressing order.

The puzzle is not a two-state parity flip. `MauvilleGymSetDefaultBarriers`
rewrites each beam id in the box x 0..8, y 5..16, and the rewrite is not
symmetric: H1/H2 beams are set to their _Off/_On id *without*
MAPGRID_IMPASSABLE in both directions (so they stay passable once touched),
while H3/H4 become impassable when they go Off -> On. So the layout after k
presses is f^k(map), and only k matters for the geometry.

`MapGridSetMetatileIdAt` keeps the elevation and takes id + collision from the
argument, which is why the IMPASSABLE flag matters:

    map[i] = (old & 0xF000) | (metatile & 0x0FFF)

Run:  python3 artifacts/playtest/gym_sim.py
"""

import collections
import struct

MAP = "third_party/pokeemerald/data/layouts/MauvilleCity_Gym/map.bin"
W, H = 10, 21

FLOOR = 0x21A
GH1 = (0x220, 0x230)   # (On, Off)
GH2 = (0x221, 0x231)
GH3 = (0x228, 0x238)
GH4 = (0x229, 0x239)
GV1 = 0x240
GV2 = 0x248
PB_ON, PB_OFF = 0x242, 0x243
PT_ON, PT_OFF = 0x250, 0x251
RH1 = (0x222, 0x232)
RH2 = (0x223, 0x233)
RH3 = (0x22A, 0x23A)
RH4 = (0x22B, 0x23B)
RV1 = 0x241
RV2 = 0x249
SWITCH_RAISED, SWITCH_PRESSED = 0x205, 0x206

IMPASSABLE = 0x0400
SWITCHES = [(0, 15, 1), (4, 12, 2), (3, 9, 3), (8, 9, 4)]   # x, y, state number


def load():
    raw = open(MAP, "rb").read()
    vals = list(struct.unpack("<%dH" % (len(raw) // 2), raw))
    return [vals[y * W:(y + 1) * W] for y in range(H)]


def metatile(v):
    return v & 0x03FF


def set_metatile(grid, x, y, new):
    grid[y][x] = (grid[y][x] & 0xF000) | (new & 0x0FFF)


def toggle(grid):
    """Apply MauvilleGymSetDefaultBarriers to a copy of the grid."""
    g = [row[:] for row in grid]
    for y in range(5 + 0, 17):
        for x in range(0, 9):
            mid = metatile(g[y][x])
            if mid == GH1[0]:
                set_metatile(g, x, y, GH1[1])
            elif mid == GH2[0]:
                set_metatile(g, x, y, GH2[1])
            elif mid == GH3[0]:
                set_metatile(g, x, y, GH3[1])
            elif mid == GH4[0]:
                set_metatile(g, x, y, GH4[1])
            elif mid == GH1[1]:
                set_metatile(g, x, y, GH1[0])
            elif mid == GH2[1]:
                set_metatile(g, x, y, GH2[0])
            elif mid == GH3[1]:
                set_metatile(g, x, y, GH3[0] | IMPASSABLE)
            elif mid == GH4[1]:
                set_metatile(g, x, y, GH4[0] | IMPASSABLE)
            elif mid == RH1[0]:
                set_metatile(g, x, y, RH1[1])
            elif mid == RH2[0]:
                set_metatile(g, x, y, RH2[1])
            elif mid == RH3[0]:
                set_metatile(g, x, y, RH3[1])
            elif mid == RH4[0]:
                set_metatile(g, x, y, RH4[1])
            elif mid == RH1[1]:
                set_metatile(g, x, y, RH1[0])
            elif mid == RH2[1]:
                set_metatile(g, x, y, RH2[0])
            elif mid == RH3[1]:
                set_metatile(g, x, y, RH3[0] | IMPASSABLE)
            elif mid == RH4[1]:
                set_metatile(g, x, y, RH4[0] | IMPASSABLE)
            elif mid == GV1:
                set_metatile(g, x, y, PB_ON | IMPASSABLE)
            elif mid == GV2:
                set_metatile(g, x, y, FLOOR)
            elif mid == RV1:
                set_metatile(g, x, y, PB_OFF | IMPASSABLE)
            elif mid == RV2:
                set_metatile(g, x, y, FLOOR)
            elif mid == PB_ON:
                set_metatile(g, x, y, GV1 | IMPASSABLE)
            elif mid == FLOOR:
                if y > 0 and metatile(g[y - 1][x]) == GV1:
                    set_metatile(g, x, y, GV2 | IMPASSABLE)
                else:
                    set_metatile(g, x, y, RV2 | IMPASSABLE)
            elif mid == PB_OFF:
                set_metatile(g, x, y, RV1 | IMPASSABLE)
            elif mid == PT_OFF:
                set_metatile(g, x, y, PT_ON | IMPASSABLE)
            elif mid == PT_ON:
                set_metatile(g, x, y, PT_OFF)
    return g


def passable(grid, x, y):
    if not (0 <= x < W and 0 <= y < H):
        return False
    return ((grid[y][x] >> 10) & 3) == 0


def show(grid, title, marks=()):
    print("=== %s" % title)
    for y in range(H):
        row = ""
        for x in range(W):
            if (x, y) in marks:
                row += "S"
            elif metatile(grid[y][x]) in (SWITCH_RAISED, SWITCH_PRESSED):
                row += "*"
            elif any(metatile(grid[y][x]) in pair for pair in
                     (GH1, GH2, GH3, GH4, RH1, RH2, RH3, RH4)) or \
                    metatile(grid[y][x]) in (GV1, GV2, RV1, RV2):
                row += "=" if passable(grid, x, y) else "#"
            elif passable(grid, x, y):
                row += "."
            else:
                row += "#"
        print("%2d %s" % (y, row))
    print()


def solve(grids, start=(4, 19)):
    """BFS over (x, y, k, state, mask): k selects the layout f^k(map)."""
    start_state = (start[0], start[1], 0, 0, 0)
    prev = {start_state: None}
    q = collections.deque([start_state])
    goal = None
    while q:
        x, y, k, state, mask = q.popleft()
        if mask == 0b1111:
            goal = (x, y, k, state, mask)
            break
        for dx, dy, d in ((0, -1, "up"), (1, 0, "right"), (0, 1, "down"), (-1, 0, "left")):
            nx, ny = x + dx, y + dy
            if not passable(grids[k], nx, ny):
                continue
            nk, nstate, nmask = k, state, mask
            for sx, sy, sn in SWITCHES:
                if (nx, ny) == (sx, sy) and state != sn:
                    nk = k + 1
                    nstate = sn
                    nmask = mask | (1 << (sn - 1))
            st = (nx, ny, nk, nstate, nmask)
            if st in prev:
                continue
            prev[st] = ((x, y, k, state, mask), d)
            q.append(st)
    if not goal:
        return None
    path = []
    st = goal
    while prev[st] is not None:
        pst, d = prev[st]
        path.append((d, st))
        st = pst
    path.reverse()
    return path


def main():
    base = load()
    grids = [base]
    for i in range(4):
        grids.append(toggle(grids[-1]))

    for k in range(5):
        marks = {(sx, sy) for sx, sy, _ in SWITCHES}
        show(grids[k], "after %d press(es)" % k, marks)

    path = solve(grids)
    if not path:
        print("NO SOLUTION FOUND")
        return
    print("solution (%d steps):" % len(path))
    print("  " + ", ".join(d for d, _ in path))
    presses = [(st[4].bit_count(), st) for d, st in path]
    for d, st in path:
        x, y, k, state, mask = st
        if mask and (mask != (path[path.index((d, st)) - 1][1][4] if path.index((d, st)) else 0)):
            print("  %s -> (%d,%d) presses=%d state=%d mask=%s"
                  % (d, x, y, k, state, format(mask, "04b")))


if __name__ == "__main__":
    main()

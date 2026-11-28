"""One session, start to finish: walk to the Mart, buy a ball, catch, read the bag.

Everything happens inside one `Pad`, so the transcript this writes is the whole
story without a gap: the greeting at the counter, the purchase lines, the ball
counts read straight out of the save, the battle menu that opens the ball
pocket, the capture, the Pokedex line, the party, and the final count.

Ball counts are decoded here rather than trusted from the shop's own line: the
bag stores a quantity XORed with the save's encryption key, so a raw word is not
the number carried. `count_ball()` applies the key and prints both the decoded
number and the bag announcer's sentence, which is what makes the "one lower"
claim checkable instead of rhetorical.
"""

import json
import struct
import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad                                    # noqa: E402
from bot import rd                                     # noqa: E402
from maps import Grid, obj_to_map, npc_tiles           # noqa: E402
import navwalk                                         # noqa: E402

TRANSCRIPT = "artifacts/playtest/reports/catch-final.txt"
BALL_OFFSET = 0x650        # SaveBlock1 bagPocket_PokeBalls
BALL_SLOTS = 16


def last(p, tag=""):
    p.flush_speech(tag)
    u = p.ask(cmd="emerald_a11y_log").get("utterances") or []
    return (u[-1]["text"] if u else "")


def curmap(p):
    return tuple(p.nav().get("map") or p.map())


def unlock(p, limit=30):
    for _ in range(limit):
        d = p.ask(cmd="emerald_dev_state")
        if not d.get("controls_locked") and not d.get("message_box"):
            return True
        p.confirm(50)
    return False


def ball_pocket(p):
    """[(slot, itemId, quantity)] with the save key applied."""
    sb1 = p.saveblock()
    sb2 = struct.unpack("<I", rd(p.s, "read_iwram", 0x03005D90, 4))[0]
    key = struct.unpack("<H", rd(p.s, "read_ewram", sb2 + 0xAC, 2))[0]
    raw = rd(p.s, "read_ewram", sb1 + BALL_OFFSET, BALL_SLOTS * 4)
    out = []
    for i in range(BALL_SLOTS):
        iid, qty = struct.unpack("<HH", raw[i * 4:(i + 1) * 4])
        if iid:
            out.append((i, iid, qty ^ key))
    return out, key


def say_count(p, tag):
    slots, key = ball_pocket(p)
    p.say(tag, f"poke-ball pocket decoded (key 0x{key:04x}): {slots if slots else 'empty'}")
    return slots


def walk(p, grid, target, tag, blocked=(), limit=240):
    """Step toward `target`, re-planning from the live tile after every step.

    Executing one BFS route blind desynchronises the moment a step is refused
    (a person in the way, a trainer battle, an elevation change): the walker
    keeps issuing the rest of the old route from the wrong square and wanders
    off the map. Re-reading the tile and re-planning each step makes the route
    self-correcting and lets a stuck walker say exactly where it is stuck.
    """
    e = navwalk.Explorer(p, tag)
    pos = obj_to_map(*navwalk.settled(p))
    p.say(tag, f"from ({pos[0]},{pos[1]}) to {target}")
    stuck = 0
    for _ in range(limit):
        if pos == target:
            return pos
        path = grid.path(pos, target, blocked=blocked)
        if not path:
            p.say(tag, f"no path from {pos} to {target}")
            return pos
        before = pos
        e.probe(path[0])
        p.frames(18)
        pos = obj_to_map(*navwalk.settled(p))
        if pos == before:
            stuck += 1
            if stuck >= 8:
                p.say(tag, f"stuck at {pos} heading for {target}")
                return pos
        else:
            stuck = 0
    p.say(tag, f"gave up at {pos} heading for {target}")
    return pos


def go_to_warp(p, grid, warps, want_map, tag, people=()):
    """Walk to the tile in front of a warp, then step onto it."""
    pos = obj_to_map(*navwalk.settled(p))
    best = None
    for wx, wy in warps:
        for d, (dx, dy) in (("north", (0, 1)), ("south", (0, -1)),
                            ("east", (-1, 0)), ("west", (1, 0))):
            ax, ay = wx + dx, wy + dy
            if not grid.passable(ax, ay):
                continue
            path = grid.path(pos, (ax, ay), blocked=people)
            if path is None:
                continue
            if best is None or len(path) < len(best[2]):
                best = ((ax, ay), d, path)
    if best is None:
        p.say(tag, f"no reachable warp to {want_map}")
        return False
    spot, direction, path = best
    p.say(tag, f"warp {want_map}: approach {spot} ({len(path)} steps), step {direction}")
    final = walk(p, grid, spot, tag, blocked=people)
    if final != spot:
        p.say(tag, f"did not reach the approach tile, at {final}")
        return False
    return step_onto(p, direction, want_map, tag)


def step_onto(p, direction, want_map, tag, tries=4):
    """Step onto a warp tile and wait for the map to change."""
    e = navwalk.Explorer(p, tag)
    for i in range(tries):
        before = curmap(p)
        e.probe(direction, f"{tag}{i}")
        for _ in range(10):
            p.frames(30)
            if curmap(p) == want_map:
                p.flush_speech(f"{tag}ok{i}")
                p.say(tag, f"warped {before} -> {curmap(p)} at {obj_to_map(*navwalk.settled(p))}")
                return True
            if curmap(p) != before:
                p.say(tag, f"landed on {curmap(p)} not {want_map}")
                return curmap(p) == want_map
    p.say(tag, f"no warp after {tries} tries, map {curmap(p)}")
    return False


def leave_shop(p, tag="leave"):
    for i in range(14):
        st = p.status()
        items = st.get("items") or []
        if st.get("scene") != "shop":
            break
        if "QUIT" in items:
            idx = items.index("QUIT")
            while p.status().get("selected") != idx:
                p.action("down", 20)
                p.frames(45)
            p.confirm(100)
        elif "CANCEL" in items:
            idx = items.index("CANCEL")
            while p.status().get("selected") != idx:
                p.action("down", 20)
                p.frames(45)
            p.confirm(90)
        else:
            p.action("cancel", 20)
            p.frames(70)
        p.flush_speech(f"{tag}{i}")
    unlock(p)
    p.say(tag, f"scene {p.status().get('scene')} after leaving the shop")


def buy_first_ball(p, tag="buy"):
    """Talk to the clerk and buy one of the first ball on the list."""
    unlock(p)
    g = Grid('LAYOUT_MART')
    walk(p, g, (3, 3), f"{tag}walk")
    p.ask(cmd="emerald_a11y_action", action="west")
    p.frames(24)
    p.confirm(90)
    p.say(f"{tag}greet", last(p, f"{tag}greet"))
    p.confirm(80)
    p.say(f"{tag}menu", last(p, f"{tag}menu"))
    items = p.status().get("items") or []
    if "BUY" in items:
        idx = items.index("BUY")
        while p.status().get("selected") != idx:
            p.action("down", 20)
            p.frames(45)
    p.confirm(90)
    p.say(f"{tag}stock", last(p, f"{tag}stock"))
    # quantity dialog: default 1, confirm it
    p.confirm(90)
    p.say(f"{tag}qty", last(p, f"{tag}qty"))
    p.confirm(80)
    p.say(f"{tag}total", last(p, f"{tag}total"))
    for i in range(3):
        p.confirm(80)
        p.say(f"{tag}line{i}", last(p, f"{tag}line{i}"))
    leave_shop(p, f"{tag}leave")


def flee(p, tag="flee"):
    for i in range(12):
        if p.scene() == "overworld":
            return True
        t = last(p, f"{tag}{i}")
        if "top left" in t:
            p.action("down", 20)
            p.frames(45)
        elif "bottom left" in t:
            p.action("right", 20)
            p.frames(45)
        elif "bottom right" in t:
            p.confirm(90)
        else:
            p.confirm(70)
    return p.scene() == "overworld"


def throw_from_bag(p, tag="throw"):
    """Turn one: right from Fight to Bag, open the ball pocket, throw."""
    for i in range(30):
        t = last(p, f"{tag}{i}")
        if "caught" in t.lower():
            return True
        if t.endswith("top left."):
            p.action("right", 20)
            p.frames(55)
            continue
        if "top right" in t:
            p.confirm(80)
            continue
        if t.upper().startswith("BAG"):
            p.confirm(80)
            continue
        if "BALL" in t.upper() and "of" in t:
            p.confirm(90)
            continue
        p.confirm(75)
    return False


def cross_edge(p, grid, edge, want_map, tag):
    """Walk to a passable tile on the map edge and step out of the map."""
    pos = obj_to_map(*navwalk.settled(p))
    axis, sign = edge
    candidates = []
    if axis == "x":
        col = grid.w - 1 if sign > 0 else 0
        for y in range(grid.h):
            if grid.passable(col, y):
                path = grid.path(pos, (col, y))
                if path is not None:
                    candidates.append((len(path), (col, y), path))
    else:
        row = grid.h - 1 if sign > 0 else 0
        for x in range(grid.w):
            if grid.passable(x, row):
                path = grid.path(pos, (x, row))
                if path is not None:
                    candidates.append((len(path), (x, row), path))
    if not candidates:
        p.say(tag, f"no passable tile on edge {edge}")
        return False
    candidates.sort()
    dist, spot, path = candidates[0]
    p.say(tag, f"edge {edge}: {spot} ({dist} steps)")
    e = navwalk.Explorer(p, tag)
    for d in path:
        e.probe(d)
        p.frames(18)
    direction = {"x": {1: "east", -1: "west"}, "y": {1: "south", -1: "north"}}[axis][sign]
    return step_onto(p, direction, want_map, tag)


def wander_to_battle(p, tag="grass", limit=90):
    """Step around an encounter area until the game starts a battle."""
    dirs = ["north", "west", "east", "south"]
    steps = 0
    for i in range(limit):
        if p.scene() != "overworld":
            break
        d = dirs[i % len(dirs)]
        moved, _ = p.step(d)
        steps += 1
        p.frames(16)
        p.flush_speech(f"{tag}{steps}")
        if steps % 5 == 0 or p.grass():
            p.say(tag, f"({obj_to_map(*navwalk.settled(p))}) grass={p.grass()} scene={p.scene()}")
        if not moved:
            dirs = dirs[1:] + dirs[:1]
    p.say(tag, f"stopped after {steps} steps, scene {p.scene()}")
    return p.scene() != "overworld"


def main():
    p = Pad(transcript=TRANSCRIPT)
    p.say("session", "Littleroot save -> Oldale Mart on foot -> buy a ball -> Route 101 grass -> catch")
    from checkpoints import Checkpoints

    class S:
        def __init__(self, pad):
            self.pad = pad

        def ask(self, **kw):
            return self.pad.ask(**kw)

    Checkpoints(conn=S(p)).load("torchic-grind")
    p.frames(150)
    unlock(p)
    p.say("start", f"map {curmap(p)} tile {obj_to_map(*navwalk.settled(p))}")
    say_count(p, "count_before")

    # out of Littleroot into Route 101
    lg = Grid('LAYOUT_LITTLEROOT_TOWN')
    if curmap(p) == (0, 9):
        walk(p, lg, (10, 1), "littleroot_exit", blocked=npc_tiles('LittlerootTown'))
        step_onto(p, "north", (0, 16), "littleroot_out")

    p.say("map", f"left Littleroot: {curmap(p)} at {obj_to_map(*navwalk.settled(p))}")
    if curmap(p) != (0, 16):
        p.say("abort", "did not reach Route 101")
        return

    # north up Route 101 into Oldale Town
    rg = Grid('LAYOUT_ROUTE101')
    walk(p, rg, (10, 1), "route101_north", blocked=npc_tiles('Route101'))
    step_onto(p, "north", (0, 10), "to_oldale")
    p.say("map", f"in Oldale: {curmap(p)} at {obj_to_map(*navwalk.settled(p))}")
    if curmap(p) != (0, 10):
        p.say("abort", "did not reach Oldale")
        return

    tw = Grid('LAYOUT_OLDALE_TOWN')
    go_to_warp(p, tw, [(14, 6)], (3, 7), "mart_door", people=npc_tiles('OldaleTown'))
    p.say("map", f"in the Mart: {curmap(p)}")
    if curmap(p) != (3, 7):
        p.say("abort", "did not reach the Mart")
        return

    buy_first_ball(p)
    say_count(p, "count_after_buy")

    mg = Grid('LAYOUT_MART')
    go_to_warp(p, mg, [(3, 7), (4, 7)], (0, 10), "mart_out")
    p.say("map", f"back in Oldale: {curmap(p)}")

    walk(p, tw, (10, 19), "oldale_south", blocked=npc_tiles('OldaleTown'))
    step_onto(p, "south", (0, 16), "to_route101")
    p.say("map", f"on Route 101: {curmap(p)} tile {obj_to_map(*navwalk.settled(p))}")
    if curmap(p) != (0, 16):
        p.say("abort", "did not get back to Route 101")
        return

    if not wander_to_battle(p):
        p.say("abort", "no encounter")
        return
    p.say("encounter", last(p, "enc"))
    caught = throw_from_bag(p)
    p.say("thrown", f"capture={caught}")
    for i in range(10):
        if p.scene() == "overworld":
            break
        p.confirm(80)
        p.say(f"after{i}", last(p, f"after{i}"))
    say_count(p, "count_after_throw")
    p.say("final", f"scene {p.scene()} map {curmap(p)}")


if __name__ == "__main__":
    main()

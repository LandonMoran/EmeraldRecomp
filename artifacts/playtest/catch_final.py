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


SESSION_FRAME = [0]


def last(p, tag=""):
    """Newest utterance the game spoke *in this session*.

    The mod's speech log is a ring that survives checkpoint loads, so the newest
    entry can be a line from an earlier run. Anything stamped before this
    session's first frame is ignored, which is what keeps the transcript to what
    this run actually heard.
    """
    p.flush_speech(tag)
    u = p.ask(cmd="emerald_a11y_log").get("utterances") or []
    fresh = [x for x in u if int(x.get("frame", 0)) >= SESSION_FRAME[0]]
    return (fresh[-1]["text"] if fresh else "")


def curmap(p):
    return tuple(p.nav().get("map") or p.map())


def unlock(p, limit=30):
    for _ in range(limit):
        d = p.ask(cmd="emerald_dev_state")
        if not d.get("controls_locked") and not d.get("message_box"):
            return True
        p.confirm(50)
    return False


SB1_VALID = (0x02000000, 0x02040000)


def _settle(fn, tries=6):
    """Read until two consecutive reads agree, so a moving pointer can't fool us."""
    prev = None
    for _ in range(tries):
        cur = fn()
        if prev is not None and cur == prev:
            return cur
        prev = cur
    return prev


def ball_pocket(p):
    """[(slot, itemId, quantity)] from bagPocket_PokeBalls, plus the raw bytes.

    Layout is fixed by the game: at SaveBlock1 + 0x650 the 16 entries are
    `u16 itemId, u16 quantity ^ key`, the key being u16 at SaveBlock2 + 0xAC.
    Both pointers are settled first - reading them once raced a checkpoint load
    and produced an empty pocket one moment and a real one the next.
    """
    def ptrs():
        sb1 = struct.unpack("<I", rd(p.s, "read_iwram", 0x03005D8C, 4))[0]
        sb2 = struct.unpack("<I", rd(p.s, "read_iwram", 0x03005D90, 4))[0]
        return sb1, sb2

    sb1, sb2 = _settle(ptrs)
    if not (SB1_VALID[0] <= sb1 <= SB1_VALID[1]):
        return [], 0, ""
    key = struct.unpack("<H", rd(p.s, "read_ewram", sb2 + 0xAC, 2))[0]
    raw = rd(p.s, "read_ewram", sb1 + BALL_OFFSET, BALL_SLOTS * 4)
    out = []
    for i in range(BALL_SLOTS):
        iid, qty = struct.unpack("<HH", raw[i * 4:(i + 1) * 4])
        if iid:
            out.append((i, iid, qty ^ key))
    return out, key, raw[:16].hex()


def say_count(p, tag):
    slots, key, raw = ball_pocket(p)
    total = sum(q for _, _, q in slots)
    p.say(tag, f"ball pocket: key 0x{key:04x} first 16 bytes {raw} -> "
               f"{slots if slots else 'empty'} (carrying {total})")
    return slots, total


def finish_shop(p, tag="shop"):
    """Walk the shop's own menus out: confirm the sale, then cancel to the floor.

    The clerk answers the quantity with a yes/no, then prints the sale and the
    money, then shows the stock list again; only cancel leaves the counter.
    """
    heard_sale = False
    for i in range(14):
        st = p.status()
        if st.get("scene") != "shop":
            break
        items = st.get("items") or []
        upper = [str(x).upper() for x in items]
        if "YES" in upper and "NO" in upper:
            idx = upper.index("YES")
            while p.status().get("selected") != idx:
                p.action("up", 20)
                p.frames(35)
            p.confirm(85)
        elif any(u.startswith(("POK", "ULTRA", "GREAT", "MASTER", "PREMIER"))
                 for u in upper):
            p.action("cancel", 20)
            p.frames(55)
        else:
            p.confirm(85)
        line = last(p, f"{tag}{i}")
        p.say(f"{tag}{i}", line)
        if "here you go" in line.lower():
            heard_sale = True
    p.say(tag, f"sale heard={heard_sale} scene={p.status().get('scene')}")
    # Deliberately no unlock() here: the player is facing the clerk, and a
    # stray A press reopens the counter menu.
    return heard_sale


def leave_counter(p, tag="counter"):
    """Leave the counter with B, never A, and prove the map actually changed.

    At the end of a sale the clerk is still holding the pad: `controls_locked`
    is 1 while the text reads "Is there anything else I can help you with?".
    One B answers that question ("Please come again!"), a second B closes the
    farewell and releases the pad. A is wrong here in both places - it answers
    yes and reopens the buy menu - which is what kept the player standing on the
    clerk's tile in earlier runs.
    """
    for i in range(6):
        d = p.ask(cmd="emerald_dev_state")
        if not d.get("controls_locked") and not d.get("message_box"):
            break
        p.cancel(95)
        p.frames(45)
        line = last(p, f"{tag}b{i}")
        if line:
            p.say(f"{tag}b{i}", line)

    d = p.ask(cmd="emerald_dev_state")
    p.say(tag, f"pad free: locked={d.get('controls_locked')} box={d.get('message_box')}")
    if d.get("controls_locked"):
        return False

    for i in range(10):
        if curmap(p) != (11, 7):
            break
        p.step("south")
        p.frames(85)
        p.flush_speech(f"{tag}step{i}")
    p.say(tag, f"map {curmap(p)} tile {obj_to_map(*navwalk.settled(p))}")
    return curmap(p) == (0, 3)


def walk(p, grid, target, tag, blocked=(), limit=240):
    """Step toward `target`, re-planning from the live tile after every step.

    Two things the static grid cannot know are handled here rather than being
    guessed at load time: a person standing in the lane (passed in `blocked`),
    and a tile the grid calls open but the game refuses - a ledge, a one-way
    drop, a counter. A refused step marks that tile unusable for the rest of
    this walk and the route is rebuilt around it, so the walker learns the
    difference between the map data and the room instead of stalling on it.
    """
    e = navwalk.Explorer(p, tag)
    pos = obj_to_map(*navwalk.settled(p))
    avoid = set()
    p.say(tag, f"from ({pos[0]},{pos[1]}) to {target}")
    for _ in range(limit):
        if pos == target:
            return pos
        path = grid.path(pos, target, blocked=set(blocked) | avoid)
        if not path:
            p.say(tag, f"no path from {pos} to {target} (avoiding {len(avoid)} tiles)")
            return pos
        before = pos
        e.probe(path[0])
        p.frames(18)
        pos = obj_to_map(*navwalk.settled(p))
        if pos == before:
            d = path[0]
            dx, dy = navwalk.DIRS[d] if hasattr(navwalk, "DIRS") else (0, 0)
            if (dx, dy) == (0, 0):
                from maps import DIRS as _D
                dx, dy = _D[d]
            nxt = (before[0] + dx, before[1] + dy)
            if nxt in avoid:
                p.say(tag, f"stuck at {pos} heading for {target}")
                return pos
            avoid.add(nxt)
            p.say(tag, f"({before[0]},{before[1]}) refuses {d} to {nxt}; routing around it")
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
    # quantity dialog: it opens at 1; two ups make it 3, enough to retry a
    # break-out throw without walking back to the counter.
    for _ in range(2):
        p.action("up", 20)
        p.frames(45)
    p.confirm(90)
    p.say(f"{tag}qty", last(p, f"{tag}qty"))
    p.confirm(80)
    p.say(f"{tag}total", last(p, f"{tag}total"))


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


def throw_from_bag(p, tag="throw", tries=5):
    """Throw a ball from the bag's own ball pocket, on the battle's first turn.

    The verified chain, in the order the game speaks it: `Fight, top left.`
    (right) `Bag, top right.` (A opens the bag) - the bag opens on the item
    pocket, so one more right moves to the Poké Balls pocket - A selects
    `POKé BALL`, the footer reads `POKé BALL is selected. USE, CANCEL`, A uses
    it, the game prints `A used POKé BALL!` and the throw resolves.
    """
    for attempt in range(tries):
        for i in range(24):
            st = p.status()
            if st.get("scene") != "battle":
                p.say(tag, f"left the battle without a capture line: scene {st.get('scene')}")
                return False
            line = last(p, f"{tag}{attempt}_{i}")
            p.say(f"{tag}{attempt}_{i}", line)
            low = line.lower()
            if "gotcha" in low or "was caught" in low:
                return True
            if "appeared to be caught" in low:      # broke free; try again
                break
            if "top left" in line:                  # Fight/Bag/Run menu
                p.action("right", 20)
                p.frames(55)
                continue
            if "top right" in line:                 # Bag is selected
                p.confirm(85)
                continue
            if st.get("scene") == "bag":
                items = st.get("items") or []
                if not any("BALL" in str(x).upper() for x in items):
                    p.action("right", 20)           # move to the ball pocket
                    p.frames(65)
                    continue
                if "selected" in low and "use" in low:
                    p.confirm(90)                   # USE
                    continue
                p.confirm(90)                       # select the ball
                continue
            p.confirm(80)
        else:
            return False
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
    """Reach grass, then pace inside it until the game starts a battle.

    Encounters only roll on encounter tiles, so wandering at random from the
    map edge wastes most of its steps. Walk toward grass first (checking the
    mod's own grass flag), then alternate two directions inside the patch.
    """
    for i in range(60):
        if p.scene() != "overworld":
            break
        if p.grass():
            break
        moved = False
        for d in ("east", "north", "south", "west"):
            m, _ = p.step(d)
            p.frames(14)
            if m:
                moved = True
                break
        if not moved:
            p.say(tag, f"no way to grass from ({obj_to_map(*navwalk.settled(p))})")
            break
    p.say(tag, f"grass={p.grass()} at {obj_to_map(*navwalk.settled(p))} scene={p.scene()}")

    dirs = ["east", "west", "north", "south"]
    for i in range(limit):
        if p.scene() != "overworld":
            break
        d = dirs[i % len(dirs)]
        moved, _ = p.step(d)
        p.frames(12)
        p.flush_speech(f"{tag}{i}")
        if not moved:
            dirs = dirs[1:] + dirs[:1]
        if i % 10 == 9:
            p.say(tag, f"step {i + 1}: {obj_to_map(*navwalk.settled(p))} "
                       f"grass={p.grass()} scene={p.scene()}")
    p.say(tag, f"stopped after {limit} steps, scene {p.scene()}")
    return p.scene() != "overworld"


def main():
    p = Pad(transcript=TRANSCRIPT)
    SESSION_FRAME[0] = int(p.ask(cmd="get_frame").get("frame", 0))
    p.say("session", "one session, no restart: Rustboro gym -> Mart -> buy a ball -> "
                     "Route 116 grass -> throw from the bag -> capture")
    from checkpoints import Checkpoints

    class S:
        def __init__(self, pad):
            self.pad = pad

        def ask(self, **kw):
            return self.pad.ask(**kw)

    # rustboro-cleared is the shortest honest path: the gym is one open room two
    # steps from its exit, the town's Mart is a straight walk with no warp, and
    # Route 116 grass is one map connection east.
    Checkpoints(conn=S(p)).load("rustboro-cleared")
    p.frames(150)
    unlock(p)
    p.say("start", f"map {curmap(p)} tile {obj_to_map(*navwalk.settled(p))}")
    before, before_total = say_count(p, "count_before")

    gg = Grid('LAYOUT_RUSTBORO_CITY_GYM')
    go_to_warp(p, gg, [(5, 19), (6, 19)], (0, 3), "gym_out",
               people=npc_tiles('RustboroCity_Gym'))
    if curmap(p) != (0, 3):
        p.say("abort", f"did not leave the gym, at {curmap(p)}")
        return
    p.say("map", f"out of the gym: {curmap(p)} at {obj_to_map(*navwalk.settled(p))}")

    tw = Grid('LAYOUT_RUSTBORO_CITY')
    go_to_warp(p, tw, [(16, 45)], (11, 7), "mart_door", people=npc_tiles('RustboroCity'))
    if curmap(p) != (11, 7):
        p.say("abort", f"did not reach the Mart, at {curmap(p)}")
        return
    p.say("map", f"in the Mart: {curmap(p)} at {obj_to_map(*navwalk.settled(p))}")

    buy_first_ball(p)
    finish_shop(p, "shop")
    after, after_total = say_count(p, "count_after_buy")

    if not leave_counter(p, "counter"):
        p.say("abort", f"still in the Mart: {curmap(p)}")
        return
    p.say("map", f"back on the city map: {curmap(p)} at {obj_to_map(*navwalk.settled(p))}")

    cross_edge(p, tw, ("x", 1), (0, 31), "to_route116")
    if curmap(p) != (0, 31):
        p.say("abort", f"did not reach Route 116, at {curmap(p)}")
        return
    p.say("map", f"on Route 116: {curmap(p)} tile {obj_to_map(*navwalk.settled(p))}")

    if not wander_to_battle(p):
        p.say("abort", "no wild encounter started")
        return
    p.say("encounter", last(p, "enc"))
    caught = throw_from_bag(p)
    p.say("thrown", f"capture line seen={caught}")
    for i in range(14):
        p.confirm(85)
        p.say(f"after{i}", last(p, f"after{i}"))
        st = p.status()
        if st.get("scene") == "overworld" and i >= 2:
            break

    end_slots, end_total = say_count(p, "count_after_throw")
    dump_party(p)
    p.say("decrement", f"after purchase {after_total} -> after throw {end_total}, "
                       f"difference {after_total - end_total}")
    p.say("final", f"scene {p.scene()} map {curmap(p)} at {obj_to_map(*navwalk.settled(p))}")


if __name__ == "__main__":
    main()

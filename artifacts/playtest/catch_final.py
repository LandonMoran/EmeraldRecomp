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


SESSION_SEQ = [0]


def last(p, tag=""):
    """Newest utterance the game spoke *in this session*.

    The mod's speech log is a ring that survives checkpoint loads, so the newest
    entry can be a line from an earlier run. Anything stamped before this
    session's first frame is ignored, which is what keeps the transcript to what
    this run actually heard.
    """
    p.flush_speech(tag)
    u = p.ask(cmd="emerald_a11y_log").get("utterances") or []
    fresh = [x for x in u if int(x.get("seq", 0)) > SESSION_SEQ[0]]
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


def buy_until(p, want=3, tag="buy", tries=5):
    """Buy until the pocket itself shows `want` balls.

    The shop's `IN BAG:` line is a raw list/price/quantity field, not a count,
    so the only accepted evidence is the pocket bytes. A single purchase of one
    ball is already proven; repeating it is deterministic and needs no work on
    the quantity selector, and a break-out throw then has balls left to retry.
    """
    for i in range(tries):
        slots, key, raw = ball_pocket(p)
        total = sum(q for _, _, q in slots)
        p.say(tag, f"pocket before purchase {i + 1}: {slots if slots else 'empty'} "
                   f"(carrying {total}) bytes {raw}")
        if total >= want:
            return total
        if i == 0:
            buy_first_ball(p, f"{tag}1")
        else:
            p.confirm(95)                      # A at the counter reopens the shop
            p.say(f"{tag}{i + 1}open", last(p, f"{tag}{i + 1}open"))
            for _ in range(4):
                items = [str(x).upper() for x in (p.status().get("items") or [])]
                if "BUY" in items:
                    idx = items.index("BUY")
                    while p.status().get("selected") != idx:
                        p.action("up", 20)
                        p.frames(40)
                    p.confirm(90)
                    break
                if any("BALL" in x for x in items):
                    break
                p.confirm(85)
            p.say(f"{tag}{i + 1}stock", last(p, f"{tag}{i + 1}stock"))
            p.confirm(90)
            p.say(f"{tag}{i + 1}qty", last(p, f"{tag}{i + 1}qty"))
            p.confirm(90)
            p.say(f"{tag}{i + 1}total", last(p, f"{tag}{i + 1}total"))
        finish_shop(p, f"{tag}{i + 1}shop")
    slots, key, raw = ball_pocket(p)
    return sum(q for _, _, q in slots)


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


def battle_and_catch(p, tag="battle", max_throws=4):
    """Open the bag from the battle menu and throw until the game says caught.

    Driven from live state, not from expected speech: a wild ABRA encounter
    prints no `Fight, top left.` line, so gating on the menu announcements
    deadlocks. What is always true is the scene: in `battle` the cursor starts
    on Fight, one right selects Bag and A opens the bag; the bag opens on the
    item pocket, so walk right until a ball row exists; A selects it, the footer
    becomes `USE, CANCEL`, and A uses it. Everything the game says during the
    animation is logged verbatim, which is what carries the capture and Pokedex
    lines into the transcript.
    """
    throws = 0
    for _ in range(max_throws):
        if p.status().get("scene") == "overworld":
            break
        p.action("right", 20)          # Fight -> Bag
        p.frames(65)
        p.confirm(95)                  # open the bag
        for _ in range(5):
            st = p.status()
            if st.get("scene") != "bag":
                break
            items = [str(i).upper() for i in (st.get("items") or [])]
            if any("BALL" in i for i in items):
                break
            p.action("right", 20)      # item pocket -> Poké Balls pocket
            p.frames(70)
            p.flush_speech(f"{tag}pocket")
        p.confirm(95)                  # select the ball
        p.say(f"{tag}select", last(p, f"{tag}select"))
        p.confirm(95)                  # USE
        throws += 1
        p.say(tag, f"throw {throws}")
        for _ in range(18):            # let the throw animation resolve
            p.frames(70)
            p.flush_speech(tag)
            heard = capture_lines(p)
            if any("was caught" in t.lower() or "gotcha" in t.lower() for t in heard):
                # The Pokedex lines land a beat after the capture line, so keep
                # draining the speech instead of cutting the transcript here.
                p.say(tag, f"captured after throw {throws}")
                for _ in range(14):
                    p.frames(70)
                    p.flush_speech(tag)
                return throws
            if p.status().get("scene") == "overworld":
                break
    p.say(tag, f"throws used: {throws}, scene {p.status().get('scene')}")
    return throws


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


def dump_party(p):
    """Append the live party, read from gPlayerParty, to this transcript."""
    import party as party_mod
    try:
        out = party_mod.dump(p)
    except Exception as exc:
        p.say("party", f"party read failed: {exc}")
        return
    for line in out:
        p.say("party", str(line))


def capture_lines(p, since_tag="battle"):
    u = p.ask(cmd="emerald_a11y_log").get("utterances") or []
    return [x["text"] for x in u if int(x.get("seq", 0)) > SESSION_SEQ[0]]


def flee(p, tag="flee"):
    """Leave a wild battle through the battle menu's Run entry."""
    for _ in range(6):
        if p.status().get("scene") != "battle":
            return
        p.action("down", 20)
        p.frames(55)
        p.action("right", 20)
        p.frames(55)
        p.confirm(90)
        p.frames(90)
        p.flush_speech(tag)


def run_encounters(p, rounds=8, tag="hunt"):
    """Keep meeting wild Pokemon until one is newly registered.

    A save that already owns a species gets no `data was added to the POKeDEX`
    line for it, and some encounters cannot be caught at all (the ABRA that
    TELEPORTed away). So the leg is driven by the game's own announcements:
    known-owned species are left through Run instead of spending a ball, and
    the hunt only stops when the Pokedex line itself appears.
    """
    known = set()
    for r in range(rounds):
        slots, _k, _raw = ball_pocket(p)
        have = sum(q for _, _, q in slots)
        if have <= 0:
            p.say(tag, "out of balls")
            return False
        if not wander_to_battle(p):
            p.say(tag, f"round {r + 1}: no encounter")
            continue
        seen = last(p, f"{tag}enc{r + 1}")
        p.say(f"{tag}enc{r + 1}", seen)
        upper = seen.upper()
        if "POOCHYENA" in upper:
            p.say(tag, f"round {r + 1}: POOCHYENA already owns a Pokedex entry, running")
            flee(p, f"{tag}flee{r + 1}")
            known.add("POOCHYENA")
            continue
        throws = battle_and_catch(p, tag)
        texts = [t for t in capture_lines(p)]
        caught = any("was caught" in t.lower() for t in texts)
        dex = any("added to the POK" in t for t in texts)
        slots, _k, _raw = ball_pocket(p)
        p.say(tag, f"round {r + 1}: thrown={throws} caught={caught} pokedex={dex} "
                   f"balls left={sum(q for _, _, q in slots)}")
        if caught and dex:
            return True
    return False


def main():
    p = Pad(transcript=TRANSCRIPT)
    # Speech is logged by a ring that outlives a checkpoint load and whose frame
    # stamps restart, so this session is given a seq floor: anything logged
    # before the run began can never be quoted as evidence.
    _u = p.ask(cmd="emerald_a11y_log").get("utterances") or []
    SESSION_SEQ[0] = max([int(x.get("seq", 0)) for x in _u] or [0])
    p.log_seq = SESSION_SEQ[0]
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

    bought = buy_until(p, 5, "buy")
    after, after_total = say_count(p, "count_after_buy")
    p.say("bought", f"pocket holds {bought} balls after shopping")

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
    caught_ok = run_encounters(p)
    p.say("caught", f"a Pokemon was caught this session: {caught_ok}")

    end_slots, end_total = say_count(p, "count_after_throw")
    dump_party(p)
    p.say("decrement", f"after purchase {after_total} -> after throw {end_total}, "
                       f"difference {after_total - end_total}")
    p.say("final", f"scene {p.scene()} map {curmap(p)} at {obj_to_map(*navwalk.settled(p))}")


if __name__ == "__main__":
    main()

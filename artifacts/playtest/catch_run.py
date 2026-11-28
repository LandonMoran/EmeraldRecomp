"""One session: buy a Poke Ball at the Oldale counter, walk to Route 101, catch.

Why this exists
---------------
The first catch proved the mechanic but its transcript was lost: `pad.Pad`
truncated the transcript on every new connection, and the run was several
sessions. This script is the whole sequence in one connection so the file it
writes is the whole story: the purchase with its confirmation, the walk south
into Route 101 with the map-transition cue, the encounter, the ball thrown from
the bag pocket, the capture, and the Pokedex line.

Run:  python3 artifacts/playtest/catch_run.py
"""

import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad                                    # noqa: E402
from maps import Grid, obj_to_map                      # noqa: E402
import navwalk                                         # noqa: E402

TRANSCRIPT = "artifacts/playtest/reports/catch-pokeball.txt"


def last(p, tag=""):
    p.flush_speech(tag)
    u = p.ask(cmd="emerald_a11y_log").get("utterances") or []
    return (u[-1]["text"] if u else "")


def curmap(p):
    return tuple(p.nav().get("map") or p.map())


def unlock(p, limit=25):
    for _ in range(limit):
        d = p.ask(cmd="emerald_dev_state")
        if not d.get("controls_locked") and not d.get("message_box"):
            return True
        p.confirm(50)
    return False


def select_item(p, wanted, limit=12):
    """Walk the mod's announced list to the entry whose text starts with `wanted`."""
    for i in range(limit):
        t = last(p, f"sel{i}")
        if t.upper().startswith(wanted.upper()):
            return t
        p.action("down", 20)
        p.frames(45)
    return last(p, "sel_end")


def leave_shop(p, tag="leave"):
    """Walk out of the shop UI: QUIT the clerk list, answer nothing else."""
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
    # the farewell box is still open and owns the pad
    unlock(p)
    return p.status().get("scene")


def walk_path(p, grid, target, tag="walk"):
    pos = obj_to_map(*navwalk.settled(p))
    path = grid.path(pos, target)
    p.say(tag, f"({pos[0]},{pos[1]}) -> {target}: {None if path is None else len(path)} steps")
    e = navwalk.Explorer(p, tag)
    for d in path or []:
        e.probe(d)
        p.frames(18)
    return obj_to_map(*navwalk.settled(p))


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


def battle_throw(p, ball="POKé BALL"):
    """Turn one: Bag -> the ball pocket -> the ball. Never the Fight cursor."""
    for i in range(26):
        t = last(p, f"b{i}")
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


def main():
    p = Pad(transcript=TRANSCRIPT)
    p.say("session", "Oldale Mart counter -> Route 101 grass -> Poke Ball catch")
    unlock(p)
    p.say("at", f"map {curmap(p)} tile {obj_to_map(*navwalk.settled(p))}")

    g = Grid('LAYOUT_MART')
    walk_path(p, g, (3, 3), "counter")
    p.ask(cmd="emerald_a11y_action", action="west")
    p.frames(24)
    p.confirm(90)
    p.say("talk", last(p, "talk"))
    p.confirm(80)
    p.say("menu", last(p, "menu"))

    # BUY is the first clerk entry
    idx = (p.status().get("items") or []).index("BUY") if p.status().get("items") else 0
    while p.status().get("selected") != idx:
        p.action("down", 20)
        p.frames(45)
    p.confirm(90)
    p.say("stock", select_item(p, "POKé BALL") or "?")
    p.confirm(90)
    p.say("quantity", last(p, "qty"))
    p.confirm(80)
    p.say("total", last(p, "total"))
    for i in range(3):
        p.confirm(80)
        p.say(f"buy{i}", last(p, f"buy{i}"))
    leave_shop(p)
    p.say("shop_done", f"scene {p.status().get('scene')}")

    # out of the door and south to Route 101
    walk_path(p, g, (3, 7), "todoor")
    e = navwalk.Explorer(p, "out")
    e.probe("south")
    p.frames(200)
    p.flush_speech("oldale")
    p.say("oldale", f"map {curmap(p)} tile {obj_to_map(*navwalk.settled(p))}")

    og = Grid('OldaleTown_Layout')
    walk_path(p, og, (10, 19), "tosouth")
    e.probe("south")
    p.frames(220)
    p.flush_speech("route101")
    p.say("route101", f"map {curmap(p)} tile {obj_to_map(*navwalk.settled(p))}")

    # into the grass until something jumps out
    rg = Grid('Route101_Layout')
    steps = 0
    while steps < 90 and p.scene() == "overworld":
        pos = obj_to_map(*navwalk.settled(p))
        target = (10, 3) if pos[1] > 3 else (10, 8)
        path = rg.path(pos, target) or []
        for d in path:
            if p.scene() != "overworld":
                break
            p.step(d)
            steps += 1
            p.frames(20)
        p.flush_speech(f"grass{steps}")
        p.say("grass", f"({pos[0]},{pos[1]}) grass={p.grass()} scene={p.scene()}")
        if p.scene() != "overworld":
            break
        if p.scene() == "overworld" and steps % 20 == 0:
            og2 = (pos[0], pos[1])
            p.step("north" if steps % 40 else "south")
            p.frames(20)
    p.say("encounter", last(p, "enc"))
    if p.scene() == "battle":
        caught = battle_throw(p)
        p.say("throw_done", f"caught={caught}")
        for i in range(8):
            if p.scene() == "overworld":
                break
            p.confirm(80)
            p.say(f"after{i}", last(p, f"after{i}"))
        p.say("final", f"scene {p.scene()}")
    else:
        p.say("no_battle", f"scene {p.scene()} after {steps} steps")


if __name__ == "__main__":
    main()

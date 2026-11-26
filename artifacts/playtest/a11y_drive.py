"""Accessibility playtest driver (script-aware).

The intro is full of scripted movements: pressing the d-pad while a script is
walking the player leaves the player object stuck in a held movement, after
which no input moves it. So every input here waits for the field script to be
idle first, and A is only pressed while a message box is actually waiting.

State comes from the a11y TCP layer (nav / status / spoken log) plus two guest
bytes: the script context status and the field message box mode.

    python3 drive.py state
    python3 drive.py intro     advance text / walk through the intro to the house
    python3 drive.py stairs    walk to the 2F stairs and take them
    python3 drive.py clock     find the clock, open it
    python3 drive.py out       leave the house
    python3 drive.py north     walk north until the map changes
"""
import sys
import time
sys.path.insert(0, "/tmp")
import bot
from bot import *

S = bot.conn()
S.settimeout(15)

SCRIPT_STATUS = 0x03000E38      # sGlobalScriptContextStatus: 2 = running
MESSAGE_BOX = 0x020375BC        # sFieldMessageBoxMode: non-zero = box waiting


def log(*a):
    print(*a, flush=True)


def u8(addr):
    return rd(S, "read_ewram" if addr < 0x03000000 else "read_iwram", addr, 1)[0]


def player_busy():
    """True while the player object is held by a script or frozen.

    The field script status stays RUNNING on an idle field, so it is not a
    usable signal; the player object's own flags are: heldMovementActive,
    frozen, or inactive.
    """
    av = rd(S, "read_ewram", 0x02037590, 8)
    eid = av[5]
    e = rd(S, "read_ewram", 0x02037350 + eid * 0x24, 4)
    active = e[0] & 1
    held = (e[0] >> 6) & 1
    frozen = e[1] & 1
    return (not active) or held == 1 or frozen == 1


def script_running():
    return player_busy()


def box_open():
    return u8(MESSAGE_BOX) != 0


def st():
    return nav(S)


def frames(n):
    ask(S, {"cmd": "run_frames", "n": n})


def wait_idle(limit=40):
    """Let scripts finish; returns True when the field accepts input."""
    for _ in range(limit):
        if not player_busy() and not box_open():
            return True
        frames(15)
    return False


def advance(limit=30):
    """Press A while a message box is waiting; returns boxes advanced."""
    n = 0
    for _ in range(limit):
        if not box_open():
            return n
        act(S, "confirm", 24)
        frames(40)
        n += 1
    return n


def move_one(d, frames_hold=24):
    if not wait_idle():
        log("   (script busy, movement skipped)")
        return False
    a = st()
    before = (a["x"], a["y"], tuple(a["map"]))
    act(S, d, frames_hold)
    b = st()
    return (b["x"], b["y"], tuple(b["map"])) != before, b


def walk_to(tx, ty, budget=60, tag="walk"):
    for _ in range(budget):
        n = st()
        cur = (n["x"], n["y"])
        if cur == (tx, ty):
            log(f"[{tag}] arrived {cur}")
            return True
        if advance(3):
            continue
        order = sorted(((1, 0, "right"), (-1, 0, "left"), (0, 1, "down"), (0, -1, "up")),
                       key=lambda o: abs(cur[0] + o[0] - tx) + abs(cur[1] + o[1] - ty))
        moved = False
        for dx, dy, d in order:
            ok = move_one(d)
            if ok and ok != True:
                ok, b = ok
                if ok:
                    log(f"[{tag}] {d} -> ({b['x']},{b['y']}) {b['map']} look={b['look']['kind']}")
                    moved = True
                    break
        if not moved:
            log(f"[{tag}] stuck at {cur}")
            frames(30)
    log(f"[{tag}] gave up at {st()['x']},{st()['y']}")
    return False


def state(tag):
    n = st()
    stt = status(S)
    log(f"{tag}: map={n['map']} pos=({n['x']},{n['y']}) facing={n['facing']} "
        f"look={n['look']['kind']} warps={[(w['x'], w['y'], w['dest']) for w in n['warps']]}")
    log(f"   script={u8(SCRIPT_STATUS)} box={u8(MESSAGE_BOX)} menu={stt['menu']} "
        f"list={stt['list']} battle={stt['battle']} items={stt['items'][:6]}")
    log(f"   speech={speech(S)[-2:]}")


def cmd_intro():
    """Advance every dialogue box until the field is idle and free to walk."""
    for i in range(80):
        if box_open():
            n = advance(6)
            if n:
                log(f"[{i}] advanced {n} box(es)")
                continue
        if not player_busy() and not box_open():
            log(f"[{i}] field idle")
            state("idle")
            return
        frames(20)
    state("intro end")


def cmd_truck():
    """Walk east into the truck's door and read the intro that follows."""
    state("truck")
    for _ in range(8):
        n = st()
        res = move_one("right", 30)
        if res is False:
            advance(2)
            continue
        ok, b = res
        if ok:
            log(f"[truck] right -> ({b['x']},{b['y']}) {b['map']}")
            if n["map"] != b["map"]:
                log(f"[truck] left the truck {n['map']} -> {b['map']}")
                frames(120)
                cmd_intro()
                return
    state("truck end")


def cmd_stairs():
    state("start")
    walk_to(9, 9, tag="stairs")
    state("at stairs")
    ok = move_one("up", 40)
    frames(150)
    state("after up")


def cmd_clock():
    state("in 2F")
    for d in ("up", "left", "right", "down"):
        wait_idle()
        act(S, d, 2)
        frames(15)
        act(S, "confirm", 30)
        frames(60)
        stt = status(S)
        if stt["menu"] or stt["list"]:
            log(f"menu facing {d}: items={stt['items']} sel={stt['selected']}")
            state("clock menu")
            return
    state("no menu")


def cmd_out():
    state("out start")
    n = st()
    door = [w for w in n["warps"] if tuple(w["dest"]) != (0, 9)]
    log(f"exits: {door}")
    if door:
        walk_to(door[0]["x"], door[0]["y"], tag="door")
        frames(120)
    state("after door")


def cmd_north():
    state("north start")
    for _ in range(40):
        n = st()
        res = move_one("up", 24)
        if res is False:
            advance(2)
        elif res[0]:
            b = res[1]
            if n["map"] != b["map"]:
                log(f"map change {n['map']} -> {b['map']}")
                state("after map change")
                return
    state("north end")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "state"
    {
        "state": lambda: state("state"),
        "intro": cmd_intro,
        "truck": cmd_truck,
        "stairs": cmd_stairs,
        "clock": cmd_clock,
        "out": cmd_out,
        "north": cmd_north,
    }[cmd]()

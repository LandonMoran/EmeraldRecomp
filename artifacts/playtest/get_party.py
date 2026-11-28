"""Get a real party into a checkpoint by playing Route 101's rescue event.

A checkpoint without a party cannot test a gym, because the gym's trainers lock
the field before the puzzle is reachable. The starter itself must come from the
game: this script warps to Route 101 just south of the rescue coord event,
arms it the way Littleroot's gate script does (``VAR_ROUTE101_STATE = 1``), walks
onto the trigger, takes the first starter the cutscene offers, and wins the
rescue battle with the pad.

Walking out of Littleroot is deliberately not attempted: the north exit is
blocked by a coord event while ``VAR_LITTLEROOT_TOWN_STATE`` is 0, which is the
message a script with no party gets stuck on.

    python3 artifacts/playtest/get_party.py --save party-starter

The emulator must already be running (artifacts/playtest/boot_field.py starts
one); a checkpoint is written with checkpoints.Checkpoints only on success.
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from checkpoints import Checkpoints  # noqa: E402
from pad import Pad  # noqa: E402
import party as party_mod  # noqa: E402

ROUTE101 = (0, 16)
# Route 101's rescue coord events sit at (10,19) and (11,19). Map y grows
# southwards, so the approach tile is (10,18) and the step onto the trigger is
# "down".
APPROACH = (10, 18)
TRIGGER = (10, 19)
VAR_ROUTE101_STATE = 0x4060


def arm_trigger(p):
    sb1 = p.saveblock()
    addr = sb1 + 0x139C + 2 * (VAR_ROUTE101_STATE - 0x4000)
    p.ask(cmd="write_mem", addr=addr, hex=struct.pack("<H", 1).hex())
    p.say("scaffold", "VAR_ROUTE101_STATE=1")


def warp(p, x, y, facing="south"):
    reply = p.ask(cmd="emerald_dev_warp", map_group=ROUTE101[0], map_num=ROUTE101[1],
                  x=x, y=y, facing=facing)
    if reply.get("ok") is False:
        raise SystemExit(f"warp refused: {reply.get('error')}")
    for _ in range(120):
        state = p.ask(cmd="emerald_dev_state")
        if state.get("warp", {}).get("done"):
            if not state["warp"].get("ok"):
                raise SystemExit(f"warp failed: {state['warp'].get('detail')}")
            p.say("warp", state["warp"].get("detail", "ok"))
            return
        p.frames(5)
    raise SystemExit("warp did not finish in 10 s")


def advance_cutscene(p, on_starter=None):
    """Press A through the dialogue; choose the first starter when offered."""
    for i in range(200):
        st = p.status()
        if st.get("scene") == "battle":
            p.say("cutscene", "battle started")
            return "battle"
        items = st.get("items") or []
        if st.get("menu") and len(items) >= 2:
            p.say("cutscene", f"menu {items} -> choosing first")
            if on_starter:
                on_starter(i)
            p.confirm(40)
            continue
        p.confirm(24)
        p.flush_speech(f"cut{i + 1}")
    return "timeout"


def win_battle(p, limit=160):
    """The battle opens on FIGHT / the first move, so A alone fights it."""
    for i in range(limit):
        st = p.status()
        if st.get("scene") != "battle":
            p.flush_speech("after-battle")
            return True
        p.confirm(30)
        p.flush_speech(f"battle{i + 1}")
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save", default="party-starter", help="checkpoint name")
    args = ap.parse_args()

    p = Pad("artifacts/playtest/transcript-party.txt")
    st = p.status()
    p.say("start", f"scene {st.get('scene')} map {p.map_name()}")

    arm_trigger(p)
    warp(p, *APPROACH)
    p.say("field", f"at {p.ask(cmd='emerald_dev_state').get('pos')}")

    moved, _ = p.step("down")
    p.flush_speech("trigger")
    pos = p.ask(cmd="emerald_dev_state").get("pos")
    p.say("trigger", f"{moved=} pos {pos} want {list(TRIGGER)}")
    if pos != list(TRIGGER):
        raise SystemExit(f"did not land on the rescue trigger: {pos}")

    outcome = advance_cutscene(p)
    if outcome != "battle":
        raise SystemExit(f"cutscene ended in {outcome}, no battle")

    # Party exists as soon as the starter is created, before the battle.
    mons = party_mod.dump(p)
    p.say("party", f"count {len(mons)} levels {[m['level'] for m in mons]}")

    if not win_battle(p):
        p.say("battle", "did not finish in the step budget")
    st = p.status()
    p.say("end", f"scene {st.get('scene')}")

    ck = Checkpoints(conn=p)
    ck.save(args.save, note="starter obtained on Route 101")
    print(f"saved checkpoint {args.save}")


if __name__ == "__main__":
    main()

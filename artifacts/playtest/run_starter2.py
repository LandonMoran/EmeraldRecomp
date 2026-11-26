"""Phase 2b: land on the Route 101 rescue trigger and play the starter cutscene.

Harness scaffolding (docs/PLAYTEST.md has the why):
  * the intro truck leaves the player object outside its 5x5 layout, so the
    game cannot be walked out of the opening. The harness asks the game to load
    a map through its own CB2_LoadMap instead.
  * VAR_LITTLEROOT_INTRO_STATE / VAR_ROUTE101_STATE are set to the values the
    intro would have set, so the route's rescue coord event is armed and the
    town's arrival script does not re-seat the player.

Run:  nohup python3 -u artifacts/playtest/run_starter2.py > artifacts/playtest/run_starter2.log 2>&1 &
"""

import struct
import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad, boot_to_field   # noqa: E402

VAR_LITTLEROOT_INTRO_STATE = 0x4092
VAR_ROUTE101_STATE = 0x4060


def main():
    p = Pad("artifacts/playtest/transcript-starter.txt")
    boot_to_field(p)

    sb1 = p.saveblock()

    def setvar(var, value):
        addr = sb1 + 0x139C + 2 * (var - 0x4000)
        p.ask(cmd="write_mem", addr=addr, hex=struct.pack("<H", value).hex())
        p.say("scaffold", f"var {hex(var)} = {value} @ {hex(addr)}")

    setvar(VAR_LITTLEROOT_INTRO_STATE, 1)
    setvar(VAR_ROUTE101_STATE, 1)

    p.force_map(0, 16, 10, 19)
    o = p.obj()
    p.say("field", f"({o['x']},{o['y']}) map {p.map_name()} scene {p.scene()}")

    # If the arrival tile was not the trigger, step onto it.
    for attempt in range(6):
        if p.scene() != "overworld":
            break
        for d in ("up", "right", "left", "down"):
            moved, o = p.step(d)
            p.flush_speech(f"seek{attempt}{d}")
            p.say("seek", f"{d} {'->' if moved else 'blocked at'} ({o['x']},{o['y']}) "
                          f"map {p.map_name()} scene {p.scene()}")
            if p.scene() != "overworld":
                break
            if moved:
                break

    # Cutscene: advance text, take the first starter when the choice opens.
    for i in range(120):
        st = p.status()
        if st.get("scene") == "battle":
            p.say("cutscene", "BATTLE STARTED")
            break
        items = st.get("items") or []
        if st.get("menu") and len(items) >= 2:
            p.say("cutscene", f"menu {items} selected {st.get('selected')}")
            p.confirm(40)
            continue
        p.confirm(24)
        p.flush_speech(f"cut{i + 1}")

    p.flush_speech("battle")
    st = p.status()
    p.say("status", f"scene {st.get('scene')} menu {st.get('menu')} battle {st.get('battle')} "
                    f"message '{(st.get('message') or '')[:120]}'")
    p.say("end", "phase 2b done")


if __name__ == "__main__":
    main()

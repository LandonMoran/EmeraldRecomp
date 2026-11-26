"""Phase 2c: town -> north gate -> Route 101 rescue -> starter -> battle.

Live NPC tiles are planned around (static collision cannot see people).
Scaffolding is limited to: force_map (the intro truck cannot be walked in this
build) and VAR_ROUTE101_STATE=1 (arms the route's rescue coord event).

Run:  nohup python3 -u artifacts/playtest/run_starter3.py > artifacts/playtest/run_starter3.log 2>&1 &
"""

import struct
import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad, boot_to_field   # noqa: E402
from mapdata import Layout           # noqa: E402
from navwalk import goto             # noqa: E402


def main():
    p = Pad("artifacts/playtest/transcript-starter.txt")
    town = Layout("LittlerootTown_Layout")
    boot_to_field(p)

    sb1 = p.saveblock()
    addr = sb1 + 0x139C + 2 * (0x4060 - 0x4000)          # VAR_ROUTE101_STATE
    p.ask(cmd="write_mem", addr=addr, hex=struct.pack("<H", 1).hex())
    p.say("scaffold", "VAR_ROUTE101_STATE=1")

    p.force_map(0, 9, 10, 10)
    o = p.obj()
    npcs = p.npc_tiles()
    p.say("field", f"({o['x']},{o['y']}) map {p.map_name()} npcs {sorted(npcs)}")

    gate = [(10, 0), (11, 0), (10, 1), (11, 1)]
    goto(p, town, gate, blocked=npcs, tag="north", max_steps=60)

    # Out of the gate and onto the rescue trigger.
    for i in range(4):
        if p.scene() != "overworld":
            break
        moved, o = p.step("up")
        p.flush_speech(f"gate{i + 1}")
        p.say("gate", f"up {'->' if moved else 'blocked at'} ({o['x']},{o['y']}) "
                      f"map {p.map_name()} scene {p.scene()}")

    # Cutscene: advance text; take the first starter when the choice opens.
    for i in range(140):
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
    p.say("end", "phase 2c done")


if __name__ == "__main__":
    main()

"""Phase 2: walk into Birch's rescue on Route 101, pick a starter, reach the battle.

Harness scaffolding (documented in docs/PLAYTEST.md):
  * pad.force_map(0,16,...) -- this build cannot walk out of the intro truck;
    the harness asks the game to load Route 101 through its own CB2_LoadMap.
  * VAR_ROUTE101_STATE = 1  -- the coord event at (10,19)/(11,19) that starts
    the rescue only fires in that state, and the intro never set it.

Run:  nohup python3 -u artifacts/playtest/run_starter.py > artifacts/playtest/run_starter.log 2>&1 &
"""

import struct
import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad, boot_to_field          # noqa: E402
from mapdata import Layout                  # noqa: E402
from navwalk import goto                    # noqa: E402


def main():
    p = Pad("artifacts/playtest/transcript-starter.txt")
    lay = Layout("LittlerootTown_Layout")
    boot_to_field(p)
    # Land inside LittlerootTown and walk out of its north gate: the town's only
    # path north is x=10/11, which lands straight on the rescue trigger tile
    # (10,19) of Route 101. One step per pad action, verified below.
    p.force_map(0, 9, 10, 10)

    # VAR_ROUTE101_STATE (0x4060) lives in SaveBlock1.vars at +0x139C.
    sb1 = p.saveblock()
    var_addr = sb1 + 0x139C + 2 * (0x4060 - 0x4000)
    p.ask(cmd="write_mem", addr=var_addr, hex=struct.pack("<H", 1).hex())
    p.say("scaffold", f"VAR_ROUTE101_STATE=1 at {hex(var_addr)}")

    o = p.obj()
    p.say("field", f"start ({o['x']},{o['y']}) map {p.map_name()}")
    # Walk to the town's north gate, then straight out into Route 101: the
    # gate corridor lands on (10,19)/(11,19), the rescue trigger tiles.
    goto(p, lay, [(10, 0), (11, 0), (10, 1), (11, 1)], tag="north")
    for _ in range(3):
        if p.scene() != "overworld":
            break
        moved, o = p.step("up")
        p.flush_speech("gate")
        p.say("gate", f"up {'->' if moved else 'blocked at'} ({o['x']},{o['y']}) "
                      f"map {p.map_name()} scene {p.scene()}")

    # Cutscene: advance text, and take the first starter when the choice opens.
    for i in range(90):
        st = p.status()
        scene = st.get("scene")
        if scene == "battle":
            p.say("cutscene", "BATTLE STARTED")
            break
        items = st.get("items") or []
        if st.get("menu") and len(items) >= 2:
            p.say("cutscene", f"menu: {items} (selected {st.get('selected')})")
            p.confirm(40)
            continue
        p.confirm(24)
        p.flush_speech(f"cut{i + 1}")

    p.flush_speech("battle")
    st = p.status()
    p.say("status", f"scene {st.get('scene')} menu {st.get('menu')} battle {st.get('battle')} "
                    f"message '{(st.get('message') or '')[:110]}'")
    p.say("end", "phase 2 done")


if __name__ == "__main__":
    main()

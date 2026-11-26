"""Phase 1: walk Route 101 by ear until a wild Pokémon shows up.

Run:  nohup python3 -u artifacts/playtest/run_wild.py > artifacts/playtest/run_wild.log 2>&1 &
"""

import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad, boot_to_field   # noqa: E402

OUT = "artifacts/playtest/transcript-walk.txt"


def main():
    p = Pad(OUT)
    boot_to_field(p)
    # Harness scaffolding (see pad.force_map): the truck intro leaves this build
    # unable to walk, so put the game on Route 101 through its own map loader.
    p.force_map(0, 16, 10, 18)
    o = p.obj()
    p.say("field", f"map {p.map_name()} ({o['x']},{o['y']}) grass={p.grass()}")

    # The route runs north from LittlerootTown; the tall grass sits off the
    # path. Walk west first, then north, and pace in the first grass we find.
    p.walk("left", 6, "west")
    for i in range(20):
        if p.scene() == "battle":
            break
        p.walk("up", 1, "north")
        if p.scene() == "battle":
            break
        if p.grass():
            p.say("field", "in tall grass, pacing for an encounter")
            for _ in range(25):
                p.walk("down", 1, "pace")
                if p.scene() == "battle":
                    break
                p.walk("up", 1, "pace")
                if p.scene() == "battle":
                    break
            break

    p.flush_speech("battle")
    st = p.status()
    p.say("status", f"scene {st.get('scene')} menu {st.get('menu')} "
                    f"battle {st.get('battle')} message {st.get('message','')[:80]}")
    nav = p.nav()
    p.say("status", f"nav x {nav.get('x')} y {nav.get('y')} look {nav.get('look')}")
    p.say("end", "phase 1 done")


if __name__ == "__main__":
    main()

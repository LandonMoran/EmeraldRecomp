"""Test: is the truck intro walkable now that a pad direction is a real step?

Run:  nohup python3 -u artifacts/playtest/run_intro.py > artifacts/playtest/run_intro.log 2>&1 &
"""

import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad, boot_to_field   # noqa: E402

OUT = "artifacts/playtest/transcript-intro.txt"


def main():
    p = Pad(OUT)
    boot_to_field(p)
    for i in range(10):
        o = p.obj()
        p.say("truck", f"({o['x']},{o['y']}) map {p.map_name()} "
                       f"grass={p.grass()} scene={p.scene()}")
        moved, o = p.step("right")
        p.flush_speech(f"right{i + 1}")
        p.say("truck", f"right {'moved' if moved else 'blocked'} -> ({o['x']},{o['y']}) "
                       f"map {p.map_name()} scene {p.scene()}")
        if p.map_name() != "InsideOfTruck":
            break
    p.flush_speech("after")
    st = p.status()
    p.say("status", f"scene {st.get('scene')} message '{(st.get('message') or '')[:100]}'")
    p.say("end", "intro test done")


if __name__ == "__main__":
    main()

"""Phase 1b: explore Route 101 tile by tile until tall grass, pace, get a battle.

Each pad direction is one verified tile (see pad.py). Every step records the
facing probe, so the transcript shows what the layer says as we look around.

Run:  nohup python3 -u artifacts/playtest/run_wild2.py > artifacts/playtest/run_wild2.log 2>&1 &
"""

import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad, boot_to_field   # noqa: E402

OUT = "artifacts/playtest/transcript-walk.txt"
ORDER = ("up", "left", "right", "down")


def look_line(nav):
    look = nav.get("look") or {}
    kind = look.get("kind", "?")
    if kind == "nothing":
        return f"facing {look.get('dir')} nothing"
    return f"facing {look.get('dir')} {kind} at ({look.get('x')},{look.get('y')})"


def main():
    p = Pad(OUT)
    boot_to_field(p)
    p.force_map(0, 16, 10, 18)
    o = p.obj()
    p.say("field", f"map {p.map_name()} ({o['x']},{o['y']}) grass={p.grass()}")

    seen = set()
    for i in range(70):
        if p.scene() == "battle":
            break
        here = (p.obj()["x"], p.obj()["y"])
        moved_any = False
        for d in ORDER:
            moved, o = p.step(d)
            p.flush_speech(f"step{i + 1}{d}")
            if moved:
                seen.add((o["x"], o["y"]))
                p.say("step", f"{d} -> ({o['x']},{o['y']}) "
                              f"{look_line(p.nav())}"
                              f"{' GRASS' if p.grass() else ''}")
                moved_any = True
                break
            p.say("step", f"{d} blocked at ({o['x']},{o['y']})")
        if not moved_any:
            p.say("step", "boxed in")
            break
        if p.scene() == "battle":
            break
        if p.grass():
            p.say("field", "in tall grass: pacing for a wild encounter")
            for _ in range(40):
                for d in ("down", "up"):
                    moved, o = p.step(d)
                    p.flush_speech(f"pace{d}")
                    p.say("pace", f"{d} ({o['x']},{o['y']}) grass={p.grass()}")
                    if p.scene() == "battle":
                        break
                if p.scene() == "battle":
                    break
            break

    p.flush_speech("battle")
    st = p.status()
    p.say("status", f"scene {st.get('scene')} menu {st.get('menu')} "
                    f"battle {st.get('battle')} message '{(st.get('message') or '')[:90]}'")
    p.say("end", "phase 1b done")


if __name__ == "__main__":
    main()

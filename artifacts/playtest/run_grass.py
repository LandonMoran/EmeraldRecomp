"""Phase 3: walk to the nearest tall grass on Route 101 and pace for an encounter.

Proves (or disproves) that wild battles start on this build without going
through the intro, which decides whether the harness needs to grant a starter.

Run:  nohup python3 -u artifacts/playtest/run_grass.py > artifacts/playtest/run_grass.log 2>&1 &
"""

import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad                 # noqa: E402
from mapdata import Layout, ROUTE101  # noqa: E402


def main():
    lay = Layout(ROUTE101)
    p = Pad("artifacts/playtest/transcript-encounter.txt")
    o = p.obj()
    p.say("field", f"({o['x']},{o['y']}) map {p.map_name()} grass={p.grass()}")

    goals = sorted(lay.grass_tiles(), key=lambda t: abs(t[0] - o["x"]) + abs(t[1] - o["y"]))
    plan = lay.path((o["x"], o["y"]), goals[:8])
    p.say("plan", f"{len(plan)} steps to grass: {' '.join(plan)}")
    for i, d in enumerate(plan):
        moved, o = p.step(d)
        p.flush_speech(f"to{i + 1}")
        p.say("walk", f"{d} {'->' if moved else 'blocked at'} ({o['x']},{o['y']}) "
                      f"grass={p.grass()} scene={p.scene()}")
        if not moved:
            p.say("walk", "re-plan")
            plan = lay.path((o["x"], o["y"]), goals[:8])
            if not plan:
                break
        if p.scene() != "overworld":
            break

    for i in range(60):
        if p.scene() == "battle":
            break
        for d in ("down", "up"):
            moved, o = p.step(d)
            p.flush_speech(f"pace{i + 1}{d}")
            p.say("pace", f"{d} ({o['x']},{o['y']}) grass={p.grass()} scene={p.scene()}")
            if p.scene() == "battle":
                break
        if p.scene() == "battle":
            break

    p.flush_speech("battle")
    st = p.status()
    p.say("status", f"scene {st.get('scene')} menu {st.get('menu')} battle {st.get('battle')} "
                    f"msg '{(st.get('message') or '')[:120]}'")
    p.say("end", "phase 3 done")


if __name__ == "__main__":
    main()

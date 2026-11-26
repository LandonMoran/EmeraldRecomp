"""Phase 1c: plan the walk to tall grass from the map data, then pace for a battle.

Run:  nohup python3 -u artifacts/playtest/run_wild3.py > artifacts/playtest/run_wild3.log 2>&1 &
"""

import sys

sys.path.insert(0, "artifacts/playtest")

from pad import Pad, boot_to_field          # noqa: E402
from mapdata import Layout, ROUTE101        # noqa: E402

OUT = "artifacts/playtest/transcript-walk.txt"


def look_line(nav):
    look = nav.get("look") or {}
    kind = look.get("kind", "?")
    if kind == "nothing":
        return f"facing {look.get('dir')} nothing"
    return f"facing {look.get('dir')} {kind} at ({look.get('x')},{look.get('y')})"


def do_step(p, d, tag):
    moved, o = p.step(d)
    p.flush_speech(tag)
    p.say("step", f"{d} {'->' if moved else 'blocked at'} ({o['x']},{o['y']}) "
                  f"{look_line(p.nav())}{' GRASS' if p.grass() else ''}")
    return moved, o


def main():
    lay = Layout(ROUTE101)
    p = Pad(OUT)
    boot_to_field(p)
    p.force_map(0, 16, 10, 18)
    o = p.obj()
    p.say("field", f"map {p.map_name()} ({o['x']},{o['y']}) grass={p.grass()}")

    # The forced load drops us just south of the route proper; step north until
    # we are inside the 20x20 layout so the planner's grid matches the world.
    for i in range(12):
        if 0 <= o["y"] < lay.height:
            break
        moved, o = do_step(p, "up", f"north{i + 1}")
        if not moved:
            break
    p.say("field", f"grid start ({o['x']},{o['y']})")

    steps = lay.path((o["x"], o["y"]), lay.grass_tiles())
    p.say("plan", f"{len(steps)} planned steps to tall grass: {' '.join(steps)}")
    for i, d in enumerate(steps):
        moved, o = do_step(p, d, f"plan{i + 1}")
        if not moved:
            p.say("plan", f"blocked by {d} at ({o['x']},{o['y']}), re-planning")
            steps = lay.path((o["x"], o["y"]), lay.grass_tiles())
            p.say("plan", f"re-plan: {' '.join(steps)}")
            for j, d2 in enumerate(steps):
                moved2, o = do_step(p, d2, f"replan{j + 1}")
                if not moved2:
                    break
            break

    p.say("field", f"arrived ({o['x']},{o['y']}) grass={p.grass()}")

    # Pace in the grass: every step in tall grass rolls for an encounter.
    for i in range(60):
        if p.scene() == "battle":
            break
        for d in ("down", "up"):
            moved, o = do_step(p, d, f"pace{i + 1}{d}")
            if p.scene() == "battle":
                break
        if p.scene() == "battle":
            break

    p.flush_speech("battle")
    st = p.status()
    p.say("status", f"scene {st.get('scene')} menu {st.get('menu')} "
                    f"battle {st.get('battle')} message '{(st.get('message') or '')[:120]}'")
    p.say("end", "phase 1c done")


if __name__ == "__main__":
    main()

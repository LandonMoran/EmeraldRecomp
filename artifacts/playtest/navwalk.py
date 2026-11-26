"""Verified tile navigation: plan from the map data, walk one tile at a time.

The static layout knows hedges; it cannot know about a person standing on a
tile, so a bounce is recorded and the route re-planned around it.
"""

import sys

sys.path.insert(0, "artifacts/playtest")

STEP = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def goto(p, lay, goals, blocked=None, max_steps=80, tag="goto"):
    """Walk to any tile in `goals`. Returns True when one of them is reached."""
    goals = set(goals)
    blocked = set() if blocked is None else blocked
    for i in range(max_steps):
        cur = (p.obj()["x"], p.obj()["y"])
        if cur in goals:
            p.say(tag, f"arrived ({cur[0]},{cur[1]})")
            return True
        plan = lay.path(cur, goals, blocked)
        if not plan:
            p.say(tag, f"no route from ({cur[0]},{cur[1]}) to {sorted(goals)[:4]}")
            return False
        d = plan[0]
        moved, o = p.step(d)
        p.flush_speech(f"{tag}{i + 1}{d}")
        if not moved:
            dx, dy = STEP[d]
            blocked.add((cur[0] + dx, cur[1] + dy))
            p.say(tag, f"{d} blocked at ({o['x']},{o['y']}); re-planning")
            continue
        p.say(tag, f"{d} -> ({o['x']},{o['y']}) map {p.map_name()} scene {p.scene()}")
        if p.scene() != "overworld":
            return True
    return False


OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}
DIRS = ("up", "left", "right", "down")


def explore(p, max_steps=90, tag="explore"):
    """Depth-first walk that learns the real walkable grid as it goes.

    Used where the static layout cannot be trusted (connection strips) or where
    people block the only corridor. Stops as soon as the scene changes, which
    is what happens when a coord-event cutscene fires.
    """
    seen = {}                    # tile -> set of directions already tried
    stack = []                   # path taken, for backtracking
    for i in range(max_steps):
        if p.scene() != "overworld":
            p.say(tag, f"scene changed at step {i} -> {p.scene()}")
            return True
        cur = (p.obj()["x"], p.obj()["y"])
        tried = seen.setdefault(cur, set())
        options = [d for d in DIRS if d not in tried]
        if not options:
            if not stack:
                p.say(tag, f"explored out of moves at {cur}")
                return False
            back = OPPOSITE[stack.pop()]
            moved, o = p.step(back)
            p.flush_speech(f"{tag}{i + 1}back")
            p.say(tag, f"backtrack {back} {'->' if moved else 'blocked at'} ({o['x']},{o['y']})")
            continue
        d = options[0]
        tried.add(d)
        moved, o = p.step(d)
        p.flush_speech(f"{tag}{i + 1}{d}")
        p.say(tag, f"{d} {'->' if moved else 'blocked at'} ({o['x']},{o['y']}) "
                   f"map {p.map_name()} scene {p.scene()}")
        if moved:
            stack.append(d)
    return False

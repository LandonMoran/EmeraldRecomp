"""Walk a gym from its entrance to a list of waypoints, fighting what blocks.

gym_run.py takes a fixed direction string, which is fine for a corridor and
hopeless for a gym whose beams move: one refused step desynchronises the rest of
the route. This walker plans each tile from the map's own blockdata, re-plans
after every step against where the player actually is, treats battles as part of
the route, and records every line the mod speaks.

    python3 artifacts/playtest/gym_walk.py --checkpoint party-lab \
        --map 10,0 --layout MauvilleCity_Gym_Layout --start 4,19 \
        --waypoints "4,17;2,17;2,16;talk:w;2,15;0,15;0,12;4,12;4,10;3,10;3,9" \
        --report mauville-full

Waypoint syntax: ``x,y`` walks to that tile; ``talk:DIR`` turns and presses A
(what starts a trainer battle without stepping into a sight line); ``wait``
runs frames without input.
"""

import argparse
import json
import os
import struct
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import party  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from pad import Pad  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.join(HERE, "reports")
DECOMP = os.path.join(HERE, "..", "..", "third_party", "pokeemerald")

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
BATTLE_PRESS_LIMIT = 160


class ProgressLog(list):
    """Append-only log that also prints, so a long run can be watched live."""

    def append(self, message):
        print(message, flush=True)
        super().append(message)


class Grid:
    """Collision straight from the layout's blockdata (no decomp build needed)."""

    def __init__(self, name):
        path = os.path.join(DECOMP, "data/layouts/layouts.json")
        with open(path, encoding="utf-8") as fh:
            layouts = json.load(fh)["layouts"]
        lay = next(x for x in layouts if x["name"] == name)
        self.width, self.height = lay["width"], lay["height"]
        with open(os.path.join(DECOMP, lay["blockdata_filepath"]), "rb") as fh:
            self.blocks = fh.read()

    def walkable(self, x, y):
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        off = 2 * (x + self.width * y)
        block = struct.unpack("<H", self.blocks[off:off + 2])[0]
        return ((block >> 10) & 3) == 0

    def path(self, start, goal, blocked):
        if start == goal:
            return []
        seen = {start}
        queue = deque([(start, [])])
        while queue:
            (x, y), route = queue.popleft()
            for name, (dx, dy) in DIRS.items():
                nxt = (x + dx, y + dy)
                if nxt in seen or not self.walkable(*nxt):
                    continue
                if nxt in blocked and nxt != goal:
                    continue
                if nxt == goal:
                    return route + [name]
                seen.add(nxt)
                queue.append((nxt, route + [name]))
        return None


def settle(p, log, limit=40):
    presses = 0
    while presses < limit:
        state = p.ask(cmd="emerald_dev_state")
        if (not state.get("message_box") and not state.get("controls_locked")
                and p.status().get("scene") in ("overworld", "menu")):
            break
        p.confirm(40)
        p.flush_speech(f"settle{presses}")
        presses += 1
    log.append(f"settle: {presses} presses, scene {p.status().get('scene')}")
    return presses


def fight_if_needed(p, tag, log):
    """Advance text and fight until the field hands control back.

    A trainer's challenge is dialogue *before* the battle, so pressing A only
    while `scene == battle` leaves the game waiting on the intro and every later
    step is refused. This presses A while a battle, a message box or a locked
    script owns the game, and stops when the field is free again.
    """
    presses = 0
    idle = 0
    last_text = p.status().get("last_print")
    for_text = 0
    while presses < BATTLE_PRESS_LIMIT and idle < 80:
        status = p.status()
        scene = status.get("scene")
        state = p.ask(cmd="emerald_dev_state")
        text = status.get("last_print")
        # A scripted message during a locked sequence does not always raise the
        # engine's message-box flag, but the game is still waiting for A: the
        # field stays locked, so a locked field counts as waiting too. The
        # per-line cap stops that from turning into blind button mashing.
        waiting = (scene == "battle" or state.get("message_box")
                   or state.get("controls_locked"))
        if waiting:
            if text != last_text:
                last_text, for_text = text, 0
            if for_text >= 6:
                p.frames(30)
                idle += 1
                continue
            # A level-up recalculates the mon's stats from its IVs, which would
            # throw away the test stat block mid-battle, so re-apply it before
            # each press. Cheap, and only while a battle or its text owns the
            # game; nothing about the puzzle is touched.
            if scene == "battle":
                party.boost(p)
            p.confirm(40)
            p.flush_speech(f"{tag}-{presses}")
            presses += 1
            for_text += 1
            idle = 0
            continue
        break
    if presses:
        p.frames(45)
        state = p.ask(cmd="emerald_dev_state")
        log.append(f"[{tag}] {presses} presses, scene {p.status().get('scene')}, "
                   f"locked {state.get('controls_locked')}")
    if presses >= BATTLE_PRESS_LIMIT:
        log.append(f"[{tag}] WARNING hit the press limit")
    return presses


def pos_of(p):
    return tuple(p.ask(cmd="emerald_dev_state").get("pos") or ())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--waypoints", required=True)
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    group, num = (int(v) for v in args.map.split(","))
    stem = os.path.splitext(os.path.basename(args.report))[0] if args.report else ""
    report_path = os.path.join(REPORTS, f"{stem}.md") if stem else ""
    if report_path:
        os.makedirs(REPORTS, exist_ok=True)
    p = Pad(report_path.replace(".md", ".txt") if report_path else None)
    log = ProgressLog()

    ck = Checkpoints(conn=p)
    ck.load(args.checkpoint)
    p.frames(30)
    settle(p, log)

    warp = None
    for attempt in range(2):
        reply = p.ask(cmd="emerald_dev_warp", map_group=group, map_num=num,
                      x=int(args.start.split(",")[0]), y=int(args.start.split(",")[1]),
                      facing="north")
        if reply.get("ok") is False:
            log.append(f"warp refused ({attempt}): {reply.get('error')}")
            settle(p, log)
            continue
        for _ in range(160):
            warp = p.ask(cmd="emerald_dev_state").get("warp") or {}
            if warp.get("done"):
                break
            p.frames(5)
        break
    log.append(f"warp: {(warp or {}).get('detail')}")
    if not (warp or {}).get("ok"):
        raise SystemExit("warp failed")

    grid = Grid(args.layout)
    for raw in args.waypoints.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        fight_if_needed(p, "pre", log)

        if raw.startswith("talk:"):
            direction = raw.split(":", 1)[1]
            p.step(direction)          # turns even when the tile is occupied
            p.flush_speech(f"turn-{direction}")
            p.action("confirm")
            p.flush_speech(f"talk-{direction}")
            log.append(f"talk {direction} from {pos_of(p)}")
            fight_if_needed(p, "talk", log)
            continue

        if raw == "wait":
            p.frames(120)
            log.append(f"wait at {pos_of(p)}")
            continue

        gx, gy = (int(v) for v in raw.split(","))
        for attempt in range(4):
            here = pos_of(p)
            route = grid.path(here, (gx, gy), set(p.npc_tiles() or ()))
            if route is None:
                log.append(f"no route {here} -> ({gx},{gy})")
                break
            blocked = False
            for name in route:
                fight_if_needed(p, "walk", log)
                before = pos_of(p)
                p.step(name)
                p.flush_speech(f"{before}-{name}")
                if pos_of(p) == before:
                    state = p.ask(cmd="emerald_dev_state")
                    log.append(f"{before} {name} refused (locked {state.get('controls_locked')}, "
                               f"msgbox {state.get('message_box')}, "
                               f"scene {p.status().get('scene')}); re-planning")
                    blocked = True
                    break
            if not blocked:
                log.append(f"reached {(gx, gy)} after {len(route)} steps")
                break

    fight_if_needed(p, "end", log)
    state = p.ask(cmd="emerald_dev_state")
    log.append(f"end: pos {state.get('pos')} puzzle {state.get('puzzle')}")

    if report_path:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(f"# Gym walk: {args.report}\n\nCheckpoint `{args.checkpoint}`, "
                     f"map [{group},{num}], start ({args.start}).\n\n## Route\n\n")
            for line in log:
                fh.write(f"- {line}\n")
            fh.write("\n## What the mod said\n\n")
            for line in p.lines:
                fh.write(f"    {line}\n")
    for line in log:
        print(line)


if __name__ == "__main__":
    main()

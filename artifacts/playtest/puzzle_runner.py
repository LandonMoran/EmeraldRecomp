"""Puzzle playtest runner for the Emerald accessibility mod.

Two things this file refuses to do, because the whole point of the playtest is
to prove a blind player can win:

  1. It never answers a puzzle from game memory. It only presses buttons, reads
     what the accessibility layer *spoke* (`emerald_a11y_log`) and, separately,
     records developer diagnostics (`emerald_dev_state`) for the report.
  2. It never claims a puzzle passed. The report it writes is raw evidence; the
     PASS / PARTIAL / FAIL status is set by a human reading the transcript
     against the rule in docs/PUZZLE_PLAYTEST.md.

Commands:

    # Create/refresh the per-puzzle starting plans from the decomp inventory.
    python3 artifacts/playtest/puzzle_runner.py --build-plans

    # Warp to a puzzle's start and keep a checkpoint of it.
    python3 artifacts/playtest/puzzle_runner.py --puzzle mauville --start

    # Replay a checkpoint and run a step list, writing a report.
    python3 artifacts/playtest/puzzle_runner.py --puzzle mauville \
        --checkpoint mauville-start --steps "north*3, a, wait:20"

    # Anything ad hoc.
    python3 artifacts/playtest/puzzle_runner.py --warp 10,0,4,17,north --report /tmp/x.md
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcp import Conn  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
PUZZLE_DIR = os.path.join(ROOT, "artifacts/puzzles")
PLAN_DIR = os.path.join(PUZZLE_DIR, "plans")
REPORT_DIR = os.path.join(HERE, "reports")

# The eight gyms, by decomp map name and the short name the docs use. The plan
# builder resolves each one's interior entry tile from the warps that point at
# it, so the starting save is the same tile the game itself lands on.
GYMS = [
    ("RustboroCity_Gym", "rustboro"),
    ("DewfordTown_Gym", "dewford"),
    ("MauvilleCity_Gym", "mauville"),
    ("LavaridgeTown_Gym_1F", "lavaridge"),
    ("PetalburgCity_Gym", "petalburg"),
    ("FortreeCity_Gym", "fortree"),
    ("MossdeepCity_Gym", "mossdeep"),
    ("SootopolisCity_Gym_1F", "sootopolis"),
]

DIRECTIONS = ("north", "south", "east", "west")


def load_maps():
    with open(os.path.join(PUZZLE_DIR, "maps.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_plans():
    """Entry tiles for each gym, resolved from the warps that lead into it."""
    data = load_maps()
    by_name = {m["name"]: m for m in data["maps"]}
    by_id = {m["id"]: m for m in data["maps"] if m.get("id")}
    os.makedirs(PLAN_DIR, exist_ok=True)
    written = []
    for map_name, slug in GYMS:
        gym = by_name.get(map_name)
        if not gym:
            continue
        entry = None
        # Which exterior map warps into this gym, and through which door?
        for source in data["maps"]:
            for warp in source["warps"]:
                if warp.get("dest_map") != gym["id"]:
                    continue
                door = int(warp.get("dest_warp_id") or 0)
                if door < len(gym["warps"]):
                    inside = gym["warps"][door]
                    entry = {
                        "from_map": source["name"],
                        "from_xy": [warp["x"], warp["y"]],
                        "map": map_name,
                        "map_group": gym["group"],
                        "map_num": gym["num"],
                        "x": inside["x"],
                        "y": inside["y"],
                        "elevation": inside["elevation"],
                    }
                    break
            if entry:
                break
        plan = {
            "puzzle": slug,
            "map": map_name,
            "map_group": gym["group"],
            "map_num": gym["num"],
            "layout": gym["layout"],
            "size": [gym["width"], gym["height"]],
            "start": entry,
            "triggers": gym["triggers"],
            "warps": gym["warps"],
            "script_hooks": gym["scripts"],
            # Filled in by a playtest; the runner refuses to run without one.
            "facing": None,
            "steps": [],
            "status": "NOT TESTED",
        }
        path = os.path.join(PLAN_DIR, slug + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=1)
        written.append(path)
    print(f"wrote {len(written)} plans to {PLAN_DIR}")
    for path in written:
        print(" ", os.path.relpath(path, ROOT))


class Runner:
    def __init__(self, port=19892):
        self.conn = Conn(port=port)
        self.cp = Checkpoints(port=port, conn=self.conn)
        self.log_index = 0
        self.start_state = None   # captured before the first action
        self.locked = False       # a script or battle took the field mid-route
        self.events = []      # (kind, frame, text)

    # ── transport ────────────────────────────────────────────────────────
    def ask(self, **kw):
        return self.conn.ask(**kw)

    def frames(self, n):
        self.ask(cmd="run_frames", n=n)

    def state(self):
        return self.ask(cmd="emerald_dev_state")

    def nav(self):
        return self.ask(cmd="emerald_a11y_nav")

    def status(self):
        return self.ask(cmd="emerald_a11y_status")

    # ── speech (accessibility only) ──────────────────────────────────────
    def utterances(self):
        reply = self.ask(cmd="emerald_a11y_log")
        rows = reply.get("utterances") or []
        new = [r for r in rows if r.get("seq", 0) > self.log_index]
        if new:
            self.log_index = max(r.get("seq", 0) for r in new)
        for row in new:
            self.events.append(("speech", row.get("frame"), row.get("text", "")))
        return new

    def drain(self, tag=""):
        out = []
        for row in self.utterances():
            out.append(row.get("text", ""))
        return out

    # ── actions ──────────────────────────────────────────────────────────
    def action(self, name, frames=6):
        self.ask(cmd="emerald_a11y_action", action=name)
        self.frames(frames)

    def step(self, direction, settle=52):
        before = self.state()
        self.action(direction, 0)
        self.frames(settle)
        after = self.state()
        moved = before.get("pos") != after.get("pos")
        spoken = self.drain()
        # A locked field (script, cutscene, trainer battle) swallows every press.
        # Record it and stop the route instead of grinding steps into a lock.
        locked = bool(after.get("controls_locked")) and not moved
        if locked:
            self.locked = True
        self.events.append(("action", 0,
                            f"{direction} -> {after.get('pos')} "
                            f"facing {after.get('object', {}).get('facing')} "
                            f"{'moved' if moved else 'blocked'}"
                            f"{' (field locked: script or battle)' if locked else ''}"))
        return moved, after, spoken

    def run_steps(self, steps):
        for token in [s.strip() for s in steps.split(",") if s.strip()]:
            if token.startswith("wait:"):
                self.frames(int(token.split(":", 1)[1]))
                self.drain()
                continue
            count = 1
            if "*" in token:
                token, n = token.split("*", 1)
                count = int(n)
            if token in DIRECTIONS:
                for _ in range(count):
                    if self.locked:
                        self.events.append(("note", 0, "route stopped: field locked"))
                        break
                    self.step(token)
                continue
            if token in ("a", "b", "start", "up", "down", "left", "right",
                         "confirm", "cancel"):
                name = {"a": "confirm", "b": "cancel"}.get(token, token)
                for _ in range(count):
                    self.action(name, 30)
                    self.drain()
                continue
            raise SystemExit(f"unknown step {token!r}")

    # ── warp ─────────────────────────────────────────────────────────────
    def warp(self, group, num, x, y, facing=None, timeout=30.0):
        req = {"cmd": "emerald_dev_warp", "map_group": group, "map_num": num,
               "x": x, "y": y}
        if facing:
            req["facing"] = facing
        reply = self.ask(**req)
        if not reply.get("ok"):
            raise RuntimeError(f"warp refused: {reply.get('error')}")
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.frames(20)
            state = self.state()
            warp = state.get("warp") or {}
            if warp.get("done"):
                self.drain()
                if not warp.get("ok"):
                    raise RuntimeError(f"warp failed: {warp.get('detail')}")
                return state
        raise RuntimeError("warp timed out")

    # ── report ───────────────────────────────────────────────────────────
    def report(self, title, plan=None, extra=None):
        st = self.state()
        start = self.start_state or st
        nav = self.nav()
        puzzle = st.get("puzzle") or {}
        lines = [f"# {title}", "",
                 f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
                 "",
                 "## Starting state", "",
                 f"- Map: `{start.get('location', {}).get('map')}` "
                 f"({(start.get('puzzle') or {}).get('map')})",
                 f"- Position: `{start.get('pos')}` facing "
                 f"`{(start.get('object') or {}).get('facing')}`",
                 f"- Terrain underfoot / ahead: `{puzzle.get('underfoot')}` / "
                 f"`{puzzle.get('facing')}`",
                 f"- Trigger tiles: {puzzle.get('triggers')}, nearest "
                 f"{puzzle.get('trigger_dist')} at "
                 f"({puzzle.get('trigger_dx')},{puzzle.get('trigger_dy')})",
                 "",
                 "## Accessibility announcements (spoken by the mod)", ""]
        said = [e for e in self.events if e[0] == "speech"]
        if said:
            for _, frame, text in said:
                lines.append(f"- `f{frame}` {text}")
        else:
            lines.append("- (none)")
        lines += ["", "## Final state (developer diagnostic, never spoken)", "",
                  f"- Position: `{st.get('pos')}` facing "
                  f"`{(st.get('object') or {}).get('facing')}` "
                  f"controls_locked={st.get('controls_locked')}",
                  "", "## Developer diagnostics (never spoken)", "",
                  "```json", json.dumps(st, indent=1)[:6000], "```", "",
                  "## Navigation state", "", "```json",
                  json.dumps(nav, indent=1)[:4000], "```", ""]
        if plan:
            lines += ["## Plan", "", "```json", json.dumps(plan, indent=1)[:3000],
                      "```", ""]
        if extra:
            lines += ["## Notes", "", extra, ""]
        os.makedirs(REPORT_DIR, exist_ok=True)
        path = os.path.join(REPORT_DIR, title.lower().replace(" ", "-") + ".md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(path)
        return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=19892)
    ap.add_argument("--build-plans", action="store_true")
    ap.add_argument("--puzzle", help="plan slug, e.g. mauville")
    ap.add_argument("--start", action="store_true",
                    help="warp to the puzzle's plan start and checkpoint it")
    ap.add_argument("--checkpoint", help="load this checkpoint first")
    ap.add_argument("--save-checkpoint", help="save a checkpoint under this name")
    ap.add_argument("--warp", help="g,n,x,y[,facing]")
    ap.add_argument("--steps", default="")
    ap.add_argument("--report", help="report title")
    args = ap.parse_args()

    if args.build_plans:
        build_plans()
        return

    plan = None
    if args.puzzle:
        path = os.path.join(PLAN_DIR, args.puzzle + ".json")
        if not os.path.exists(path):
            raise SystemExit(f"no plan for {args.puzzle!r}; run --build-plans")
        with open(path, "r", encoding="utf-8") as fh:
            plan = json.load(fh)

    r = Runner(port=args.port)
    if args.checkpoint:
        r.cp.load(args.checkpoint)

    if plan and args.start:
        start = plan.get("start")
        if not start:
            raise SystemExit("plan has no resolved entry tile")
        state = r.warp(plan["map_group"], plan["map_num"], start["x"], start["y"],
                       plan.get("facing"))
        name = f"{args.puzzle}-start"
        r.cp.save(name, note=f"{plan['map']} entry tile {start['x']},{start['y']}")
        print(json.dumps(state, indent=1))
        return

    if args.warp:
        parts = [p.strip() for p in args.warp.split(",")]
        group, num, x, y = (int(p) for p in parts[:4])
        facing = parts[4] if len(parts) > 4 else None
        print(json.dumps(r.warp(group, num, x, y, facing), indent=1))

    if args.steps:
        r.start_state = r.state()
        r.run_steps(args.steps)

    if args.save_checkpoint:
        r.cp.save(args.save_checkpoint)

    if args.report:
        r.report(args.report, plan=plan)


if __name__ == "__main__":
    main()

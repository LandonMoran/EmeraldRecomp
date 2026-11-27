"""Load a checkpoint and play a gym route, battles included.

puzzle_runner.py stops the moment the field reports ``locked``; that is right for
a switch test and useless for a whole gym, because every gym puts trainers
between the door and the puzzle. This runner treats a battle as part of the
route: it presses A (the battle opens on FIGHT / the first move) until the field
comes back, then carries on walking. It only ever drives the pad, and it records
what the mod said, so a puzzle solved through it was still solved by ear.

    python3 artifacts/playtest/gym_run.py --checkpoint party-ready \
        --map 10,0 --x 4 --y 19 --facing north --route "up*7" --report mauville-gym

A checkpoint with a party is required; party.py can prepare one.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from checkpoints import Checkpoints  # noqa: E402
from pad import Pad  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.join(HERE, "reports")
BATTLE_PRESS_LIMIT = 220


def parse_route(text):
    steps = []
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        name, _, count = part.partition("*")
        steps.extend([name] * int(count or 1))
    return steps


def wait_warp(p):
    for _ in range(160):
        warp = (p.ask(cmd="emerald_dev_state").get("warp") or {})
        if warp.get("done"):
            return warp
        p.frames(5)
    raise SystemExit("warp did not finish within 13 s")


def settle(p, log, limit=40):
    """Finish whatever text or script the checkpoint was saved inside.

    A checkpoint taken mid-dialogue resumes with the box open, and the dev warp
    refuses to load a map out from under a message box on purpose. Pressing A
    until the field hands control back is exactly what a player would do.
    """
    presses = 0
    while presses < limit:
        state = p.ask(cmd="emerald_dev_state")
        scene = p.status().get("scene")
        if (not state.get("message_box") and not state.get("controls_locked")
                and scene in ("overworld", "menu")):
            break
        p.confirm(40)
        p.flush_speech(f"settle{presses}")
        presses += 1
    log.append(f"settle: {presses} presses, scene {p.status().get('scene')}")
    return presses


def fight_if_needed(p, tag, log):
    presses = 0
    while p.status().get("scene") == "battle" and presses < BATTLE_PRESS_LIMIT:
        p.confirm(40)
        p.flush_speech(f"{tag}-battle")
        presses += 1
    if presses:
        log.append(f"[{tag}] battle: {presses} presses, "
                   f"scene now {p.status().get('scene')}")
    if presses >= BATTLE_PRESS_LIMIT:
        raise SystemExit(f"{tag}: battle did not end in {BATTLE_PRESS_LIMIT} presses")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--map", required=True, help="map_group,map_num")
    ap.add_argument("--x", type=int, required=True)
    ap.add_argument("--y", type=int, required=True)
    ap.add_argument("--facing", default="north")
    ap.add_argument("--route", default="", help='e.g. "up*4,left*3,confirm"')
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    group, num = (int(v) for v in args.map.split(","))
    report_path = os.path.join(REPORTS, f"{args.report}.md") if args.report else ""
    if report_path:
        os.makedirs(REPORTS, exist_ok=True)
    p = Pad(report_path.replace(".md", ".txt") if report_path else None)

    ck = Checkpoints(conn=p)
    loaded = ck.load(args.checkpoint)
    log = [f"checkpoint {args.checkpoint}: {loaded}"]
    p.frames(30)
    settle(p, log)

    reply = p.ask(cmd="emerald_dev_warp", map_group=group, map_num=num,
                  x=args.x, y=args.y, facing=args.facing)
    if reply.get("ok") is False:
        raise SystemExit(f"warp refused: {reply.get('error')}")
    warp = wait_warp(p)
    log.append(f"warp: {warp.get('detail')} (ok={warp.get('ok')})")
    if not warp.get("ok"):
        raise SystemExit("warp failed: " + str(warp.get("detail")))

    for i, step in enumerate(parse_route(args.route)):
        fight_if_needed(p, f"step{i}", log)
        if step in ("up", "down", "left", "right"):
            moved, obj = p.step(step)
            p.flush_speech(f"{i}-{step}")
            state = p.ask(cmd="emerald_dev_state")
            log.append(f"[{i}] {step} moved={moved} pos={state.get('pos')} "
                       f"map={state.get('location', {}).get('map')}")
        else:
            p.action(step)
            p.flush_speech(f"{i}-{step}")
            log.append(f"[{i}] {step}")

    fight_if_needed(p, "end", log)
    state = p.ask(cmd="emerald_dev_state")
    st = p.status()
    log.append(f"end: pos {state.get('pos')} map {state.get('location', {}).get('map')} "
               f"scene {st.get('scene')} puzzle {state.get('puzzle')}")

    if report_path:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(f"# Gym run: {args.report}\n\nroute `{args.route}` on map "
                     f"[{group},{num}] from ({args.x},{args.y})\n\n")
            for line in log:
                fh.write(f"- {line}\n")
            fh.write("\n## What the mod said\n\n")
            for line in p.lines:
                fh.write(f"    {line}\n")
    for line in log:
        print(line)


if __name__ == "__main__":
    main()

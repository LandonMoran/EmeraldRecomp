"""Explore Lavaridge Gym with only what the mod says.

No map data is used to navigate: one step is taken at a time and the new
position/map comes from the game, while the spoken line for each step is
recorded. The graph is therefore exactly what a blind player could learn, and
the pits show up as edges that change the map instead of the tile.

    python3 artifacts/playtest/lavaridge_walk.py --budget 260
"""

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from checkpoints import Checkpoints  # noqa: E402
from pad import Pad  # noqa: E402

REPORTS = os.path.join(HERE, "reports")
DIRS = [("up", 0, -1), ("right", 1, 0), ("down", 0, 1), ("left", -1, 0)]
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}
# The two town doors: stepping on them leaves the gym, and the exploration has
# nothing to learn out there.
SKIP = {((4, 1), 13, 18), ((4, 1), 14, 18)}


class Shim:
    def __init__(self, pad):
        self.p = pad

    def ask(self, **kw):
        return self.p.ask(**kw)


def here(p):
    o = p.obj()
    return (tuple(p.map()), o["x"] - 7, o["y"] - 7)


def say(p):
    st = p.status()
    return st.get("message") or st.get("status") or ""


def settle(p, log):
    for i in range(40):
        st = p.ask(cmd="emerald_dev_state")
        if (p.status().get("scene") == "overworld" and not st.get("message_box")
                and not st.get("controls_locked")):
            return
        p.confirm(40)
        p.flush_speech("settle%d" % i)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=260)
    ap.add_argument("--report", default="lavaridge-walk")
    args = ap.parse_args()

    p = Pad(transcript=os.path.join(REPORTS, args.report + ".txt"))
    cps = Checkpoints(conn=Shim(p))
    cps.load("lavaridge-gym")
    settle(p, log := [])

    edges = {}          # (map, x, y, dir) -> (map, x, y) | "blocked"
    seen = collections.OrderedDict()
    steps = 0
    log.append("start %s | %s" % (here(p), say(p)))

    def probe_and_walk():
        nonlocal steps
        # depth-first: walk to the closest unseen tile, then try every direction
        import heapq
        start = here(p)
        dist = {start: 0}
        prev = {start: None}
        q = collections.deque([start])
        while q:
            cur = q.popleft()
            for d, dx, dy in DIRS:
                tgt = edges.get((cur[0], cur[1], cur[2], d))
                if not tgt or tgt == "blocked" or tgt in dist:
                    continue
                dist[tgt] = dist[cur] + 1
                prev[tgt] = (cur, d)
                q.append(tgt)
        frontier = [t for t in dist if t not in seen]
        if not frontier:
            return False
        goal = min(frontier, key=lambda t: dist[t])
        path = []
        node = goal
        while prev[node] is not None:
            node, d = prev[node]
            path.append(d)
        for d in reversed(path):
            moved, o = p.step(d)
            steps += 1
            p.flush_speech("walk%d" % steps)
            log.append("walk %-5s -> %s | %s" % (d, here(p), say(p)))
        pos = here(p)
        seen[pos] = True
        for d, dx, dy in DIRS:
            if (pos[0], pos[1], pos[2], d) in edges:
                continue
            if (pos[0], pos[1] + dx, pos[2] + dy) in SKIP:
                edges[(pos[0], pos[1], pos[2], d)] = "blocked"
                log.append("skip %-5s at %s (town door)" % (d, pos))
                continue
            before = here(p)
            moved, o = p.step(d)
            steps += 1
            p.flush_speech("probe%d" % steps)
            after = here(p)
            line = say(p)
            if after == before:
                edges[(pos[0], pos[1], pos[2], d)] = "blocked"
                log.append("probe %-5s at %s BLOCKED | %s" % (d, pos, line))
            else:
                edges[(pos[0], pos[1], pos[2], d)] = after
                edges.setdefault((after[0], after[1], after[2], OPPOSITE[d]), before)
                log.append("probe %-5s at %s -> %s | %s" % (d, pos, after, line))
                # walk straight back
                p.step(OPPOSITE[d])
                steps += 1
                p.flush_speech("back%d" % steps)
                if here(p) != before:
                    log.append("  !! could not walk back: now %s" % (here(p),))
                    return True
        return True

    while steps < args.budget:
        if not probe_and_walk():
            break
        for i in range(30):
            if p.status().get("scene") == "overworld":
                break
            p.confirm(30)
            p.flush_speech("battle%d" % i)

    log.append("end %s" % (here(p),))
    with open(os.path.join(REPORTS, args.report + ".graph.json"), "w") as fh:
        json.dump({"edges": {"|".join(map(str, k)): (v if v == "blocked" else list(v[0]) + list(v[1:]))
                             for k, v in edges.items()}, "steps": steps}, fh, indent=1)
    with open(os.path.join(REPORTS, args.report + ".log"), "w") as fh:
        fh.write("\n".join(log) + "\n")
    print("\n".join(log[-40:]))
    print("tiles seen:", len(seen), "edges:", len(edges), "steps:", steps)


if __name__ == "__main__":
    main()

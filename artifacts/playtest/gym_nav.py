"""Blind-navigation bookkeeping for gym puzzles.

The mod speaks; this only holds the pad and remembers which tiles touch which.
A tile is "open" in a direction when a step actually changes the player tile,
which is the harness's way of hearing the silence that follows a successful
step (the mod says `Blocked north.` only for a refused one, once per tile).

The graph is keyed by map id and tile so it survives across runs:

    python3 - <<'EOF'
    from gym_nav import Nav
    nav = Nav(pad)
    nav.explore(budget=60)
    nav.goto(8, 9)
    EOF
"""

import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAP_PATH = os.path.join(HERE, "gym-map.json")
LOG_PATH = os.path.join(HERE, "game.log")

DIRS = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


class Nav:
    def __init__(self, pad, home=None):
        self.p = pad
        self.speech = []
        self.mark = os.path.getsize(LOG_PATH) if os.path.exists(LOG_PATH) else 0
        self.map_id = None
        self.graph = {}          # "x,y" -> {dir: [nx, ny]}
        self.banned = set()      # tiles that warp out of the map being mapped
        self.home = home         # (group, num) to return to after an accidental warp
        self.home_key = "%d,%d" % home if home else None
        self.load()

    # ── io ───────────────────────────────────────────────────────────────
    def load(self):
        if not os.path.exists(MAP_PATH):
            return
        try:
            with open(MAP_PATH) as f:
                blob = json.load(f)
        except (ValueError, OSError):
            return
        self.by_map = blob
        d = self.state()
        key = self.map_key(d)
        self.map_id = key
        self.graph = {k: {dd: tuple(v) for dd, v in dirs.items()}
                      for k, dirs in blob.get(key, {}).items()}

    def save(self):
        if self.map_id is None:
            return
        blob = {}
        if os.path.exists(MAP_PATH):
            try:
                with open(MAP_PATH) as f:
                    blob = json.load(f)
            except (ValueError, OSError):
                blob = {}
        blob[self.map_id] = {k: {dd: list(v) for dd, v in dirs.items()}
                             for k, dirs in self.graph.items()}
        with open(MAP_PATH, "w") as f:
            json.dump(blob, f, indent=1, sort_keys=True)

    # ── engine ───────────────────────────────────────────────────────────
    def state(self):
        return self.p.ask(cmd="emerald_dev_state")

    def pos(self):
        d = self.state()
        return tuple(d.get("pos") or (0, 0))

    def map_key(self, d=None):
        d = d or self.state()
        m = (d.get("location") or {}).get("map") \
            or (d.get("nav") or {}).get("map") or [0, 0]
        return "%d,%d" % (m[0], m[1])

    def frames(self, n):
        while n > 0:
            k = min(n, 300)
            self.p.frames(k)
            n -= k

    def hear(self):
        """Everything the mod said since the last call."""
        if not os.path.exists(LOG_PATH):
            return []
        with open(LOG_PATH) as f:
            f.seek(self.mark)
            data = f.read()
            self.mark = f.tell()
        out = []
        for line in data.splitlines():
            if "] speak!: " in line:
                out.append(line.split("] speak!: ")[-1])
            elif "] speak: " in line:
                out.append(line.split("] speak: ")[-1])
        out = [x for x in out if x.strip()]
        self.speech.extend(out)
        return out

    # ── movement ─────────────────────────────────────────────────────────
    def unlocked(self, tries=10):
        """A press during a script or a transition is swallowed, not refused."""
        for _ in range(tries):
            if not self.state().get("controls_locked"):
                return True
            self.frames(60)
        return False

    def step(self, direction, frames=45, retries=2):
        """A tap that neither moves nor speaks was swallowed; try again."""
        for attempt in range(retries + 1):
            self.unlocked()
            before = self.pos()
            self.p.step(direction)
            self.frames(frames)
            after = self.pos()
            said = self.hear()
            if after != before or said:
                return after, after != before, said
            self.frames(90)
        return self.pos(), False, []

    def probe(self, direction):
        """Try one step from here; record the edge in the graph."""
        here = self.pos()
        after, moved, said = self.step(direction)
        if self.home_key and self.map_key() != self.home_key:
            # A door: put the puzzle back the way it was and stop probing here.
            self.banned.add("%d,%d" % here)
            self.p.force_map(self.home[0], self.home[1], here[0], here[1])
            self.frames(300)
            self.hear()
            return here, False, said
        node = self.graph.setdefault("%d,%d" % here, {})
        if moved:
            node[direction] = after
            back = OPPOSITE[direction]
            self.graph.setdefault("%d,%d" % after, {})[back] = here
        self.save()
        return after if moved else here, moved, said

    def go(self, direction):
        """Walk one known-open edge."""
        here = self.pos()
        after, moved, said = self.step(direction)
        if not moved:
            print("  expected open %s from %s, refused by the game" % (direction, here),
                  flush=True)
        return after, moved, said

    # ── exploration ──────────────────────────────────────────────────────
    def explore(self, budget=60, quiet=True):
        """Depth-first over unknown tiles; runs the pad until the budget is spent."""
        visited = {"%d,%d" % self.pos()}
        stack = [self.pos()]
        steps = 0
        while stack and steps < budget:
            cur = stack[-1]
            if self.pos() != cur:
                stack.append(self.pos())
                cur = self.pos()
            advanced = False
            for d in ("up", "right", "down", "left"):
                nx = (cur[0] + DIRS[d][0], cur[1] + DIRS[d][1])
                if "%d,%d" % nx in visited or "%d,%d" % cur in self.banned:
                    continue
                after, moved, said = self.probe(d)
                steps += 1
                if said and not quiet:
                    print("  %s %s -> %s: %s" % (after if moved else cur, d,
                                                 after, " | ".join(said)), flush=True)
                if moved:
                    visited.add("%d,%d" % after)
                    stack.append(after)
                    advanced = True
                    break
                if steps >= budget:
                    break
            if not advanced:
                stack.pop()
                if stack:
                    tgt = stack[-1]
                    c = self.pos()
                    dx, dy = tgt[0] - c[0], tgt[1] - c[1]
                    if dx or dy:
                        d = "right" if dx > 0 else "left" if dx < 0 else \
                            "down" if dy > 0 else "up"
                        self.step(d, 35)
                        self.hear()
        self.save()
        return len(visited)

    # ── pathing ──────────────────────────────────────────────────────────
    def path(self, target, start=None):
        start = start or self.pos()
        s, t = "%d,%d" % start, "%d,%d" % target
        if s == t:
            return []
        seen = {s: None}
        queue = [s]
        while queue:
            cur = queue.pop(0)
            if cur == t:
                break
            for direction, nxt in self.graph.get(cur, {}).items():
                k = "%d,%d" % nxt
                if k in seen:
                    continue
                seen[k] = (cur, direction)
                queue.append(k)
        if t not in seen:
            return None
        steps = []
        cur = t
        while seen[cur]:
            prev, direction = seen[cur]
            steps.append(direction)
            cur = prev
        return list(reversed(steps))

    def goto(self, target, speak=True):
        route = self.path(target)
        if route is None:
            return False
        for d in route:
            _, moved, said = self.go(d)
            if speak and said:
                print("  " + " | ".join(said), flush=True)
            if not moved:
                return False
        return True

    def settle(self, frames=120):
        self.frames(frames)
        said = self.hear()
        if said:
            print("  " + " | ".join(said), flush=True)
        return said

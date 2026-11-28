"""Named checkpoint manager for puzzle playtests.

A checkpoint is the engine's own machine snapshot — the same `savestate_save`
blob the F1..F9 slots use (see gbarecomp/TCP.md) — plus a JSON sidecar that
records where it was taken and what the puzzle state was, so a failure can be
reproduced instead of rediscovered.

What it never does:
  * touch the player's `.sav` (the cartridge save) — checkpoints live under
    artifacts/playtest/checkpoints/ and are developer files;
  * touch the nine numbered state slots;
  * claim a save happened without the engine confirming it (every call checks
    the `ok` field of the reply).

Usage:
    python3 artifacts/playtest/checkpoints.py list
    python3 artifacts/playtest/checkpoints.py save mauville-before
    python3 artifacts/playtest/checkpoints.py load mauville-before
    python3 artifacts/playtest/checkpoints.py show mauville-before
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcp import Conn  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
CHECKPOINT_DIR = os.path.join(HERE, "checkpoints")

# Puzzle variables worth recording alongside a checkpoint. These are the
# decompilation's own names; the ids are read from artifacts/puzzles/vars.json
# (generated from the decomp) so no numeric guess is baked in here.
VARS_OF_INTEREST = (
    "VAR_MAUVILLE_GYM_STATE",
    "VAR_PETALBURG_GYM_STATE",
    "VAR_FORTREE_GYM_STATE",
    "VAR_MOSSDEEP_GYM_STATE",
    "VAR_SOOTOPOLIS_GYM_STATE",
    "VAR_LAVARIDGE_GYM_STATE",
    "VAR_DEWFORD_GYM_STATE",
    "VAR_RUSTBORO_GYM_STATE",
    "VAR_TEMP_0",
    "VAR_TEMP_1",
)

FLAGS_OF_INTEREST = (
    "FLAG_MAUVILLE_GYM_BARRIERS_STATE",
    "FLAG_DEFEATED_MAUVILLE_GYM",
    "FLAG_DEFEATED_PETALBURG_GYM",
    "FLAG_DEFEATED_FORTREE_GYM",
    "FLAG_DEFEATED_MOSSDEEP_GYM",
    "FLAG_DEFEATED_SOOTOPOLIS_GYM",
    "FLAG_DEFEATED_LAVARIDGE_GYM",
    "FLAG_DEFEATED_DEWFORD_GYM",
    "FLAG_DEFEATED_RUSTBORO_GYM",
    "FLAG_BADGE01_GET",
    "FLAG_BADGE02_GET",
    "FLAG_BADGE03_GET",
    "FLAG_BADGE04_GET",
    "FLAG_BADGE05_GET",
    "FLAG_BADGE06_GET",
    "FLAG_BADGE07_GET",
    "FLAG_BADGE08_GET",
)


def variable_ids():
    """{name: id} from artifacts/puzzles/variables.json, when generated."""
    path = os.path.join(ROOT, "artifacts/puzzles/variables.json")
    if not os.path.exists(path):
        return {}, {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("vars", {}), data.get("flags", {})


def slug(name):
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in name)


class Checkpoints:
    def __init__(self, port=19892, state_dir=CHECKPOINT_DIR, conn=None):
        # The debug server serves one session at a time, so a caller that
        # already holds a connection must hand it over instead of opening a
        # second socket (which simply never answers).
        self.conn = conn or Conn(port=port)
        self.dir = state_dir
        os.makedirs(self.dir, exist_ok=True)

    # ── paths ────────────────────────────────────────────────────────────
    def paths(self, name):
        base = os.path.join(self.dir, slug(name))
        return base + ".state", base + ".json"

    def names(self):
        out = []
        for entry in sorted(os.listdir(self.dir)):
            if entry.endswith(".state"):
                out.append(entry[: -len(".state")])
        return out

    # ── state ────────────────────────────────────────────────────────────
    def state(self):
        return self.conn.ask(cmd="emerald_dev_state")

    def puzzle_snapshot(self):
        """Puzzle variables and flags, by decomp name."""
        st = self.state()
        vars_by_name, flags_by_name = variable_ids()
        wanted_vars = {name: vars_by_name[name] for name in VARS_OF_INTEREST
                       if name in vars_by_name}
        wanted_flags = {name: flags_by_name[name] for name in FLAGS_OF_INTEREST
                        if name in flags_by_name}
        values = {}
        for name, var_id in wanted_vars.items():
            values["var:" + name] = self.conn.ask(cmd="emerald_dev_var", id=var_id).get("value")
        for name, flag_id in wanted_flags.items():
            values["flag:" + name] = self.conn.ask(cmd="emerald_dev_flag", id=flag_id).get("value")
        return values

    # ── save / load ──────────────────────────────────────────────────────
    def save(self, name, note=""):
        state_path, meta_path = self.paths(name)
        state = self.state()
        if not state.get("ok"):
            raise RuntimeError(f"cannot checkpoint: {state}")
        reply = self.conn.ask(cmd="savestate_save", path=os.path.abspath(state_path))
        if not reply.get("ok"):
            raise RuntimeError(f"savestate_save refused: {reply.get('error')}")
        meta = {
            "name": name,
            "note": note,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "map": state.get("pos") and state.get("location", {}).get("map"),
            "pos": state.get("pos"),
            "location": state.get("location"),
            "object": state.get("object"),
            "puzzle": state.get("puzzle"),
            "state": self.puzzle_snapshot(),
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=1)
        return meta

    def load(self, name):
        state_path, _ = self.paths(name)
        if not os.path.exists(state_path):
            raise RuntimeError(f"no checkpoint named {name!r}")
        reply = self.conn.ask(cmd="savestate_load", path=os.path.abspath(state_path))
        if not reply.get("ok"):
            raise RuntimeError(f"savestate_load refused: {reply.get('error')}")
        return self.state()

    def show(self, name):
        _, meta_path = self.paths(name)
        if not os.path.exists(meta_path):
            raise RuntimeError(f"no checkpoint named {name!r}")
        with open(meta_path, "r", encoding="utf-8") as fh:
            return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["list", "save", "load", "show"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--note", default="")
    ap.add_argument("--port", type=int, default=19892)
    args = ap.parse_args()

    cp = Checkpoints(port=args.port)
    if args.action == "list":
        for name in cp.names():
            meta = cp.show(name)
            print(f"{name:32s} {meta.get('map')} {meta.get('pos')} {meta.get('note')}")
    elif args.action == "save":
        meta = cp.save(args.name, args.note)
        print(json.dumps(meta, indent=1))
    elif args.action == "load":
        print(json.dumps(cp.load(args.name), indent=1))
    else:
        print(json.dumps(cp.show(args.name), indent=1))


if __name__ == "__main__":
    main()

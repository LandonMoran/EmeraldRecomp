#!/usr/bin/env python3
"""Inventory Emerald's maps and puzzles straight from the decompilation.

Why: the accessibility playtest needs one authoritative table of map group /
map number / layout / trigger tiles for every puzzle, so a save can be created
and a warp issued without guessing. The decomp is used read-only; only facts
(names, ids, counts, script names) enter the generated JSON, which the harness
reads.

    python3 tools/puzzle_inventory.py --decomp /path/to/pokeemerald \
        --out artifacts/puzzles

Outputs:
  maps.json       every map: group, number, layout, size, script hooks,
                  warps, trigger (coord) events, background events
  inventory.json  the subset that can block progression, with the puzzle
                  metadata the playtest documents reference
"""

import argparse
import json
import os
import re
import sys

# Maps whose geometry, terrain or scripted barriers gate progress. Verified
# names from data/maps/ in the pinned decomp revision (c2dcc629).
PUZZLE_PREFIXES = (
    "RustboroCity_Gym",
    "DewfordTown_Gym",
    "MauvilleCity_Gym",
    "LavaridgeTown_Gym",
    "PetalburgCity_Gym",
    "FortreeCity_Gym",
    "MossdeepCity_Gym",
    "SootopolisCity_Gym",
    "SeafloorCavern",
    "SkyPillar",
    "VictoryRoad",
    "CaveOfOrigin",
    "ShoalCave",
    "ScorchedSlab",
    "AquaHideout",
    "MagmaHideout",
    "NewMauville",
    "AbandonedShip",
    "TrickHouse",
    "MtPyre",
    "DesertRuins",
    "IslandCave",
    "AncientTomb",
    "MirageTower",
    "ArtisanCave",
    "AlteringCave",
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def group_table(decomp):
    """[(group_index, num, map_name)] from map_groups.json."""
    data = load_json(os.path.join(decomp, "data/maps/map_groups.json"))
    order = data.get("group_order", [])
    out = []
    for group_index, group_name in enumerate(order):
        entries = data.get(group_name)
        if entries is None:
            continue
        # The file lists maps in order; older revisions use {"maps": [...]}.
        if isinstance(entries, dict):
            entries = entries.get("maps", [])
        for num, name in enumerate(entries):
            out.append((group_index, num, name))
    return out, order


def layouts(decomp):
    path = os.path.join(decomp, "data/layouts/layouts.json")
    if not os.path.exists(path):
        return {}
    data = load_json(path)
    out = {}
    items = data.get("layouts") or data.get("layouts_table_labels") or []
    if isinstance(data, dict) and isinstance(items, list):
        for row in items:
            # map.json refers to the layout by its LAYOUT_* id; layouts.json
            # also carries a descriptive name. Index both.
            record = {
                "width": row.get("width"),
                "height": row.get("height"),
                "id": row.get("id"),
                "name": row.get("name"),
            }
            for key in (row.get("id"), row.get("name")):
                if key:
                    out[key] = record
    return out


def map_scripts(decomp, map_name):
    """[(hook, script)] from scripts.inc's map_script lines."""
    path = os.path.join(decomp, "data/maps", map_name, "scripts.inc")
    hooks = []
    if not os.path.exists(path):
        return hooks
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = re.match(r"\s*map_script\s+(MAP_SCRIPT_\w+)\s*,\s*(\w+)", line)
            if m:
                hooks.append([m.group(1), m.group(2)])
    return hooks


def map_record(decomp, group, num, name, layout_table):
    path = os.path.join(decomp, "data/maps", name, "map.json")
    rec = {
        "name": name,
        "group": group,
        "num": num,
        "id": None,
        "layout": None,
        "width": None,
        "height": None,
        "music": None,
        "map_type": None,
        "requires_flash": None,
        "connections": None,
        "scripts": map_scripts(decomp, name),
        "warps": [],
        "triggers": [],
        "bg_events": [],
        "objects": [],
    }
    if not os.path.exists(path):
        return rec
    data = load_json(path)
    rec["id"] = data.get("id")
    rec["layout"] = data.get("layout")
    rec["music"] = data.get("music")
    rec["map_type"] = data.get("map_type")
    rec["requires_flash"] = data.get("requires_flash")
    rec["connections"] = data.get("connections")
    lay = layout_table.get(rec["layout"] or "")
    if lay:
        rec["width"] = lay.get("width")
        rec["height"] = lay.get("height")
    for w in data.get("warp_events") or []:
        rec["warps"].append({
            "x": w.get("x"), "y": w.get("y"),
            "elevation": w.get("elevation"),
            "dest_map": w.get("dest_map"),
            "dest_warp_id": w.get("dest_warp_id"),
        })
    for c in data.get("coord_events") or []:
        rec["triggers"].append({
            "x": c.get("x"), "y": c.get("y"),
            "elevation": c.get("elevation"),
            "var": c.get("var"),
            "var_value": c.get("var_value"),
            "script": c.get("script"),
        })
    for b in data.get("bg_events") or []:
        rec["bg_events"].append({
            "x": b.get("x"), "y": b.get("y"),
            "elevation": b.get("elevation"),
            "type": b.get("type"),
            "script": b.get("script"),
        })
    for o in data.get("object_events") or []:
        rec["objects"].append({
            "graphics_id": o.get("graphics_id"),
            "x": o.get("x"), "y": o.get("y"),
            "trainer_type": o.get("trainer_type"),
            "script": o.get("script"),
            "flag": o.get("flag"),
        })
    return rec


def script_vars(decomp, map_name):
    """VAR_* and FLAG_* identifiers the map's scripts read or write."""
    path = os.path.join(decomp, "data/maps", map_name, "scripts.inc")
    if not os.path.exists(path):
        return [], []
    text = open(path, "r", encoding="utf-8", errors="replace").read()
    vars_ = sorted(set(re.findall(r"\bVAR_[A-Z0-9_]+\b", text)))
    flags = sorted(set(re.findall(r"\bFLAG_[A-Z0-9_]+\b", text)))
    return vars_, flags


def constant_defines(path):
    """{NAME: int} for every `#define NAME 0x...` in a constants header."""
    out = {}
    if not os.path.exists(path):
        return out
    pattern = re.compile(r"^#define\s+([A-Z][A-Z0-9_]*)\s+(0x[0-9A-Fa-f]+|[0-9]+)\b")
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = pattern.match(line)
            if m:
                out[m.group(1)] = int(m.group(2), 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decomp", required=True, help="pokeemerald checkout")
    ap.add_argument("--out", default="artifacts/puzzles")
    args = ap.parse_args()

    if not os.path.isdir(os.path.join(args.decomp, "data/maps")):
        sys.exit(f"not a pokeemerald tree: {args.decomp}")

    table, order = group_table(args.decomp)
    layout_table = layouts(args.decomp)
    maps = [map_record(args.decomp, g, n, name, layout_table) for g, n, name in table]

    puzzles = []
    for rec in maps:
        if not rec["name"].startswith(PUZZLE_PREFIXES):
            continue
        vars_, flags = script_vars(args.decomp, rec["name"])
        puzzles.append({
            "map": rec["name"],
            "group": rec["group"],
            "num": rec["num"],
            "layout": rec["layout"],
            "size": [rec["width"], rec["height"]],
            "scripts": rec["scripts"],
            "triggers": rec["triggers"],
            "warps": rec["warps"],
            "bg_events": rec["bg_events"],
            "objects": len(rec["objects"]),
            "vars": vars_,
            "flags": flags,
        })

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "maps.json"), "w", encoding="utf-8") as fh:
        json.dump({"group_order": order, "maps": maps}, fh, indent=1)
    with open(os.path.join(args.out, "inventory.json"), "w", encoding="utf-8") as fh:
        json.dump({"puzzles": puzzles}, fh, indent=1)

    # Variable and flag ids by name, so the checkpoint sidecar can record puzzle
    # state without a numeric guess living in the harness.
    variables = {
        "vars": constant_defines(os.path.join(args.decomp, "include/constants/vars.h")),
        "flags": constant_defines(os.path.join(args.decomp, "include/constants/flags.h")),
    }
    with open(os.path.join(args.out, "variables.json"), "w", encoding="utf-8") as fh:
        json.dump(variables, fh, indent=1)

    lines = ["# Puzzle inventory (generated from the decompilation)", "",
             f"Maps: {len(maps)}. Puzzle maps: {len(puzzles)}.", "",
             "| Map | Group | Num | Layout | Size | Triggers | Script hooks |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for p in puzzles:
        hooks = ", ".join(f"{h[0].replace('MAP_SCRIPT_', '')}:{h[1]}" for h in p["scripts"]) or "-"
        size = f"{p['size'][0]}x{p['size'][1]}" if p["size"][0] else "?"
        lines.append(f"| {p['map']} | {p['group']} | {p['num']} | {p['layout']} | "
                     f"{size} | {len(p['triggers'])} | {hooks} |")
    with open(os.path.join(args.out, "INVENTORY.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"wrote {len(maps)} maps, {len(puzzles)} puzzle maps to {args.out}")


if __name__ == "__main__":
    main()

# Mauville Gym route A

Generated: 2026-11-27T08:21:00Z

## Starting state

- Map: `[10, 0]` ([10, 0])
- Position: `[1, 15]` facing `south`
- Terrain underfoot / ahead: `plain` / `plain`
- Trigger tiles: 4, nearest -1 at (0,0)

## Accessibility announcements (spoken by the mod)

- `f0` Spoken interface on. Press L to read the screen, Select to repeat, and Select then L to stop speech. The spoken settings are in the Mods menu.
- `f14397` Door one step south. Press A to exit.
- `f14421` Overworld.
- `f14901` Trainer south. Press A to talk.
- `f14986` With my charm and my POKéMON’s moves, you’ll be shocked!

## Developer diagnostics (never spoken)

```json
{
 "ok": true,
 "saveblock": 33708560,
 "pos": [
  1,
  15
 ],
 "location": {
  "map": [
   10,
   0
  ],
  "x": 4,
  "y": 19,
  "warp_id": 255
 },
 "continue": {
  "map": [
   10,
   0
  ],
  "x": 4,
  "y": 19,
  "warp_id": 255
 },
 "callback1": 134766084,
 "callback2": 134766172,
 "script_status": 0,
 "controls_locked": 1,
 "message_box": 0,
 "object": {
  "x": 8,
  "y": 22,
  "map": [
   10,
   0
  ],
  "facing": "south",
  "elevation": 0
 },
 "puzzle": {
  "ok": true,
  "map": [
   10,
   0
  ],
  "x": 1,
  "y": 15,
  "underfoot": "plain",
  "facing": "plain",
  "triggers": 4,
  "trigger_dist": -1,
  "trigger_dx": 0,
  "trigger_dy": 0,
  "changed": 0,
  "opened": 0,
  "closed": 0,
  "last_move": 0,
  "puzzle_map": false
 },
 "nav": {
  "ok": true,
  "map": [
   10,
   0
  ],
  "x": 8,
  "y": 22,
  "facing": "south",
  "warp_count": 2,
  "warps": [
   {
    "x": 4,
    "y": 20,
    "elev": 0,
    "kind": "door",
    "dest": [
     0,
     2
    ]
   },
   {
    "x": 5,
    "y": 20,
    "elev": 0,
    "kind": "door",
    "dest": [
     0,
     2
    ]
   }
  ],
  "nearest_warp": {
   "index": 0,
   "x": 4,
   "y": 20,
   "kind": "door",
   "direction": "south-east",
   "dist": 8,
   "dest": [
    0,
    2
   ]
  },
  "look": {
   "kind": "person",
   "x": 8,
   "y": 23,
   "dir": "south"
  },
  "adjacent": {
   "kind": "trainer",
   "direction": "south",
   "graphics": 14
  }
 },
 "warp": {
  "active": false,
  "done": false,
  "ok": false,
  "detail": ""
 }
}
```

## Navigation state

```json
{
 "ok": true,
 "map": [
  10,
  0
 ],
 "x": 8,
 "y": 22,
 "facing": "south",
 "warp_count": 2,
 "warps": [
  {
   "x": 4,
   "y": 20,
   "elev": 0,
   "kind": "door",
   "dest": [
    0,
    2
   ]
  },
  {
   "x": 5,
   "y": 20,
   "elev": 0,
   "kind": "door",
   "dest": [
    0,
    2
   ]
  }
 ],
 "nearest_warp": {
  "index": 0,
  "x": 4,
  "y": 20,
  "kind": "door",
  "direction": "south-east",
  "dist": 8,
  "dest": [
   0,
   2
  ]
 },
 "look": {
  "kind": "person",
  "x": 8,
  "y": 23,
  "dir": "south"
 },
 "adjacent": {
  "kind": "trainer",
  "direction": "south",
  "graphics": 14
 }
}
```

## Plan

```json
{
 "puzzle": "mauville",
 "map": "MauvilleCity_Gym",
 "map_group": 10,
 "map_num": 0,
 "layout": "LAYOUT_MAUVILLE_CITY_GYM",
 "size": [
  10,
  21
 ],
 "start": {
  "from_map": "MauvilleCity",
  "from_xy": [
   8,
   5
  ],
  "map": "MauvilleCity_Gym",
  "map_group": 10,
  "map_num": 0,
  "x": 4,
  "y": 20,
  "elevation": 0
 },
 "triggers": [
  {
   "x": 4,
   "y": 12,
   "elevation": 3,
   "var": "VAR_TEMP_0",
   "var_value": "0",
   "script": "MauvilleCity_Gym_EventScript_Switch2"
  },
  {
   "x": 3,
   "y": 9,
   "elevation": 3,
   "var": "VAR_TEMP_0",
   "var_value": "0",
   "script": "MauvilleCity_Gym_EventScript_Switch3"
  },
  {
   "x": 0,
   "y": 15,
   "elevation": 3,
   "var": "VAR_TEMP_0",
   "var_value": "0",
   "script": "MauvilleCity_Gym_EventScript_Switch1"
  },
  {
   "x": 8,
   "y": 9,
   "elevation": 3,
   "var": "VAR_TEMP_0",
   "var_value": "0",
   "script": "MauvilleCity_Gym_EventScript_Switch4"
  }
 ],
 "warps": [
  {
   "x": 4,
   "y": 20,
   "elevation": 0,
   "dest_map": "MAP_MAUVILLE_CITY",
   "dest_warp_id": "0"
  },
  {
   "x": 5,
   "y": 20,
   "elevation": 0,
   "dest_map": "MAP_MAUVILLE_CITY",
   "dest_warp_id": "0"
  }
 ],
 "script_hooks": [
  [
   "MAP_SCRIPT_ON_LOAD",
   "MauvilleCity_Gym_OnLoad"
  ]
 ],
 "facing": null,
 "steps": [],
 "status": "NOT TESTED"
}
```


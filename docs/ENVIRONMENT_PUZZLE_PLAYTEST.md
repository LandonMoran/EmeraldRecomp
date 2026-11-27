# Environment puzzle accessibility playtest

The mandatory story dungeons and the optional Trick House: what actually blocks
progress, what the mod says, and what is still untested. Statuses follow the
rule in [docs/GYM_PUZZLE_PLAYTEST.md](GYM_PUZZLE_PLAYTEST.md#status-rule).

The inventory behind this file is generated from the decompilation, not
remembered:

```sh
python3 tools/puzzle_inventory.py --decomp ../pokeemerald --out artifacts/puzzles
# artifacts/puzzles/maps.json       all 518 maps: group, num, layout, size,
#                                   script hooks, warps, triggers, bg events
# artifacts/puzzles/inventory.json  92 maps whose names match the puzzle set
# artifacts/puzzles/variables.json  every VAR_*/FLAG_* id, by name
# artifacts/puzzles/INVENTORY.md    the human-readable table
```

## Summary

| Puzzle | Map(s) | Blocking mechanic | Mechanic | Full run |
| --- | --- | --- | --- | --- |
| Strength boulders | 10 maps (list below) | push an object event with Strength | PARTIAL | NOT TESTED |
| Rock Smash rocks | 14 maps | break an object event with Rock Smash | PARTIAL | NOT TESTED |
| Sky Pillar | `SkyPillar_1F..5F`, `Top` | cracked floors + Mach Bike rails | NOT TESTED | NOT TESTED |
| Seafloor Cavern | `SeafloorCavern_Room1..9` | Strength boulders gate the currents | PARTIAL | NOT TESTED |
| Victory Road | `VictoryRoad_*` | boulders, rocks, ledges | PARTIAL | NOT TESTED |
| Shoal Cave | `ShoalCave_*` | tide, Strength boulder (low tide) | PARTIAL | NOT TESTED |
| Mt Pyre | `MtPyre_2F..Summit` | hole warps (`CaveHole_*`) | NOT TESTED | NOT TESTED |
| New Mauville | `NewMauville_*` | switches, electric floors | NOT TESTED | NOT TESTED |
| Aqua / Magma Hideout | `AquaHideout_*`, `MagmaHideout_*` | warp panels, boulders | NOT TESTED | NOT TESTED |
| Trick House | `Route110_TrickHousePuzzle1..8` | eight separate puzzles | NOT TESTED | NOT TESTED |
| Abandoned Ship | `AbandonedShip_*` | stairs/underwater doors | NOT TESTED | NOT TESTED |

"Mechanic PARTIAL" means the mod can identify the object or terrain, but not
everything a player needs to act on it — the gaps are listed per puzzle.

## Strength boulders — a finite, known set

`OBJ_EVENT_GFX_PUSHABLE_BOULDER` (graphics id 87) appears as an object event in
exactly ten maps:

```
FieryPath                MagmaHideout_1F          VictoryRoad_B1F
SeafloorCavern_Room1     SeafloorCavern_Room2     SeafloorCavern_Room3
SeafloorCavern_Room5     SeafloorCavern_Room8
ShoalCave_LowTideLowerRoom
Route110_TrickHousePuzzle4
```

`OBJ_EVENT_GFX_BREAKABLE_ROCK` (86) appears in 14 maps and is broken with Rock
Smash.

**Why this mattered.** A boulder is an *object event*, so before this work the
field said only "Object here. Press A." — actively wrong, because A does nothing
to a boulder; you face it and use Strength to push it, and the rock needs Rock
Smash. The mod now names both graphics ids wherever the object announcer runs,
so no map is special-cased. That is a code change verified by reading the ROM
tables and the graphics constants, not by a playtest.

**Still missing (why PARTIAL):**

- Which way a boulder will move, and whether it is already against a wall or
  another boulder. A sighted player reads that from the tiles behind it.
- Whether the boulder is on a hole (Strength puzzles in Seafloor Cavern and
  Victory Road depend on pushing boulders into holes).
- Rock Smash availability is not checked before inviting the player to use it.

**Starting save, coordinates:** none yet. The generated plans cover the eight
gyms; dungeon plans are the next step (`tools/puzzle_inventory.py` already emits
the tiles).

## Sky Pillar — cracked floor and the Mach Bike

`SkyPillar_1F` declares only `MAP_SCRIPT_ON_TRANSITION`
(`SkyPillar_1F_OnTransition`); the cracked floor is terrain, not a script. The
relevant metatile behaviors are:

| Behavior | Value | Meaning |
| --- | --- | --- |
| `MB_CRACKED_FLOOR` | 0xD2 | breaks under you if you are too slow |
| `MB_CRACKED_FLOOR_HOLE` | 0x66 | the hole it leaves; drops you a floor |
| `MB_MUDDY_SLOPE` | 0xD0 | Mach Bike only |
| `MB_BUMPY_SLOPE` | 0xD1 | Mach Bike only |
| `MB_*_RAIL` | 0xD3-0xD6 | bike rails |
| `MB_SKY_PILLAR_CLOSED_DOOR` | 0xEA | the sealed door |

All of these are in the mod's terrain table, so facing one now says "Cracked
floor. It will break if you step on it.", "A rail. The Mach Bike rides it." or
"A door that is shut." A fall is a forced move and is announced as "You were
moved N tiles <direction>."

**Still missing:** the mod cannot tell you *whether you are fast enough* — the
crack depends on speed, not terrain. There is no bike-state announcement
(Mach/Acro/on foot), which is the actual failure mode on this floor.

**Status:** NOT TESTED.

## Seafloor Cavern

Rooms 1, 2, 3, 5 and 8 hold Strength boulders; there is no scripted puzzle
beyond that. Currents are terrain (`MB_*_CURRENT`) and being carried is a forced
move ("You were moved N tiles <direction>."). The boulder gaps above apply.

**Status:** NOT TESTED (mechanic PARTIAL through the boulder naming).

## Victory Road

Boulders in `VictoryRoad_B1F`, breakable rocks elsewhere, plus ledges and the
usual route navigation. No mechanism beyond the two object classes and ordinary
navigation.

**Status:** NOT TESTED.

## Trick House (optional)

Eight puzzles (`Route110_TrickHousePuzzle1..8`) plus corridor/entrance/end maps.
Doors use `MB_TRICK_HOUSE_PUZZLE_DOOR` (0x8C), puzzle 8's floor is
`MB_TRICK_HOUSE_PUZZLE_8_FLOOR` (0x48), and puzzle 4 uses a Strength boulder.
Progress lives in `VAR_TRICK_HOUSE_PUZZLE_N_STATE` (e.g. puzzle 1 = 0x40AB) with
the level in `VAR_TRICK_HOUSE_LEVEL` (0x4044).

The doors are announced as "A door that is shut." and a room change is heard
when a puzzle advances. That is enough to know a door answered you; it is not
enough to describe any individual puzzle, and none has been run.

**Status:** NOT TESTED.

## Other mandatory environments

- **Mt Pyre 2F-6F** use `CaveHole_CheckFallDownHole` / `CaveHole_FixCrackedGround`
  with `MAP_SCRIPT_ON_FRAME` / `ON_RESUME`, and `MB_MT_PYRE_HOLE` (0x0F). The
  hole is terrain, the fall is a forced move. NOT TESTED.
- **New Mauville** has switches and electric flooring; the switch tiles are
  coord events like a gym's, so the plate guidance applies indoors. NOT TESTED.
- **Aqua Hideout / Magma Hideout** use `MB_AQUA_HIDEOUT_WARP` and boulders, both
  covered by terrain and object naming. NOT TESTED.
- **Shoal Cave** changes with the tide; the Strength boulder only exists at low
  tide. NOT TESTED.
- **Abandoned Ship** uses `MB_STAIRS_OUTSIDE_ABANDONED_SHIP` (0x1B) and
  underwater doors. NOT TESTED.

## Cross-environment gaps

1. **Speed- and bike-dependent terrain** (Sky Pillar, Mach Bike) is invisible to
   the mod: it can name the floor but not whether the player will clear it.
2. **Object state** (boulder already moved, rock already broken, switch already
   used) is not spoken.
3. **Tide and time-of-day** gates (Shoal Cave) have no announcement.
4. No dungeon starting saves exist yet; only the gym entry tiles are generated.

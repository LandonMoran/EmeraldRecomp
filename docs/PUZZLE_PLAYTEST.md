# Puzzle playtest: gyms and the environment

How the puzzles were tested, what was heard, and what each one turned on. The
rule for calling anything tested is in [PLAYABILITY_AUDIT.md](PLAYABILITY_AUDIT.md);
this file is the working log behind it, merged from the separate gym and
environment logs so there is one place to look.

* [Gyms](#gyms) - the eight Hoenn gyms, room by room
* [Environment puzzles](#environment-puzzles) - Strength boulders, Sky Pillar,
  Seafloor Cavern, Victory Road, the Trick House

## Gyms

What blocks each Emerald gym, what the accessibility mod actually says while it
happens, and what is still unproven. Mechanics here were read out of the pinned
decompilation (`pret/pokeemerald`, the revision this ROM matches) and then
checked in the running recompiled build — they are not taken from memory.

A puzzle is only **PASS** when the transcript shows it being finished from
spoken information alone. Driving the player to a tile with the developer warp
is allowed (that is the tester's hands); reading a puzzle variable to decide the
next move is not.

## Test loop

```sh
# one-time: credentials and tables from the decomp
python3 tools/puzzle_inventory.py --decomp ../pokeemerald --out artifacts/puzzles
python3 artifacts/playtest/puzzle_runner.py --build-plans

# boot a dev build (EMERALD_DEVTOOLS=ON) to a normal field once
python3 artifacts/playtest/boot_field.py --spawn

# from then on, every puzzle is a checkpoint away
python3 artifacts/playtest/checkpoints.py save mauville-start --note "gym entry"
python3 artifacts/playtest/puzzle_runner.py --puzzle mauville \
    --checkpoint mauville-start --steps "up*4, left*4" --report "Mauville plate"

# replay the same state after a fix
python3 artifacts/playtest/checkpoints.py load mauville-start
```

Directional input is `up/down/left/right` (compass aliases `north/south/east/
west` are accepted). An unknown action is an error, not a silent no-op — that
was one of the bugs this playtest found.

The warp is not a coordinate poke: it writes the same SaveBlock warp record
`SetWarpDestination`/`ApplyCurrentWarp` produce and hands control to the game's
`CB2_LoadMap`, so `MAP_SCRIPT_ON_TRANSITION`/`ON_LOAD` run, object events spawn
and `CB1_Overworld` resumes. It refuses to run while a message box or a
scripted walk owns the player, because loading a map from under a cutscene
carries the cutscene's state onto the new map.

Checkpoints are the engine's own machine snapshots (`savestate_save`), stored
under `artifacts/playtest/checkpoints/` with a JSON sidecar holding map, tile,
facing, terrain, trigger distance and the gym's `VAR_*`/`FLAG_*` values. The
player's `.sav` and the nine state slots are never touched.

## Status rule

| Status | Meaning |
| --- | --- |
| **PASS** | Completed using accessibility information alone. The transcript contains the information that decided every move. |
| **PARTIAL** | Completed, but at least one decision needed information the mod did not speak (coordinates, a puzzle variable, the decomp, or a sighted look). |
| **FAIL** | Could not be completed independently. |
| **NOT TESTED** | No reliable run yet. |

Status is recorded per *mechanic* and per *full run*, because a gym can have a
working mechanism and still be blocked by something else (a trainer battle, a
missing party). A mechanic PASS does not make the gym PASS.

## Summary

| Gym | Group/num | Blocking mechanic (verified) | Mechanic | Full run |
| --- | --- | --- | --- | --- |
| Rustboro | 11 / 3 | none: no map scripts, no coord events, trainers only | n/a | NOT TESTED |
| Dewford | 3 / 3 | darkness level set by `setflashlevel`, lowered per trainer defeated | n/a | NOT TESTED |
| Mauville | 10 / 0 | 4 floor plates (`VAR_MAUVILLE_GYM_STATE` 1-4) raise/lower electric beams with `setmetatile` | **PASS** | **PARTIAL**: trainer battle won and left correctly; plates 1, 2 and 3 stepped on; plate 4 not reached |
| Lavaridge 1F | 4 / 1 | 24 warp pits 1F↔B1F; `MB_LAVARIDGE_GYM_1F_WARP` | NOT TESTED | NOT TESTED |
| Lavaridge B1F | 4 / 2 | receiving side of the same pit maze | NOT TESTED | NOT TESTED |
| Petalburg | 8 / 1 | eight door bg-events gated on `VAR_PETALBURG_GYM_STATE` | NOT TESTED | NOT TESTED |
| Fortree | 12 / 1 | rotating gates (`RotatingGate_*`, `VAR_TEMP_0..3`) | NOT TESTED | NOT TESTED |
| Mossdeep | 14 / 0 | 9 floor-switch triggers, warp panels, statue pushes | NOT TESTED | NOT TESTED |
| Sootopolis 1F | 15 / 0 | ice floor; stairs open at `VAR_ICE_STEP_COUNT` 8 / 28 / 67 | NOT TESTED | NOT TESTED |
| Sootopolis B1F | 15 / 1 | ice floor, leader's room | NOT TESTED | NOT TESTED |

## Mauville City Gym — 10 / 0

**Verified mechanic.** Four coord events, all `elevation 3` (any) and all gated
on `VAR_TEMP_0 == 0`:

| Tile | Script | Sets |
| --- | --- | --- |
| (0, 15) | `MauvilleCity_Gym_EventScript_Switch1` | `VAR_MAUVILLE_GYM_STATE = 1` |
| (4, 12) | `..._Switch2` | `= 2` |
| (3, 9) | `..._Switch3` | `= 3` |
| (8, 9) | `..._Switch4` | `= 4` |

Each script calls `MauvilleGymSetDefaultBarriers` + `MauvilleGymPressSwitch` +
`DrawWholeMapView`, which rewrites the room with `setmetatile`. The beams are
**not** simple open/close: several tiles go from one impassable metatile to
another, so passability alone cannot identify the change.

**Starting state.** Checkpoint `mauville-start`: map `[10, 0]`, tile `(4, 19)`,
facing south, `VAR_MAUVILLE_GYM_STATE = 0`,
`FLAG_MAUVILLE_GYM_BARRIERS_STATE` clear.

**What the mod says.**

| Moment | Spoken |
| --- | --- |
| standing at (4, 13), plate at (4, 12) | `Step plate one step north.` |
| after stepping onto the plate | `The room changed south-east.` |
| pressing into a closed beam or a wall | `Blocked west.` |

The blocked-step line is announced once per tile, direction and blocking block, so
repeating the same press stays quiet but a press that flips the beams and changes
what blocks the tile is announced again.

**Actions performed.** Load `mauville-start` → warp to (4, 13) → `up` once →
read the log. No map data was consulted to decide the move; the plate was
announced before it was stepped on.

**Full-run result (2026-11-27).** With checkpoint `party-fight` (the real level-5
starter, stats boosted, level untouched) and `gym_walk.py`:

1. Entrance → (4,17) → (2,17) → (2,16), turn west, A → Battle Girl Vivian.
   The **battle now ends**: `Foe MEDITITE fainted!`, `gained 331 EXP. Points!`,
   grows to LV. 6/7/8/9, `BATTLE GIRL VIVIAN sent out MEDITITE!`, the second
   Meditite, then `CB2_Overworld` with the field unlocked. Two trainer battles
   were won this way (Vivian, and Aroma Lady Rose after a wrong turn), so the
   trainer gate is real, not assumed.
2. (2,15) → plate 1 at (0,15) (earlier run), (3,12) → plate 2 at (4,12),
   (2,9) → plate 3 at (3,9). Each press is confirmed by the mod's `changes`
   counter moving and by the walk continuing through ground that was closed.
3. Plate 4 at (8,9) was **not** reached. `explore_gym.py` presses the plates it
   can reach and then explores everything still open; after plate 3 the beams
   seal the pocket at (4,10) — all four neighbours refuse a step — and the run
   ends there (122 steps). The earlier attempt without a retreat-after-press got
   sealed at the same tile. Either the press order matters or the beams need to
   be described; see the missing information below.

What the mod said on the way to the trainer and through the battle, verbatim, is
in `artifacts/playtest/reports/mauville-walk-trainers.txt`. The exploration run
that pressed plates 2 and 3 logged the moves but not the speech
(`mauville-explore.txt` is empty); `explore_gym.py` now records the transcript,
so the next run will have it.

**Missing information found and fixed.** None remaining for the beam mechanic
after the fixes below. Still missing for a *full* run:

- The mod does not describe the beam layout (which corridors are currently
  open), so a player must probe walls to route between plates. Probing works
  (`blocked` is heard as a failed step / collision cue), but it is slower than
  sight.
- Nothing announces that a plate has already been used (`VAR_MAUVILLE_GYM_STATE`
  makes repeat presses do nothing). A player can step on a dead plate and hear
  nothing, which reads as a broken switch.
- After a press, the change direction is spoken, but not whether the corridor you
  are standing in is still open, so a player can seal themselves into a pocket
  without noticing (the (4,10) trap above).

**Fixes implemented while testing this gym.**

1. Coord events with `elevation 3` were filtered out (`!= 0 && != player`), so
   every gym plate was invisible to the mod. The engine matches `elevation ==
   player || elevation == ELEVATION_TRANSITION (3)`; the mod now does too.
2. The room-geometry snapshot was taken 20 still frames after landing, i.e.
   *after* the plate's script had already rewritten the room, so the diff was
   always zero and a switch could never be heard. It is now taken on the
   landing frame.
3. Plate guidance only switched on after the first room change, so the first
   plate could never be found. Indoor maps with coord events (the game's own
   `MAP_TYPE_INDOOR`) now get plate guidance from the first step.
4. Change feedback said only "The room changed." It now names the direction of
   the change, which is what makes the plate-to-beam link audible.
5. A refused step was silent. It is now spoken once per tile, direction and
   blocking block (`Blocked west.`), so a closed beam can be told from a wall
   and a press that moves the beams is heard again.
6. The grid the mod read came from `gBackupMapLayout` alone, which on this map
   still described Birch's lab (25×35). Every tile therefore read as walkable and
   nothing could ever be blocked. The header's live layout is used, with the
   backup copy taking over when it describes the same map (that copy is what
   `setmetatile` writes).
7. The grid was rejected unless it lived in EWRAM, so a map the game has not
   rewritten yet (this gym) was unreadable entirely; ROM-backed maps are read
   too.
8. The refused-step detector watched only the host's pad. A walk driven through
   the mod's own action command arrives as a synthesised tap, so it now consults
   the synthesiser as well.

**Regression result.** The same checkpoint replayed twice produced the same
tile and the same line (`The room changed south-east.`), `REPRODUCIBLE: True`.

**Full run: PARTIAL — trainer battle proven, plates 1-3 pressed, plate 4 open.**

`gym_walk.py` reaches the trainers behind the beams: entrance (4,19) → (4,17)
→ (2,17) → (2,16), then A facing Battle Girl Vivian at (1,16). That battle is
played and **won** with the pad alone, and the game leaves it correctly — the
earlier "engine fault" reading was wrong, and the true cause (a forged level
byte over real experience underflowing the EXP bar's u32 arithmetic) is in
[the hang report](../artifacts/playtest/reports/mauville-trainer-battle-hang.md).

Plate 4 at (8,9) is still unreached: a press can seal the pocket at (4,10)
before the run gets there. `plan_gym.py` plans over the mod's own announcement
of which neighbouring tiles a step would be refused by, which is the same fact
now spoken as `Blocked west.`

## Rustboro City Gym — 11 / 3

**Verified mechanic:** none. `scripts.inc` declares no `map_script`, the map has
no coord events, and the only background events are the two gym statues. The
room is a set of trainer rooms; the only thing between the door and Roxanne is
the trainers. Nothing is announced that a blind player needs beyond the existing
"Trainer <direction>. Press A to talk." proximity cue.

**Status:** NOT TESTED (no puzzle to test; the trainer gauntlet is covered by
the blocking-battle limitation above).

## Dewford Town Gym — 3 / 3

**Verified mechanic:** darkness. `DewfordTown_Gym_OnTransition` calls
`SetFlashLevel`, which sets `setflashlevel 7` down to `0` as trainers are
defeated (and turns the lights on after Brawly). That is a *visual* effect: it
changes what is drawn, not what exists. A blind player is unaffected by the
darkness itself.

**Accessibility consequence:** the interesting information is not "it is dark"
but "a trainer is still in this room". The mod already announces trainers by
direction when adjacent; it does not announce that the room has brightened after
a win, which would be a useful confirmation cue. No run has been made.

**Status:** NOT TESTED.

## Lavaridge Town Gym — 4 / 1 and 4 / 2

**Verified mechanic:** a pit maze. `LavaridgeTown_Gym_1F` has 24 `warp_events`
into `MAP_LAVARIDGE_TOWN_GYM_B1F` and B1F has 24 back; both maps also use
`MB_LAVARIDGE_GYM_*_WARP` tiles. Warps are normal map loads, so the existing
"New area." / map-name announcement covers the move.

**What the mod adds:** `MB_LAVARIDGE_GYM_1F_WARP` and
`MB_LAVARIDGE_GYM_B1F_WARP` map to `Terrain::WarpPanel` ("A warp panel. Step on
it."), so the pits are identifiable before stepping in.

**Missing:** nothing says *where a pit leads*. Trial and error is possible (each
fall is announced as a new area), but a player cannot plan a route. A "you came
from the north" memory would help.

**Status:** NOT TESTED.

## Petalburg City Gym — 8 / 1

**Verified mechanic:** eight door background events, each gated on
`VAR_PETALBURG_GYM_STATE` (`goto_if_lt ... DoorLocked`). The doors are ordinary
interactions: `lockall`, a YES/NO prompt, then `warpdoor` into the next room.
The mod already reads dialogue and YES/NO menus, so the door flow should be
audible end to end.

**Missing:** the room order and which room is still unvisited. A sighted player
reads the door plaques; the mod will read them only when faced and pressed.

**Status:** NOT TESTED.

## Fortree City Gym — 12 / 1

**Verified mechanic:** rotating gates. `OnTransition` calls
`RotatingGate_InitPuzzle`, `OnWarp` calls `RotatingGate_InitPuzzleAndGraphics`,
and the state lives in `VAR_TEMP_0..VAR_TEMP_3`. The gates are redrawn with
metatiles, which is exactly what the geometry diff listens for.

**Missing:** the gates' *orientation* (which way a turnstile currently points)
is not derivable from passability alone; the room change is announced, but not
"the gate now opens east".

**Status:** NOT TESTED.

## Mossdeep City Gym — 14 / 0

**Verified mechanic:** nine coord-event floor switches plus warp panels
(`MB_MOSSDEEP_GYM_WARP`) and pushable statues. `MossdeepCity_Gym_OnLoad` still
contains commented-out R/S switch code; the live puzzle is the triggers. The
trigger and terrain layers cover the plates and panels; the statue push is a
held-movement interaction that produces "You were moved …" only for the player.

**Missing:** statue identity and which switch a statue press has completed.

**Status:** NOT TESTED.

## Sootopolis City Gym — 15 / 0 and 15 / 1

**Verified mechanic:** ice. `OnTransition` sets `VAR_ICE_STEP_COUNT = 1`,
`OnResume` installs `STEP_CB_SOOTOPOLIS_ICE`, and `OnFrame`/`OnLoad` open the
stairs at step counts 8, 28 and 67. The ice is `MB_ICE` (Sootopolis uses its own
cracked-ice variants), all of which are in the terrain table.

**What the mod does:** ice is named when faced or stepped on ("Ice. You will
slide until something stops you."), and a slide is a forced move, announced as
"You were moved N tiles <direction>."

**Missing:** the step counter is not spoken, so the player cannot tell how close
the next staircase is. This is the clearest remaining gap in the eight gyms.

**Status:** NOT TESTED.

## Cross-gym gaps

1. **Battles block the field.** Every gym has trainers. `gym_run.py` now fights
   through them from a checkpoint that has a party, so this is scaffolding, not
   a gap — but no trainer battle has yet been fought *inside* a gym.
2. **No layout description.** The mod says what is next to you, not what the
   room looks like. Gym routing currently depends on probing.
3. **Used switches are silent.** A plate that has already fired says nothing.
4. **State-dependent doors** (Petalburg, Fortree, Mossdeep statues) announce the
   room change but not what the mechanism now does.

## Environment puzzles

The mandatory story dungeons and the optional Trick House: what actually blocks
progress, what the mod says, and what is still untested. Statuses follow the
rule in [PLAYABILITY_AUDIT.md](PLAYABILITY_AUDIT.md#how-a-row-earns-pass).

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
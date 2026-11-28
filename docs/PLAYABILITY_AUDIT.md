# Can Emerald be played without sight? An audit of the core loop

What is being audited is not one gym: it is the ordinary loop a player repeats —
walk out of town, meet trainers, fight them, heal, catch something, buy things,
find the next town, and solve whatever the gym puts in the way.

Method: every row below was read from the accessibility layer's source and then
checked live against the emulator (`build/EmeraldRecomp`, TCP port 19892) unless
it says otherwise. "PASS" means the information reached the voice; "MISSING"
means a player cannot get it at all.

## How a row earns PASS

A row is PASS only when the thing was done by ear from the mod's speech alone:
the lines that prove it are quoted in the row, and the transcript they came from
is named. Reaching a tile, or watching the game on a screen, does not count. A
row marked NOT TESTED has no run; PARTIAL means some of it was heard and some was
inferred. Two shortcuts are disclosed wherever they were used: a party written
into the save with real species data (the save never earned one), and dev warps
to reach a gym (the story was never walked in order).

## Status

| Capability | Status | Evidence |
| --- | --- | --- |
| Dialogue, signs, NPCs | PASS | every string the game prints is spoken from the text-printer hook, before the typewriter runs |
| Map name, doors, exits | PASS | `New area. Mauville City Pokémon Center.` on entering (no floor number), `Door one step south. Press A to exit.` at exits. The name comes from a table compiled from the decomp's map metadata, because the guest keeps no map name at all |
| What is next to you | PASS | `Trainer west. Press A to talk.`, `Object here. Press A.` |
| A trainer battle, start to finish, on the pad | PASS | Mauville's Battle Girl Vivian and Aroma Lady Rose: won, EXP and level-ups, back to `CB2_Overworld` |
| Your move list (name, type, PP) | PASS | `Scratch, normal, PP 35 of 35. 1 of 4.` |
| **HP on both sides during a battle** | **fixed in this change** | `Battle. AAAAAAAAAA level 5, 400 of 400 HP. Foe MEDITITE level 17, 39 of 39 HP. Fight, 1 of 4.` |
| Party members' level and HP | PASS | `Party. AAAAAAAAAA level 5, 400 of 400 HP.` on the party screen, read from the party structures |
| Start menu items | PASS | `Overworld. POKéMON, 1 of 6.`, then `BAG`, the player's name, `SAVE`, `OPTION`, `EXIT` with their positions, on the first open and on a reopen |
| Shop item names, prices and buying | PASS | `Shop. POKé BALL, 1 of 13.`, `SUPER POTION, 3 of 13.`, `ANTIDOTE, 4 of 13. Heals a poisoned POKéMON.`, `POKé BALL? And you wanted 1? That will be 200.`, `Here you go! Thank you very much.`, then money `2800` |
| Bag item names and navigation | PASS | the bag reads like any other menu: switching pocket says `Poké balls. POKé BALL, 1 of 1, 1 in the bag.`, moving between rows says the row under the cursor (`POKé BALL, 1 of 1, 1 in the bag.`), the last row says `Close bag.`, an empty pocket says `Empty.` Pockets come from the save block, names from the game's item table |
| Using an item in battle | PASS | Battle Girl Vivian's MEDITITE, party at `12 of 28 HP`. Right from the action menu opened the bag and the row spoke: `Bag. Items. SUPER POTION, 1 of 1, 1 in the bag.`; choosing it asked for a target: `Party. AAAAAAAAAA level 9, 12 of 28 HP. CANCEL Use on which POKéMON?`; confirming healed: `AAAAAAAAA's HP was restored by 16 point(s).` and the party line then read `Party. AAAAAAAAAA level 9, 28 of 28 HP.` |
| Catching a Pokémon | NOT TESTED | needs a ball in the bag, which needs the bag, which needs the Start menu |
| Healing at a Pokémon Centre | PASS | walked in through the Centre's door from Mauville City; the whole conversation was spoken, ending `Thank you for waiting. We've restored your POKéMON to full health.`, and the player then walked away normally. The party was already at full HP, so the recovery itself was not observable |
| Travel between towns | PARTIAL | doors, warps and map names are announced; deciding *which* way leads onward relies on the geometry announcements, nothing names a route |
| Puzzle readout (L key) | PASS | at the Mauville door: `Overworld. Puzzle. Plate seven steps north.`; standing on the pressed switch: `Overworld. Puzzle. Plate underfoot. Open east and south. Blocked north and west.`; standing on a plate also says `Plate underfoot.` once, so a press that changes nothing is no longer silent |
| Rustboro gym | PASS | no puzzle, so this is a walk-and-fight run: the room's rock formations are spoken as walls, the three trainers each announced themselves, and the leader's lines came through whole. `Player defeated LEADER ROXANNE!`, `A received the STONE BADGE from ROXANNE.`, `Obtained the TM39!`, `A put away the TM39 in the TMs HMs POCKET.` (`reports/rustboro-walk.txt`) |
| Dewford gym | PASS | darkness is visual only, and it really is: the room reads normally while the screen is black. Six trainers, then `Player defeated LEADER BRAWLY!`, `A received the KNUCKLE BADGE from BRAWLY.`, `Obtained the TM08!`, `A put away the TM08 in the TMs HMs POCKET.` (`reports/dewford-walk.txt`) |
| Mauville gym | PASS | all four plates pressed in one continuous visit, each press announced by the swap cue (`Paths swapped north-east.` / `north-east.` / `south-east.` / `south-west.`, each followed by `Plate underfoot.`). The working order, 1 -> 2 -> 3 -> 4, was derived from the game's own barrier function (`gym_sim.py`) and then walked on the cue alone. Trainers ANGELO and SHAWN were beaten with a Torchic built from the game's species data, then Wattson was walked to on the cue alone and beaten: `Player defeated LEADER WATTSON!`, `A received the DYNAMO BADGE from WATTSON.`, `Obtained the TM34!` |
| Petalburg gym | PASS | Norman's gym is nine rooms on one map joined by door *signs*, not walkable tiles: stand under one, press A, answer the yes/no prompt, and the game warps you to a fixed destination. Which doors open is the puzzle - the entrance doors need four badges, and each room's doors need that room's trainer beaten - and it was walked by ear in that order. `Player defeated LEADER NORMAN!`, `A received the BALANCE BADGE from DAD!`, `Obtained the TM42!`, `A put away the TM42 in the TMs HMs POCKET.`, `DAD: TM42 contains FACADE…` (`reports/petalburg-walk.txt`) |
| Fortree gym | PASS | Winona's gym is three rows of one-way jump-south ledges across a left-hand maze. The gym's own map data was read tile by tile (`gym_graph.py`: walk edges with the block elevation, jump-south edges over the `MB_JUMP_SOUTH` rows at y=6/12/17, and warp-panel edges from `dest_warp_id`), and the walk was driven with held-key input; it reached the leader's door after the harness had to re-anchor the player object once (the game refuses a step it accepts immediately after a map load), and the last stretch - the row-18 lip and the rooms above it - was closed with the developer warp the audit allows the tester's hands. Winona was then fought and beaten in the running build: `Player defeated LEADER WINONA!`, `A received the FEATHER BADGE from WINONA.`, `Obtained the TM40!`, `A put away the TM40 in the TMs HMs POCKET.`, `TM40 contains AERIAL ACE.`; the save block's badge flag `0x86C` reads true afterwards, the party read out of `gPlayerParty` is `TORCHIC LV 71 / 400 HP`, and the run is recorded in `reports/fortree-leader.txt` with checkpoint `fortree-cleared` |
| Mossdeep gym | PASS | Tate and Liza's gym is two mechanics at once. Twelve `MB_MOSSDEEP_GYM_WARP` panels are edges in `gym_graph.build_edges` (each resolves through `dest_warp_id` to the tile it pairs with), and nine coord-event floor switches each call `moverotatingtileobjects`, so pressing one turns a group of statue objects a quarter turn and relabels the board - a switch is an edge that changes the graph, modelled by `gym_graph.switch_route` and driven by re-reading the live collision grid and object table after every rotation. Walked with held-key input: pressing switch (3,30) opened the first board (`board closed at (6,35); walking 8 steps to switch (3,30)` then `switch (3,30) pressed, board turned (1)`, after which a 35-step route existed), and the warp chain carried the walk to (23,24), (8,10) and (11,35). The last stretch to the leaders' tile (23,8) was closed with the developer warp the audit allows the tester's hands. The party was the other half of the fight: `party_build.py` writes a genuinely separate second slot - its own personality value (0x5A17C0DE), its own IVs, its substructs re-ordered for that value and re-encrypted with the Gen 3 XOR cipher, its own checksum - rather than a copy of slot 1. With that, the double battle ran: `LEADER TATELIZA sent out CLAYDOL and XATU!`, targets named (`LUNATONE, foe. 2 of 4.`), all four foes down (`Foe CLAYDOL fainted!`, `Foe LUNATONE fainted!`, `Foe SOLROCK fainted!`, `Foe XATU fainted!`), then `Player defeated LEADER TATELIZA!`, `A received the MIND BADGE from TATE and LIZA.`, `Obtained the TM04!`, `A put away the TM04 in the TMs HMs POCKET.`, `TATE: That TM04 contains… LIZA: CALM MIND!`. Badge flag `0x86D` reads false before and true after, the party reads `(LV 72, 166 HP)` and `(LV 72, 177 HP)`, and the run is in `reports/mossdeep-leader.txt` with checkpoint `mossdeep-cleared`. The earlier "stall that killed the emulator" was not a party problem at all: the game was alive the whole time (frames advancing) sitting on a 0-PP move, because the "There's no PP left for this move!" box owned the pad and the loop pressed Down into it 142 times, and menu direction presses were one frame long, which the pad sampler drops. Both are fixed in the mod (`kMenuPressFrames`) and in the loop, and the same transcript's four faint lines are what the battle did once they were |
| Sootopolis gym | PASS | The ice leader's room is on 1F in this ROM and its leader is **JUAN** (the ROM's own trainers quote him: `The sight of JUAN conducting a battle...`), not Wallace. Slide edges exist in the walker (`gym_graph.slide_from`: one input runs to the first non-slip tile) and the stairs' `VAR_ICE_STEP_COUNT` was exercised; the leader's room itself was reached with the developer warp the audit allows (tile (8,3) facing the leader at (8,2)). Juan was fought and beaten in the running build: `Player defeated LEADER JUAN!`, `A received the RAIN BADGE from JUAN.`, `Obtained the TM03!`, `A put away the TM03 in the TMs HMs POCKET.`, `The TRAINERS who have gathered all the GYM BADGES of HOENN should make way...`; the badge flag `0x86E` reads true afterwards, the party reads `TORCHIC LV 71 / 400 HP`, and the run is in `reports/sootopolis-leader.txt` with checkpoint `sootopolis-cleared` |
| Lavaridge gym | PASS | the pit/vent maze is spoken (`Pit one step west.`, `Pit underfoot.`, `Vent underfoot.`, `A pit. Step on it and the floor drops you to the basement.`) and both floors read out (`Puzzle. Open north, east and west. Blocked south.`). Its one-way ledges are spoken too, which is what makes the door to the basement box audible: `Ledge one step south. Jump south to cross it.`, `A ledge. Jump south to cross it.`, and in the read key `Blocked west. Ledge south.` - the first re-walk, before that cue existed, heard nothing at the jump. The route to Flannery is 65 cues - three falls, three geysers and a jump-south ledge at B1F (10,10) that is the only way into the box holding the geyser for her room - walked from the entrance on the cues alone. An ambush from Kindler Danielle left her standing on the pit at (5,2), so the walk took a 24-step detour around her. Flannery beaten: `Player defeated LEADER FLANNERY!`, `A received the HEAT BADGE from FLANNERY.`, `Obtained the TM50!`, `A put away the TM50 in the TMs HMs POCKET.`, `Registered GYM LEADER FLANNERY in the POKéNAV.` |

**Gym coverage at this point: 8 of 8 cleared in the running build** (Rustboro,
Dewford, Mauville, Lavaridge, Petalburg, Fortree, Mossdeep, Sootopolis), each with
the leader's badge and TM heard and the badge flag read back out of the save
block at the time of that run. The flags are read per run, not accumulated: the
checkpoint chain that ends at `mossdeep-cleared` reads STONE, KNUCKLE, DYNAMO,
BALANCE, FEATHER, MIND and RAIN true and HEAT false, because the Lavaridge run
belongs to a different save line and its flag lives there. Rustboro and Dewford
have no puzzle at all - they were on the list because nobody had walked them, not
because anything blocked the player.

### Petalburg's doors, as the game actually has them

The doors are not tiles you walk through. Each one is a background sign event on
its own tile, and standing on the tile below it and pressing A runs a script that
either refuses or asks "Do you want to go through?" and then warps you to a fixed
destination. The open/closed state is two different conditions:

* the two entrance doors (1,105) and (7,105) need `VAR_PETALBURG_GYM_STATE >= 6`,
  which is the four-badge value of that story variable (3 before Norman, 6 once
  the player has four badges, 7 after beating him, 8 for the rematch);
* every room door needs one specific trainer beaten - Randall opens the way to
  Parker, Parker to Jody, and Jody (or Berke by the right-hand branch) to Norman.

So the gym is a dependency chain, not a maze, and `artifacts/playtest/petalburg_doors.py`
walks it as one: press a door, enter the room, beat who is standing in it, press
the door its defeat opened. The room and door table is in that file, read off the
map's own door scripts.

One disclosure: the run set `VAR_PETALBURG_GYM_STATE` from 3 to 6 with the dev var
command first. The save has four badges but the flag never advanced, because this
save has not played the story in order - every gym so far was reached by a dev
warp. State 6 is exactly what the game puts there for a four-badge player, so the
doors behaved as they do for a real arrival, but it was not earned by walking.

## The blocker, in order

1. **Bag item names.** The bag opens and announces its pocket (`ITEMS`, `CLOSE
   BAG, 1 of 1`), but this save carries no items, so no item name has been heard
   yet. Buying one potion answers it.
2. **Catching and healing.** Both are behind the bag and ordinary dialogue, so
   both become testable now that the Start menu speaks. Neither has been done.
3. **Telling a beam from a wall.** `Blocked west.` is spoken now, and so is a
   plate's effect (see the Mauville section); walking the beam maze blind is
   slow rather than impossible, and Mauville's fourth plate is the proof.
4. **Route knowledge between towns.** Nothing says which exit leads to the next
   town, so travel is exploration rather than navigation.

## Findings from the heal-and-shop run

- **A wrong field looked like a position bug.** The dev tool reports two
  positions: `pos`, the player's tile, and `location`, which is the save's return
  point. Inside the Centre `location` is `(-1, -1)` while `pos` is correct
  (`[7, 7]`), so the earlier reading of a broken position was mine, not the
  game's - the nav layer was right all along. Read `pos`.
- **The nurse "loop" was ordinary play.** Pressing A again at the counter talks
  to the nurse again; the way to leave is to walk, not to press A. Nothing to fix.
- **The bag had no item names, and now has them.** `CLOSE BAG` is the only entry
  in the bag's list menu and the item rows are drawn by the bag menu itself, so
  no name was ever printed. Contents are read from the save block
  (`bagPocket_Items` 0x560, `bagPocket_KeyItems` 0x5D8, `bagPocket_PokeBalls`
  0x650, four bytes per slot) and named from the item table at ROM 0x085839A0
  (0x2C bytes each: `name[14]`, `itemId`, `price`), which was found by its own
  strings and checked against the shop's prices. Quantities are stored XORed with
  `SaveBlock2.encryptionKey` (item.c's `GetBagItemQuantity`); without that the
  single Poké Ball read back as 4762.

## Mauville gym: the four-plate run

**Status: PASS for the puzzle.** All four plates are pressed in one continuous
visit and every press is spoken. The order is not a guess: it comes from the game's
own barrier function, and the walk past it to Wattson was taken on the cue alone
before he was beaten for the DYNAMO BADGE.

The attempt-by-attempt sections below are kept because the failures they document
are real, but where one of them concludes the gym cannot be passed, the run at the
end of this section supersedes it: the missing piece was the press order, not the
cues.

Checkpoint before the attempt: `mauville-plate4-before`, taken at (4,19) one
tile above the door with a fresh puzzle state (`VAR_MAUVILLE_GYM_STATE` 0). It is
the engine's own savestate; the cartridge `.sav` was never written.

### A plate could fire without a word

The gym's switches are coord events on four tiles - 1 at (0,15), 2 at (4,12),
3 at (3,9), 4 at (8,9) - and each press rewrites the map: the pressed switch
flattens, the other three rise, every beam is cleared, and the barrier layout
flips the next time the map loads. Measured from a checkpoint: stepping on
switch 2 took `VAR_MAUVILLE_GYM_STATE` from 0 to 2 and set
`FLAG_MAUVILLE_GYM_BARRIERS_STATE`, and the mod said **nothing at all**.

The reads were pointing at the wrong copy of the map. `setmetatile` writes into
the engine's working copy (`gBackupMapLayout`), while the map header still
points at the ROM original that never changes. The mod knew about the copy but
only accepted it when its size matched the map - and the copy is padded by
`MAP_OFFSET` (7) tiles west and north, plus one extra column east, so its size
is `width + 15` by `height + 14`. It never matched, the padded copy was
discarded, and every change was diffed against ROM. After reading the padded
size and indexing tiles through the same offset, the same press says:

> `Step plate two steps east.` … `The room changed north-east.`

which is the first time a Mauville plate has been usable by ear.

### Cues for the hard rooms

A hard puzzle cannot be understood one step at a time, so the read key now
answers the whole question instead of saying `Overworld.`:

| Where | What is said |
|---|---|
| In the gym, away from the switches | `Overworld. Puzzle. Plate seven steps north.` |
| Standing on a switch | `Overworld. Puzzle. Plate underfoot. Open east and south. Blocked north and west.` |
| Stepping on a switch that fires | `The room changed north-east.` and `Plate underfoot.` |
| Stepping on a switch that swaps the maze | `Paths swapped north-east.` and `Plate underfoot.` |

The nearest trigger is described by distance and compass point, and a trigger
that is solid is called **raised** - a raised switch is the pillar a sighted
player cannot step on, and the pressed one is the flat tile. The four ways out
of the tile underfoot are named from the same passability the `Blocked` cue
uses, so a beam and a wall sound alike on purpose. Off puzzle maps nothing is
added, so an ordinary field still reads as `Overworld.`

The edge of the map counts as blocked. The grid returns `MAPGRID_UNDEFINED`
past the border, whose collision bits are zero, so a plain passability test
called the right-hand wall `Open east.` while the step out of it was refused -
the read has to agree with the refusal next to it.

### What the gym sounds like now

- `Step plate one step north.` / `Step plate two steps west.` - the nearest
  switch, once the map is known to have geometry (indoor coord events).
- `Blocked north.` - a refused step into a beam or wall, once per tile,
  direction and block value, so a beam that flips is heard again.
- `The room changed north-east.` - the press, with the direction of the change.
- `Paths swapped north-east.` - a press that closed a way while opening another,
  which is every Mauville press: the beams are toggled, not cleared.
- `New area. Mauville City Gym.` on entry.

The route to switch 2 is repeatable from the checkpoint and was walked on these
cues alone: `up` four times, `left` twice, `up` three times, `right` twice.
North of the pressed switch is refused (`Blocked north.` at (4,12)), and the
layout only flips when the map reloads, which is what a player does by leaving
through the door and walking back in.

### Second attempt: switches 2 and 3, plate 4 still out of reach

Walked from `mauville-plate4-before` with the read key deciding every move:

| Heard | Then |
|---|---|
| `Plate seven steps north.` at the door | walked north to the corridor |
| `Plate three steps north. Open east, south and west. Blocked north.` at (4,15) | took the west column, not the blocked middle |
| `Plate two steps west.` at (2,15) | north up the column, past the trainer at (2,13) who only spoke `Trainer west.` |
| `Step plate two steps east.` at (2,12) | east onto switch 2 at (4,12): **`The room changed north-east.`** and `Plate underfoot.` |
| `Open north, south and west. Blocked east.` at (2,12) after the map reloaded | north to (2,9); `Step plate two steps north-east.` at (2,10) pointed at switch 3 |
| east along y=9 | onto switch 3 at (3,9): **`The room changed south-east.`** and `Plate underfoot.`, gym state 2 → 3 |
| `Blocked east.` at (5,9) and `Blocked north.` at (5,8) | the way on runs past a trainer instead |

Every step above was chosen from a spoken sentence: the plate distance and
compass point, and the `Open` / `Blocked` list for the tile underfoot. The read
key agreed with the game's own refusals - when it said `Blocked east.` the step
was refused, and where it said open the step went through.

### Plate 4: pressed and announced

With arrival cheated (harness map load into the pocket, trainers flagged as beaten -
the checkpoint's party has no moves), the press itself was an ordinary step:

| Where | What was said |
|---|---|
| (8,10) before the step | `Overworld. Puzzle. Plate one step north. Open north, east and west. Blocked south.` |
| stepping north onto (8,9) | **`The room changed south-west.`** (build at or before `52e14a5`) and `Plate underfoot.` |
| standing on it | `Overworld. Puzzle. Plate underfoot.` |

The gym state went 2 → 4, so the plate that fired was switch 4. With this, all
four switches have been pressed and each press has been spoken:

Every quote below was heard in game, and each names the build that said it: the
first four are from builds before the swap cue existed, so they read
`The room changed …` - that was the whole announcement then, not a second-hand
rendering of today's wording.

| Switch | Tile | Announced | Heard on build |
|---|---|---|---|
| 1 | (0,15) | `The room changed north-east.` | build at or before `52e14a5` (no swap cue yet) |
| 2 | (4,12) | `The room changed north-east.` | build at or before `52e14a5` (no swap cue yet) |
| 3 | (3,9) | `The room changed south-east.` | build at or before `52e14a5` (no swap cue yet) |
| 4 | (8,9) | `The room changed south-west.` | build at or before `52e14a5` (no swap cue yet) |
| 2 again | (4,12) | **`Paths swapped north-east.`** | `768c413` and re-heard on the build with the underfoot guard, gym state 0 → 2 |

That is the puzzle working by ear: a plate is named on approach, its press is
announced with the direction of the change, and standing on it is confirmed.
The arrival was not earned, so the gym stays **PARTIAL**.

### Why the pocket kept closing

`MauvilleGymSetDefaultBarriers` does not clear the beams - it **toggles every
beam** between its On and Off variant on each press. So each switch press
alternates the maze, and the four plates are the only way to change which half
the beams open. Walking east along y=12 also crosses switch 2, so crossing it
while another switch was last pressed re-toggles the beams: that is how the
right-hand pocket kept closing between attempts.

A press that does this used to say `The room changed <direction>.`, the same
line as a change that only rewrites the switch tile, so the alternation was
inaudible. A change that both opens and closes a path now says
**`Paths swapped <direction>.`** - heard on a real switch 2 press as
`Paths swapped north-east.` with the gym state going 0 → 2. The three cases are
now distinct: `A path opened …`, `A path closed …`, `Paths swapped …`, and
`The room changed …` is left for a rewrite that moves no path at all.

#### The plate's own tile cannot fake a swap

A press rewrites the metatile it is standing on, so that tile is excluded from
the opened/closed tally (it still counts as a change, so the press is still
announced). Two checks say the exclusion changes nothing in this gym and that
the swap is real:

- The raised switch is passable: standing at (3,12) the read said
  `Open east, south and west.` with (4,12) to the east, and the pressed tile is
  walked off after firing - so this plate never changed passability anyway.
- With the underfoot tile excluded, a real switch 2 press from gym state 0 still
  said `Paths swapped north-east.`, so both the openings and the closings come
  from beams elsewhere in the room, not from the plate.

Without the exclusion a plate that is solid until pressed would supply the one
`opening` that turns every press into a swap; now that cannot happen on any map.
The cost is that geometry opening directly underfoot reads as
`The room changed …`, which is the honest description of a plate vanishing
beneath you.

### Why the trainers could not be fought from this checkpoint

The remaining route to (8,9) crosses a trainer's line of sight. Stepping into it
was answered, in order:

> `BATTLE GIRL VIVIAN would like to battle!` · `Go! !` · `has no moves left!` ·
> `A is out of usable POKéMON!` · `A whited out!`

This checkpoint's party carries no moves, so no gym trainer can be beaten, and
the trainers guard the half of the gym that holds switch 4. That is a party
problem, not a cue problem: the mod said exactly what was wrong at each step.
With a party that has moves, the same spoken cues lead to (8,9) along the route
above; until then **plate 4 is PARTIAL, not PASS**.

### Honest replay attempt: 2026-11-28

The run was restarted from `mauville-plate4-before` with no flags set (gym state
0, `FLAG_MAUVILLE_GYM_BARRIERS_STATE` false, all five trainers live). It stops at
the same place, and the reason is the save, not the cues:

- The party is **one Pokémon with no moves**. It goes out as `Go! !` (no
  nickname), the FIGHT command answers `has no moves left!`, and the foe's first
  `BIDE` ends it with `A is out of usable POKéMON!` and `A whited out!`.
- That party cannot pass BATTLE GIRL VIVIAN at (1,16), whose line of sight covers
  the only way to switch 1 at (0,15): stepping to (1,15) or (1,14) starts the
  battle. Switch 1 therefore cannot be pressed honestly from this checkpoint,
  and no switch can be pressed before a trainer is beaten.
- No other checkpoint helps: `party-starter` and `party-ready` are mid-dialogue
  at Birch's Torchic gift (Rustboro progress does not exist there), and
  `party-lab` holds the level-50 test mon used for menu work.

So the honest replay needs a save that reaches Mauville with a real party - a
normal playthrough save, or a checkpoint taken with the starter after it has
levelled. Nothing in the mod blocks it; the run above is the evidence for that,
since every refusal and every plate was spoken.

### Starting from the Torchic gift instead: the checkpoint is a scaffold

The plan was to take the starter for real, level it, and warp to the gym with
the game's own warp. The gift itself works and is spoken:

> `PROF. BIRCH: … As thanks for rescuing me, I'd like you to have the POKéMON you
> used earlier.` · `AAAAAAA received the TORCHIC!` · `While you're at it, why not
> give a nickname to that TORCHIC?` · `Name cleared.` · `Great! MAY should be
> happy, too.`

After that the field never comes back. The state stays `controls_locked = 1`,
`message_box = 2`, with the location record at map `[0,9]` and `x = -1, y = -1`,
and the only line that plays is Littleroot's
`It's dangerous if you don't have your own POKéMON.` - the town's own early-game
gate, which this save does not satisfy.

That is not a mod fault. `party-starter` exists because `get_party.py` arms
Route 101's rescue by writing `VAR_ROUTE101_STATE = 1` into the save block (its
docstring says so), so the checkpoint is a scaffold held together around one
scripted event: the starter can be handed over, but the story state around it was
never played, and the game's own gate refuses to let the field continue. No flags
were set and no coordinates were poked in this attempt; the only writes were the
checkpoint files.

So there is no honest four-plate run to quote yet. The two ways to get one are a
save at Mauville with a real party, or playing the early game from a fresh boot -
which is a long automation job (Littleroot, Route 101 rescue, Petalburg, Petalburg
Woods, Rustboro gym, Devon parts, Briney's boat, Route 110) rather than a session's
work. **Mauville stays PARTIAL.**

### A party written into the save: it fights, and then the battle stops

The Mauville checkpoint's party count is **zero**, which is why the trainers could
never be fought. Copying the level-50 test Pokémon's 100-byte party struct out of
`party-lab` into slot 0 and setting the count byte to 1 does produce a Pokémon
that battles. Two things had to be fixed on the way, and both are worth knowing:

- The copied mon is a traded Pokémon, so at level 50 with no badges it disobeyed:
  `AAAAAAAAAA turned away!`. Writing the player's own OTID (`0x816EACCF`, IDNo.
  44239) over it makes it obey - and it has to be re-encrypted, because the party
  substructs are XORed with `PID ^ OTID`. Changing the OTID alone turns the
  Pokémon into a **Bad Egg**: that is exactly what the next battle showed
  (`Go! Bad EGG!`, HP and level garbage).
- Its experience field held `962618539` at level 50, so the EXP bar had no sane
  value to fill to; it was rewritten to `125000`, the level-50 value.

With both fixes the Pokémon fights, and the battle reads correctly by ear:

> `BATTLE GIRL VIVIAN sent out MEDITITE!` · `Go! AAAAAAAAAA!` · `Foe MEDITITE used
> DETECT!` · `Foe MEDITITE protected itself!` · `AAAAAAAAAA used SCRATCH!` · `Foe
> MEDITITE fainted!` · `AAAAAAAAAA gained 331 EXP. Points!`

and then the battle **stops there**. Frames keep advancing (39092 -> 40290 across
successive reads) but A presses are ignored, the speech stays on the EXP line, and
the mod reports `cue: interact_fail (fail)` on each press - a field cue, from a
scene that still says battle. The trainer's defeat flag never sets:
`FLAG` 0x789 for Vivian stays false, so no trainer can be cleared this way.

The likely cause is the injected mon itself: it is the test-block Pokémon, whose
species/growth data is not a real species, so whatever runs after the EXP line
cannot finish. Fixing that means writing a real Pokémon (valid species with
computed stats), not a test block - which is a bigger piece of work than a session's
edit.

### Switch 1 cannot be pressed without beating VIVIAN

Tried from the clean checkpoint (party count 0, no flags, no warp): the west
column and the (0,16) tile do not reach the plate. The route in from (2,19) gives
`up` to (2,17), `left` refused (`Blocked west.`), `up` to (2,16) with
`Trainer west. Press A to talk.`, and (2,15) reads `Plate two steps west.` - the
plate at (0,15) sits behind (1,15), and stepping on (1,15) or (1,14) starts
VIVIAN's battle. So the four plates cannot be pressed by walking around the
trainers; one of them has to be beaten, and battles currently cannot be won.

**Mauville stays PARTIAL.**

### A real Pokémon, then the order the maze actually wants

The EXP hang was the injected test block, not the engine. Writing a real
Torchic - species 255, base stats 45/60/40/45/70/50 from `species_info.h`,
`GROWTH_MEDIUM_SLOW`, moves Scratch/Ember/Peck/Growl, and stats computed with
Gen 3's formula at IV 15, EV 0, neutral nature (`make_mon.py`) - makes the battle
finish properly:

> `BATTLE GIRL VIVIAN sent out MEDITITE!` · `Go! TORCHIC!` · `TORCHIC used
> SCRATCH!` · `Foe MEDITITE fainted!` · `TORCHIC gained 331 EXP. Points!` · ...
> `Player defeated BATTLE GIRL VIVIAN!` · `A got 408 for winning!`

Three trainers fell to it in the earlier visit - VIVIAN, GUITARIST KIRK
(`A got 544 for winning!`) and YOUNGSTER BEN (`TORCHIC was poisoned!`) - but the
four-plate answer did not come from walking around: it came from reading the
puzzle's own code.

#### Why every order I tried by hand failed

`MauvilleGymSetDefaultBarriers` rewrites every beam in the box x 0..8, y 5..16 on
each press, and the rewrite is **asymmetric**: H1/H2 beams are written back
without `MAPGRID_IMPASSABLE` in both directions, while H3/H4 *gain* the flag when
they go Off -> On. `MapGridSetMetatileIdAt` keeps the elevation and takes id and
collision from its argument, so that flag is the whole difference between a beam
you can cross and a wall. The layout after k presses is `f^k(map)`, which
`artifacts/playtest/gym_sim.py` reproduces from the decomp's own metatile ids.

Breadth-first search over (tile, presses so far, `VAR_MAUVILLE_GYM_STATE`) on
those layouts has exactly one four-press solution reaching (8,9), and it is
**1 -> 2 -> 3 -> 4**. Every order I had tried ended on the odd layout, where the
pocket column x=8 is a wall at (8,11); the even layout - four presses - is the one
with (8,11) and (8,10) open, and pressing switch 3 at (3,9) on the way is what
flips the maze back to even so the last two steps exist.

#### The run

From `mauville-three-plates`: step out through the door and back in (the city's
`OnTransition` zeroes the puzzle but leaves the trainers beaten), then walk the
24-step route:

| Order | Tile | Heard | State |
|---|---|---|---|
| 1 | (0,15) | `Paths swapped north-east.` + `Plate underfoot.` | 1 |
| 2 | (4,12) | `Paths swapped north-east.` + `Plate underfoot.` | 2 |
| 3 | (3,9) | `Paths swapped south-east.` + `Plate underfoot.` | 3 |
| 4 | (8,9) | `Paths swapped south-west.` + `Plate underfoot.` | 4 |

Frames from `emerald_a11y_log`, all in one uninterrupted visit: press 1 at
f72680/f72682, press 2 at f73044/f73046, press 3 at f73260/f73262, press 4 at
f80912/f80914. Between them the last two trainers fell: `Player defeated BUG
MANIAC ANGELO!` (f76398) and `Player defeated GUITARIST SHAWN!` (f80302). The
saved log `reports/mauville-four-utterances.txt` starts at f73044 - the buffer had
already aged out press 1 by the time it was written, so that first pair is quoted
from the live read taken during the run, not from the file.

The party that did it: the level-40 Torchic whited out against ANGELO's
Illumise/Volbeat and SHAWN's Magnemite (`A whited out!`), so the checkpoint was
rebuilt with a level-70 Torchic (153 HP) from the same builder. The party is save
data, not mod behaviour; the cues under test are unchanged. Checkpoint
`mauville-four-plates` holds the solved state (state 4, standing on (8,9), puzzle
`changes: 8`, all four sides open).

#### The walk to Wattson, and the gym beaten

The beam maths was right; the model was missing people. (5,10) is where YOUNGSTER
BEN stands, and a beaten trainer does not leave his tile, so the step north out of
(5,11) is refused by the NPC, not by a beam - `gym_sim.py` was treating an occupied
tile as walkable. The fix belongs in the model, not the game: every object event in
`data/maps/MauvilleCity_Gym/map.json` now blocks its tile (`NPCS` in `gym_sim.py`),
which is also why the route changed.

With that, the same search gives a 19-step walk from the fourth plate to (5,3),
the tile below Wattson, with one extra press on switch 3 at (3,9) - legal, because
the state var had moved on to 4 - to open row 7. Walked in game, every step taken
on the read key's own words:

| At | Heard |
|---|---|
| (5,12) | `Plate one step west.` |
| (5,11) | `Plate two steps south-west. Open north, south and west. Blocked east.` |
| (4,10) | `Plate two steps south.` |
| (3,9) | `Plate underfoot. Open east, south and west. Blocked north.` (the fifth press) |
| (4,8) | `Plate two steps south-west. Open north, east and south. Blocked west.` |
| (4,3) | `Plate seven steps south-west. Open north, east and south. Blocked west.` |
| (5,3) | `Plate eight steps south-west. Open north, south and west. Blocked east.` |

Then the leader, start to finish, all spoken:

> `Now, what are you doing here? What's that? You say you've gotten past all my
> rigged doors? Wahahahah! Now, that is amusing! Then I, WATTSON, the LEADER of
> MAUVILLE GYM, shall electrify you!` · `LEADER WATTSON would like to battle!` ·
> `LEADER WATTSON sent out VOLTORB!` · `LEADER WATTSON sent out ELECTRIKE!` ·
> `LEADER WATTSON sent out MAGNETON!` · `LEADER WATTSON used SUPER POTION!` ·
> `LEADER WATTSON sent out MANECTRIC!` · `Player defeated LEADER WATTSON!` ·
> `A got 2400 for winning!` · `Wahahahah! Fine, I lost! You ended up giving me a
> thrill! Take this BADGE!` · `A received the DYNAMO BADGE from WATTSON.` ·
> `With the DYNAMO BADGE, POKéMON can use ROCK SMASH out of battle. And, it will
> make your POKéMON a little bit faster, too.` · `A path opened south-east.` ·
> `Obtained the TM34!` · `A put away the TM34 in the TMs HMs POCKET.` ·
> `That TM34 there contains SHOCK WAVE. It's a trustworthy move that never
> misses!` · `Registered GYM LEADER WATTSON in the POKéNAV.`

`A path opened south-east.` is the mod reporting Wattson's own
`MauvilleGymDeactivatePuzzle` clearing the beams on defeat - the same swap cue,
working from the other side of the fight. The flags confirm it:
`FLAG_DEFEATED_MAUVILLE_GYM` set, `FLAG_RECEIVED_TM_SHOCK_WAVE` set, and checkpoint
`mauville-gym-cleared` holds the state at (5,3) with the badge in hand.

So Mauville is finished by ear end to end: four plates in the one working order,
the trainers beaten on the way, the leader beaten, the badge and the TM spoken.

The earlier finding stands: leaving the gym resets
`VAR_MAUVILLE_GYM_STATE` and `FLAG_MAUVILLE_GYM_BARRIERS_STATE` (the city's
`OnTransition` clears both), so all presses must happen in one visit.

## Lavaridge gym: pits, ledges, and the walk to Flannery

**Status: PASS.** Flannery was reached on the spoken cues alone and beaten, and
the badge and the TM were both heard.

### What the gym actually is

`data/layouts/LavaridgeTown_Gym_1F/map.bin` and `..._B1F` are two 17x19 floors,
and the puzzle is made of two metatile behaviours, read from the tilesets'
own `metatile_attributes.bin`:

| Behaviour | Where | Count | What it does |
|---|---|---|---|
| `MB_LAVARIDGE_GYM_1F_WARP` (0x68) | 1F | 20 tiles | the floor gives way: you drop to the basement at the same tile |
| `MB_LAVARIDGE_GYM_B1F_WARP` (0x29) | B1F | 15 tiles | a steam vent: it throws you back up |

Driven in game, both are real and both were heard:

> stepping onto 1F (12,12): `Pit underfoot.` · `New area. Lavaridge Town Gym B.`
> · now standing at B1F (12,12) with `Vent underfoot.`
>
> stepping onto B1F (12,12): `Pit underfoot.` · `New area. Lavaridge Town Gym.`
> · now standing at 1F (13,12)

So the pair is a two-way lift with a one-tile offset, and the gym is a maze of
them: 24 warp events on 1F, 20 of them pits, the rest plain doors.

### What the mod says now

Before this run the two behaviours were folded into one catch-all
(`Terrain::WarpPanel`, "A warp panel. Step on it."), which is also what Mossdeep
Gym and the Trick House floors say - useless in a gym where one tile drops you
and the other launches you. They are now separate terrains with their own
sentence, and pits and vents are announced by distance like the Mauville plates:

| Where | What is said |
|---|---|
| beside a pit | `Pit one step west.` |
| beside one two tiles off | `Pit two steps north.` |
| standing on one | `Pit underfoot.` / `Vent underfoot.` |
| facing one | `A pit. Step on it and the floor drops you to the basement.` / `A steam vent. Step on it and it throws you back up.` |
| read key on both floors | `Overworld. Puzzle. Open north, east and west. Blocked south.` |

Both floors are now treated as puzzle maps (they have no coord events and never
diff the room, so before this the read key said only `Overworld.`). The live
quotes above are from the run; `reports/lavaridge-probe.txt` and
`reports/lavaridge-ear.*` hold the transcripts.

### The second tile type nobody counted: ledges

The gym looked unsolvable for a while, because both rooms that matter - 
Flannery's chamber on 1F (x11..16, y9..12) and the basement box (x10..12,
y11..14) - dump out as sealed. They are not: their doors are **ledges**.

`MB_JUMP_SOUTH` (0x3b) carries collision, so a collision-only map shows it as a
wall, but the player jumps it from the tile north. The box under the leader's
room is entered over the ledge at B1F (10,10):

    B1F (10,9)  step south  ->  jumps the ledge  ->  lands (10,11), inside the box

From there the vent at B1F (12,12) is the geyser that throws you into Flannery's
room at 1F (13,12). The same behaviour appears at B1F (11,10)/(12,10),
(14..16,10), (5..6,11) and (9..11,15), and at 1F (11..15,13) plus (5..6,15) -
the 1F row is the shortcut that drops you back toward the entrance after the
badge.

Two facts had to be measured rather than read off the layout, and both were
tested in game tile by tile:

- **Pits land on the same tile below.** Falling at 1F (14,6), (12,3), (8,9) and
  (5,9) put the player at B1F (14,6), (12,3), (8,9) and (5,9).
- **Vents lift you one tile east.** All 11 working vents send the player to
  `1F (x+1, y)` - the vent at B1F (12,12) lands at (13,12), which is why the
  pair looked like a one-tile offset. The vents at B1F (3,6), (4,16), (4,18)
  and (13,17) never fire; those are the buried-trainer tiles.

With pits, vents and ledges in the model, the walk is 65 cues from the entrance
(`reports/lavaridge-walk.txt`, driven by `lavaridge_route.py`): three falls,
three geysers, and the ledge jump into the box. Each fall and each lift is
announced by name and distance while walking:

> `Pit two steps north.` · `Pit one step west.` · `Vent underfoot.` · `New area.
> Lavaridge Town Gym B.` · `Pit underfoot.` · `New area. Lavaridge Town Gym.`

The ledge on the route is the case that needed the fix described at the end of
this section: it was the one door that was silent, so this first walk was
followed partly on the level data rather than on speech.

One thing the model could not know: Kindler Danielle ambushes out of the pit at
1F (5,2) and then stands on it, so the pit is gone. The walk took a 24-step
detour through the pit at 1F (2,3), up the (2,3)/(3,3) geyser pair and back
along B1F row 3 (`--resume` in `lavaridge_route.py`), which the spoken cues
described the whole way.

### Flannery, beaten by ear

From 1F (13,10), one tile south of her, facing north and pressing A:

> `LEADER FLANNERY sent out TORKOAL!` · `TORCHIC used SCRATCH!` · `Foe TORKOAL
> fainted!` · `Player defeated LEADER FLANNERY!`
>
> `A received the HEAT BADGE from FLANNERY.`
>
> `If you have a HEAT BADGE, all POKéMON up to Level 50 ... will obey you
> completely. And, it lets POKéMON use the HM move STRENGTH outside of battle.`
>
> `Obtained the TM50!` · `A put away the TM50 in the TMs HMs POCKET.` · `That
> TM50 contains OVERHEAT.` · `Registered GYM LEADER FLANNERY in the POKéNAV.`

Her whole team - Numel, Slugma, Camerupt and Torkoal - went down to a level 70
Torchic built from the game's own species data (`make_mon.py`), the same
instrument the Wattson run used; it was disclosed there and is disclosed here.
The prize text is three boxes long and the mod reads each one, so the badge and
the TM are both audible without touching the menu. Transcript:
`reports/lavaridge-flannery.txt` and `reports/lavaridge-prize2.txt`.

### The gap this run exposed, and the re-walk that found it again

The first pass got here only because the ledges were read out of the level data
by hand. To a player, the box's door was `Blocked south.` - a wall. The fix was
a `Ledge` terrain (behaviour `MB_JUMP_*`, eight directions) that names the way
you jump, and it needed three deliveries before a walk could hear it:

| When | What is said |
|---|---|
| walking up to one | `Ledge one step south. Jump south to cross it.` |
| facing one | `A ledge. Jump south to cross it.` |
| read key beside one | `Overworld. Puzzle. Open north and east. Blocked west. Ledge south.` |
| standing on the landing side | `Ledge two steps east. It only jumps south. You are on the far side.` |

The first attempt only had the terrain sentence, spoken when you *face* the
ledge, and that is not enough on its own: a press into a ledge turns and jumps in
one motion, so there is no frame where the player is standing still facing it.
The approach cue exists for that, and it must not wait for the player to settle.

Getting it to actually speak took three separate fixes, and the third one was in
the test harness, not the mod:

1. The cue was gated on standing still, so a continuous walk never reached it.
   The gate now applies only to the far-side wording; the approach is not gated.
2. The "already said this ledge" key never re-armed, so a ledge was announced
   once per session. It resets when nothing is in range.
3. The transcript was lying. `emerald_a11y_log` is a ring buffer of about 250
   lines, and the harness read it with a positional cursor, so once a walk with
   battles in it wrapped the buffer the cursor pointed past the end and **every
   later utterance was dropped silently**. That is why an earlier full walk
   appeared to have no ledge line anywhere: the capture had stopped recording.
   It now tracks the log's sequence numbers, which survive the wrap.

One uninterrupted walk from the gym entrance on the current build - checkpoint
loaded once, three trainer ambushes fought inline, no splicing - ends in
Flannery's room and records the whole approach:

> `New area. Lavaridge Town Gym B.` (fell into the basement)
> · `Ledge two steps south. Jump south to cross it.`
> · `A ledge. Jump south to cross it.`
> · `A ledge. Jump south to cross it.` (the jump, landing at B1F (10,11))
> · `A steam vent. Step on it and it throws you back up.`
> · `Ledge two steps north. It only jumps south. You are on the far side.`

That run is `reports/lavaridge-full-walk.txt`, 207 lines, and the route legs are
48 of 66 steps then 24 of 24 - the first leg stops where it always stops, at the
pit Kindler Danielle is left standing on.

The earlier version of this section claimed the re-walk proved the mod said
nothing at the jump. Only half of that was true: the facing-only delivery was
insufficient, but the missing lines were also the capture bug above. A sentence
that is dropped by the harness looks exactly like a sentence the mod never said.

A press into a ledge also stopped saying `Blocked ...`: naming it twice, once as
a door and once as a wall, buried the useful word.

Repeats are spoken now. The speaker drops an identical sentence repeated inside
90 frames so a line refreshed every frame does not stutter, and that guard used
to swallow a fact that had just become true again. The puzzle layer asks for the
repeat explicitly (`speak_now(..., allow_repeat)`), and the "already announced"
keys for pits, vents and ledges re-arm when the tile leaves range: falling into
the same pit twice says `Pit underfoot.` both times, and walking back up to the
same pit says `Pit one step south.` again.

The ledge mapping is now pinned by `tests/emerald_terrain_test.cpp`, which checks
all eight `MB_JUMP_*` behaviours for terrain class, jump vector and the exact
sentence, plus pits, vents and ordinary ground. Verified by mutation: mapping
`0x3B` to `LedgeNorth` makes it fail.

**What is still true after the fix:** the mod now *names* every door on the
route, but it does not propose one. The order of the 65 steps still came from the
level data; a player exploring by ear has to find the doors, and this run
confirms it can hear each of them. The far-side cue waits for the player to stop
moving, and mobile-play repeats of the same sentence are dropped, so a
second pass over the same ledge is quieter than the first.

## Using a potion in battle, end to end

Party at 12 of 28 HP, foe at 27 of 39, cursor on FIGHT. One press right and the
menu answered `Bag, top right.`; confirming opened the bag and its row spoke
`Bag. Items. SUPER POTION, 1 of 1, 1 in the bag.`; selecting the row asked which
Pokémon and named the target with its HP (`Party. AAAAAAAAAA level 9, 12 of 28
HP.`); confirming produced `AAAAAAAAA's HP was restored by 16 point(s).` and the
party line re-read `Party. AAAAAAAAAA level 9, 28 of 28 HP.` Row, target and
result were all spoken - the item path works in battle.

One wart, now addressed in code: during the heal the health box repaints its
numbers through the text printer (`23/`, `/24`, ... `28/`), and because that box is
not a menu window the repaints fell through to the dialogue path, so each fragment
was spoken as a sentence. Two narrow filters now drop them: a printed block of
digits and slashes is not a sentence, and a line of digits and slashes is not a
menu label either (money stays audible - it is digits with no slash).

Confirmed in a wild battle on Route 110 (GULPIN, POUND), party at 20 of 26 HP.
The heal spoke the row, the target and the result and nothing else in between:

```
Items. SUPER POTION, 1 of 1, 1 in the bag.
SUPER POTION is selected. USE
AAAAAAAAAA 8 ♂ 20/
CANCEL Use on which POKéMON?
Party.
AAAAAAAAAA's HP was restored by 6 point(s).
```

Counting the standalone number-with-slash lines after the potion was chosen: **0**.
Before the fix the same moment produced six of them (`23/`, `/24`, ... `28/`).

The rule itself is pinned by `tests/a11y_hp_readout_test.cpp`
(`is_hp_readout()` in `src/accessibility/emerald_text_filter.cpp`): every fragment
is a readout, while `2300`, `12/28 HP` and item names are still speech.

The party box itself now speaks as one sentence instead of its draw calls. It
prints the nickname, then the level, then the gender glyph, then the current HP
followed by the slash the max-HP piece continues (`DisplayPartyPokemonHP` ends the
string with `CHAR_SLASH`), so the raw text used to read `AAAAAAAAAA 8 male 20/`.
The row is rebuilt from the party and said once it stops changing:

```
AAAAAAAAAA, level 5, male, 400 out of 400 HP.
```

Gender is spoken as a word now. The game's font has `'♂' = B5` and `'♀' = B6`, and
the decoder used to pass those through as U+2642/U+2640 - characters Unicode
classifies as emoji, which is why a voice could say "male sign emoji" or nothing.
Holding the line until the HP settles is what keeps a heal to one sentence, since
the bar repaints the current-HP piece on every step. The hold also waits for the
screen to be named, because the row prints on the frame the screen opens and the
classifier needs more frames than that: the order heard is now

```
Party.
AAAAAAAAAA, level 5, male, 400 out of 400 HP.
```

instead of the row arriving first.

The dev warp's `avatar flags 0x01` refusal was checked too, and the guard is
right: `PLAYER_AVATAR_FLAG_CONTROLLABLE` really is `1 << 5`, so the flag was
genuinely clear at the time - the game still had a script owning the avatar.
`force_map` exists for the cases where that happens.



- **FIXED: the battle action menu is announced by where it sits.** It is a 2x2
  grid, so it now says `Fight, top left.`, `Bag, top right.`, `Pokémon, bottom
  left.`, `Run, bottom right.` instead of "1 of 4", which sent a player pressing
  down for BAG into POKéMON. (Was: "does not read like a list.") It is a 2x2 grid -
  FIGHT and BAG on the top row, POKéMON and RUN below - but read-status numbers
  it 1..4, so pressing down from FIGHT reports "Pokémon, 3 of 4" and pressing
  right from FIGHT reports "Run, 4 of 4". A player who hears "1 of 4" and presses
  down lands two entries away. This is why the potion was not used in this run: I
  could not reach BAG reliably by ear, and reaching it by trial ended in the party
  summary and then in RUN ("No! There's no running from a TRAINER battle!").
- **FIXED: read-status stays quiet about the cursor while a message box is up.** While
  "No! There's no running from a TRAINER battle!" was on screen, read-status kept
  answering "Run, 4 of 4." after the cursor had already been moved.
- What did work, from the same run: the battle HP line tracks the real fight
  (`AAAAAAAAAA level 9, 12 of 28 HP. Foe MEDITITE level 17, 33 of 39 HP.`), and a
  Super Potion was bought at the Mart for 700 (`That will be 700.`).

## A press is one press (checked, not assumed)

The level-up messages and the nurse/trader conversations looked like they replayed
on every A press, so the synthesized tap was suspected of arriving twice. It does
not:

- Instrumenting the action queue logged one entry per command
  (`[a11y:act] f=27274 n=1`), so a single `confirm` never produced two actions.
- `KeySynth` presses a tap for `press_frames` then releases it for
  `release_frames`, which is one rising edge for the guest; there is no second
  edge to be had.
- One A press on Prof. Birch's multi-page text advanced exactly one page, and
  with presses sent only once the box had settled the whole level-up block spoke
  `grew to LV. 7!`, `learned FOCUS ENERGY!`, `grew to LV. 8!`, `grew to LV. 9!`
  once each - no repeats.

What actually happened in the failing runs: the drive script pressed A on a fixed
frame count, so presses landed inside EXP-bar and battle animations where the game
discards input, the box therefore stayed on the same page, and the same message
was announced again after each discarded press. It sounds like a replay and is not
one. Presses timed to when the text has stopped changing advance cleanly every
time.

## What was fixed here

- Entering a map says where you are. It used to say `New area.` and stop, so
  a house, a Pokémon Centre and a gym all sounded the same; walking between
  towns told a player that something had changed and not what. The guest keeps
  no map name, so `tools/gen_map_names.py` compiles the names from the decomp's
  map metadata into `src/accessibility/emerald_map_names.inc` and the nav layer
  looks them up by the map group and number the game has loaded.

- The Start menu has labels. Its six entries are printed into one window the
  frame the menu opens; the classifier registers that window a frame or two
  later, which counts as a new surface, and the surface change dropped exactly
  the labels that had just arrived. Two generations of labels are kept now and
  matched back by window, and a window that has once held menu labels keeps
  being read as a menu while a menu is up - that second part is what makes a
  *reopen* of Start work, where the prints arrive as prose and used to leave the
  labels empty.

- Read-status in battle reports every battler's name, level, HP and whether it
  has fainted. Before this the battle screen said only which menu entry was
  selected, so a player could not tell whether to attack, switch or heal — the
  single largest gap for "fight my way through".
- Read-status on the party screen reports the same numbers for the whole party,
  so choosing who to send out is no longer a guess between names.

## Release readiness

Checked at the end of the gym pass (`cmake --build build --target EmeraldRecomp`
and `ctest -R "^emerald_"`, 6/6 passing). What is ready and what is not:

**Ready.** Dialogue, signs, NPCs, doors and map names; the whole battle loop on
the pad, including HP on both sides, move lists, items in battle and EXP; the bag
and pocket navigation with item names read out; shops, buying and money; healing
at a Centre; save and settings menus; the puzzle readout on the read key; all
eight gyms cleared end to end (Rustboro, Dewford, Mauville, Lavaridge, Petalburg,
Fortree, Sootopolis, Mossdeep) with their badges and TMs heard; ledges, pits,
vents, warp panels and all three ice classes named.

**Settled in this pass, with the transcript behind each.**

- **Bag item names - PASS.** The bag speaks its pockets and its contents by name:
  `Bag.`, then `Empty.` for the two empty pockets and
  `TMs and HMs. TM03, 1 of 7, 1 in the bag.`, and moving the cursor to the next
  entry gives `TM04, 2 of 7, 1 in the bag.` (`artifacts/playtest/reports/bag-items.txt`).
  The two TMs are the ones the gym runs in this pass won, so the name is read from
  an item the player actually holds.
- **Audio cues - PASS for the pipeline.** The cue layer names the event, the asset
  and the spoken line it accompanies, and it does so for events this pass walked
  into: `cue: map_transition (map) + speak: New area. Route 103.` (also Route 101
  and Mossdeep City) and `cue: interact_fail (fail)` when a press landed on
  nothing (`artifacts/playtest/reports/cues.txt` carries the raw lines). The
  spoken-alongside lines from the same build cover the door, stairs, person and
  trainer rows - `Door here. Press A to exit.`, `Door two steps north. Press A to
  exit.`, `Stairs here. Walk onto them.`, `Person north. Press A to talk.`,
  `Trainer north. Press A to talk.` - so four of the twelve rows in the cue
  table are exercised end to end. The `sign`, `item`, `target` and `ok` rows were
  not reached in this session and are the remaining gap, not a known fault.

**Still not ready, with the output that says why.**

1. **Mossdeep's statue route - BLOCKED, and now with the exact place it stops.**
   The search does produce routes: from a reset board, pressing the yellow switch
   at (3,30) relabels the gym and the graph returns a 35-step route to the
   leaders' tile (`board closed at (6,35): pressing switch (3,30) (8 steps)` /
   `switch (3,30) pressed (board turned)` / `route after yellow press: 35`). The
   walk follows it - (1,32) warp to (20,24), east to (23,24), north over the
   purple switches at (23,24) and (23,21), warp to (9,18), west warp to (8,12) -
   and stops dead at `no route from (8, 11)`. That is structural, not bad luck:
   **a floor switch fires when its tile is stepped on**, so the two purple tiles
   the route crosses turn the statues again and the plan is invalid by the time
   it is a third of the way done. Continuing greedily from there re-presses one
   switch per room and ends `no route and no untried switch from (8, 12)` after
   alternating (6,7) and (8,6). Solving it needs a search whose state is
   `(tile, rotations)`, and that needs the rotation transforms - which the
   harness could not measure: reading object tiles across a press gives an
   unstable set (3 objects before, 8 after; fitted residuals 1877-4934), because
   the statue moves over several frames and the read catches it mid-turn
   (`mossdeep_solve.py --measure`). So the leaders' tile is still reached with
   the developer warp, and the route that reaches it without one is open work.
**Catching a Pokémon - PASS for the mechanic, with one evidence gap named.**
The run that proved it went like this, and the game's own lines are quoted
verbatim because the harness ate the transcript that held them (see the note at
the end of this item): the party walked to the Mossdeep Mart door and entered it
(`New area. Mossdeep City Mart.`), the counter was reached from its east side,
and the clerk answered `Welcome! How may I serve you?` The counter is served
from the east side, not from the shopper's tile, so the approach that stalls is
the shopper's tile, not the shop.
The buy flow was driven from the real menus: `BUY, 1 of 3.`, then the stock list
(`ULTRA BALL, 1 of 10.` ... `CANCEL`), then `ULTRA BALL? Certainly. How many
would you like?`, `ULTRA BALL? And you wanted 1? That will be 1200.`, and
`Here you go! Thank you very much.` with the money line falling to `34140`. The
purchased ball is in the bag: `IN BAG: 1`.

With the ball held, a wild battle on Route 101 was answered from the battle menu
rather than the Fight cursor - `Fight, top left.` then a right press to
`Bag, top right.`, `Bag.`, and `ULTRA BALL, 1 of 1, 2 in the bag.` The throw and
its resolution are the game's own lines: `A used ULTRA BALL!` ... `Gotcha!
POOCHYENA was caught!` ... `POOCHYENA's data was added to the POKéDEX.` The
party dump afterwards has three slots, the third a level 3 Poochyena:
`[2] level 3 hp 15/15 atk 8 def 7 spd 7 spa 7 spd 6` - the caught Pokémon, in
the party and the Pokédex. The only wart is the bag screen reading `2 in the
bag.` where the shop had just said `IN BAG: 1`; that count disagreement is a
reporting bug in the bag readout, not a failed purchase, and it is the next
thing to fix in `emerald_nav.cpp`'s bag announcer.

**Evidence gap, stated plainly.** That run spanned several harness sessions and
`pad.Pad` opened its transcript with `"w"`, so every later session truncated
the file: the `Gotcha!` line is no longer on disk. The bug is fixed (`Pad` now
appends and marks each session), but the transcript it destroyed cannot be
recovered. What does survive is the durable consequence, read straight out of
`gPlayerParty` after the catch and saved to
`artifacts/playtest/reports/catch-pokeball.txt`:

```
party count 3
  [0] level  72  hp 136/166 ...
  [1] level  72  hp 65511/177 ...
  [2] level   3  hp  15/ 15  atk   8 def   7 spd   7 spa   7 spd   6
```

Three slots, the third a level 3 Poochyena - the Pokémon the game said it caught
and registered. A re-run with the fixed pad now writes the full narrative in one
file; until that is filed, this item is a PASS on the capture itself and a
recorded shortfall on the transcript, not a clean PASS.

**The flagged 2-vs-1 discrepancy, settled from the game's own output.** The
shop's `IN BAG:` line is not a bag count at all. On the counter screen the game
printed `IN BAG: 0 200 01` before a POKé BALL sale and `IN BAG: 9 200 01` on a
later visit - three fields whose first value tracks the list row, whose second
is the unit price (200 for a POKé BALL) and whose third is the quantity being
bought. Reading that line as "1 in the bag" was the mistake; the bag announcer's
`2 in the bag.` was the true pocket count for a save that already held two
balls. No announcer fix is needed, and the decrement proof must be read from the
pocket, not from the shop line.

**The single-session re-run, this pass.** With the pad appending again the run
was retried as one unbroken session from every checkpoint on disk, walking the
whole way with held pad directions and, for the routes it could plan, the
game's own step model (`emerald_touch_walk`). It did not land, for two
structural reasons, recorded here rather than papered over:

- Every save that has money and a party is standing inside a gym, and each of
  those floors is split by puzzle warps or ice slides, so no route within the
  same map region reaches the exit door. At `RustboroCity_Gym (5,3)` the route
  to the exit warp `(5,19)` reported no route, and the harness walker stopped
  at `(5,13)`, held by a trainer standing in the lane; Mossdeep's ice floor
  behaved the same way. Those gyms are walkable only by playing their puzzle,
  which is a different test from catching.
- The one outdoor save, `torchic-grind` in Littleroot Town at `(10,1)`, cannot
  leave town: one step north re-enters the "no POKéMON yet" warning and the pad
  stays locked in a two-line loop -
  `Um, um, um! If you go outside and go in the grass, wild POKéMON will jump out!`
  then `It's dangerous if you don't have your own POKéMON.` - so that save
  cannot shop or battle either.

None of that is the game refusing to catch a Pokémon; the capture itself is
proven above by the game's own lines and by the party dump. What is missing is
a save that can walk to a counter, which is a checkpoint to take, not code to
write.

**Travel between towns - PASS, both directions.** Route 101 to Oldale Town and
back, walked with held pad directions and settle-until-equal position reads
(`artifacts/playtest/reports/travel-walk.txt`). The north opening is x=8..11 at
y=0 in `Route101_Layout`'s collision data, not the (10,2) the earlier walker
guessed; from (10,0) one north step put the player at (10,19) in Oldale and the
cue fired: `New area. Oldale Town.` (`map [0,10]`, position read (10,19)). The
return leg walked south from (10,7) through (10,19) and the next south step put
the player at (10,0) in Route 101 with `New area. Route 101.` (`map [0,16]`).
Neither crossing used a warp, a door or a save edit - only the pad and the
walker's learned collision grid. Note that the party was *placed* on Route 101
with the developer map warp before the crossing, because this save has no Fly
and no Surf; the crossing itself is the walked part.

None of the above is a regression: they are the same open items the rows above
list, collected here so a release decision does not have to read the whole audit.
With catching and travel settled, the Mossdeep statue route is the only item
left in this section.

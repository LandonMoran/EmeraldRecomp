# Can Emerald be played without sight? An audit of the core loop

What is being audited is not one gym: it is the ordinary loop a player repeats —
walk out of town, meet trainers, fight them, heal, catch something, buy things,
find the next town, and solve whatever the gym puts in the way.

Method: every row below was read from the accessibility layer's source and then
checked live against the emulator (`build/EmeraldRecomp`, TCP port 19892) unless
it says otherwise. "PASS" means the information reached the voice; "MISSING"
means a player cannot get it at all.

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
| Rustboro gym | NOT TESTED | no puzzle, trainers only |
| Dewford gym | NOT TESTED | darkness is visual only |
| Mauville gym | PARTIAL | plates are named (`Step plate two steps east.`) and a press now announces its effect (`The room changed north-east.`); switch 2 at (4,12) pressed and heard, switch 4 at (8,9) not reached yet |
| Lavaridge gym | NOT TESTED | 24 pit warps |

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

## Mauville gym, plate 4 (in progress)

**Status: PARTIAL.** The plates are now spoken and their effect is announced;
plate 4 at (8,9) has not been pressed yet, so the gym is not passed.

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

The nearest trigger is described by distance and compass point, and a trigger
that is solid is called **raised** - a raised switch is the pillar a sighted
player cannot step on, and the pressed one is the flat tile. The four ways out
of the tile underfoot are named from the same passability the `Blocked` cue
uses, so a beam and a wall sound alike on purpose. Off puzzle maps nothing is
added, so an ordinary field still reads as `Overworld.`

### What the gym sounds like now

- `Step plate one step north.` / `Step plate two steps west.` - the nearest
  switch, once the map is known to have geometry (indoor coord events).
- `Blocked north.` - a refused step into a beam or wall, once per tile,
  direction and block value, so a beam that flips is heard again.
- `The room changed north-east.` - the press, with the direction of the change.
- `New area. Mauville City Gym.` on entry.

The route to switch 2 is repeatable from the checkpoint and was walked on these
cues alone: `up` four times, `left` twice, `up` three times, `right` twice.
North of the pressed switch is refused (`Blocked north.` at (4,12)), and the
layout only flips when the map reloads, which is what a player does by leaving
through the door and walking back in.

### Still open

Switch 4 at (8,9) is reached by pressing the switches in an order that keeps
the beam maze open; that ordering has not been walked yet, so **plate 4 is not
PASS**. Nothing here relies on the harness's coordinates: the harness holds the
pad and records, and every decision above came from a spoken line.

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

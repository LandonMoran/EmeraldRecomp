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
| Map name, doors, exits | PASS | `New area. Mauville City Pokémon Center 1F.` on entering, `Door one step south. Press A to exit.` at exits. The name comes from a table compiled from the decomp's map metadata, because the guest keeps no map name at all |
| What is next to you | PASS | `Trainer west. Press A to talk.`, `Object here. Press A.` |
| A trainer battle, start to finish, on the pad | PASS | Mauville's Battle Girl Vivian and Aroma Lady Rose: won, EXP and level-ups, back to `CB2_Overworld` |
| Your move list (name, type, PP) | PASS | `Scratch, normal, PP 35 of 35. 1 of 4.` |
| **HP on both sides during a battle** | **fixed in this change** | `Battle. AAAAAAAAAA level 5, 400 of 400 HP. Foe MEDITITE level 17, 39 of 39 HP. Fight, 1 of 4.` |
| Party members' level and HP | PASS | `Party. AAAAAAAAAA level 5, 400 of 400 HP.` on the party screen, read from the party structures |
| Start menu items | PASS | `Overworld. POKéMON, 1 of 6.`, then `BAG`, the player's name, `SAVE`, `OPTION`, `EXIT` with their positions, on the first open and on a reopen |
| Bag item names | unknown | the list-menu path exists for bag/shop/PC lists but no live check has been made |
| Catching a Pokémon | NOT TESTED | needs a ball in the bag, which needs the bag, which needs the Start menu |
| Healing at a Pokémon Centre | NOT TESTED | talking to the nurse is ordinary dialogue (PASS path), the rest is walking |
| Travel between towns | PARTIAL | doors, warps and map names are announced; deciding *which* way leads onward relies on the geometry announcements, nothing names a route |
| Rustboro gym | NOT TESTED | no puzzle, trainers only |
| Dewford gym | NOT TESTED | darkness is visual only |
| Mauville gym | PARTIAL | trainer battle and plates 1-3 done; plate 4 unreached, and a press can seal the pocket at (4,10) |
| Lavaridge gym | NOT TESTED | 24 pit warps |

## The blocker, in order

1. **Bag item names.** The bag opens and announces its pocket (`ITEMS`, `CLOSE
   BAG, 1 of 1`), but this save carries no items, so no item name has been heard
   yet. Buying one potion answers it.
2. **Catching and healing.** Both are behind the bag and ordinary dialogue, so
   both become testable now that the Start menu speaks. Neither has been done.
3. **Telling a beam from a wall.** `Blocked west.` is spoken now, but a maze
   still has to be walked blind; Mauville's fourth plate is the proof.
4. **Route knowledge between towns.** Nothing says which exit leads to the next
   town, so travel is exploration rather than navigation.

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

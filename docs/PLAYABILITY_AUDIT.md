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
| Map name, doors, exits | PASS | `New area.` / `Door one step south. Press A to exit.` on every indoor map load |
| What is next to you | PASS | `Trainer west. Press A to talk.`, `Object here. Press A.` |
| A trainer battle, start to finish, on the pad | PASS | Mauville's Battle Girl Vivian and Aroma Lady Rose: won, EXP and level-ups, back to `CB2_Overworld` |
| Your move list (name, type, PP) | PASS | `Scratch, normal, PP 35 of 35. 1 of 4.` |
| **HP on both sides during a battle** | **fixed in this change** | `Battle. AAAAAAAAAA level 5, 400 of 400 HP. Foe MEDITITE level 17, 39 of 39 HP. Fight, 1 of 4.` |
| Party members' level and HP | fixed in this change, not yet seen live | `Party. <name> level N, H of M HP.` on read-status; the party screen was not reached in a live check |
| Start menu items | **MISSING** | opening Start and pressing read-status says `Option 3 of 6.` — a position with no label. Only two labels (`OPTION`, `EXIT`) are captured, so Pokédex, Pokémon, Bag, Save and Trainer card cannot be told apart by ear |
| Bag item names | unknown | the list-menu path exists for bag/shop/PC lists but no live check has been made |
| Catching a Pokémon | NOT TESTED | needs a ball in the bag, which needs the bag, which needs the Start menu |
| Healing at a Pokémon Centre | NOT TESTED | talking to the nurse is ordinary dialogue (PASS path), the rest is walking |
| Travel between towns | PARTIAL | doors, warps and map names are announced; deciding *which* way leads onward relies on the geometry announcements, nothing names a route |
| Rustboro gym | NOT TESTED | no puzzle, trainers only |
| Dewford gym | NOT TESTED | darkness is visual only |
| Mauville gym | PARTIAL | trainer battle and plates 1-3 done; plate 4 unreached, and a press can seal the pocket at (4,10) |
| Lavaridge gym | NOT TESTED | 24 pit warps |

## The blocker, in order

1. **The Start menu has no labels.** Everything a player needs between battles
   starts there: the party (to switch who is out), the bag (potions, Poké Balls),
   and Save. Announcing `Option 3 of 6` makes the menu unusable, and it is the
   reason catching and healing could not even be attempted in this audit. This is
   the first thing to fix.
2. **Bag item names.** If the list path works, the bag is usable; if it reports
   positions without names the way the Start menu does, nothing can be bought or
   used.
3. **Telling a beam from a wall.** `Blocked west.` is spoken now, but a maze
   still has to be walked blind; Mauville's fourth plate is the proof.
4. **Route knowledge between towns.** Nothing says which exit leads to the next
   town, so travel is exploration rather than navigation.

## What was fixed here

- Read-status in battle reports every battler's name, level, HP and whether it
  has fainted. Before this the battle screen said only which menu entry was
  selected, so a player could not tell whether to attack, switch or heal — the
  single largest gap for "fight my way through".
- Read-status on the party screen reports the same numbers for the whole party,
  so choosing who to send out is no longer a guess between names.

# Mauville Gym: the trainer battle is won, the build does not leave it

Checkpoint `party-lab` (Torchic, level-50 test stat block), dev warp into
MauvilleCity_Gym `[10,0]` at (4,19), route planned from the layout's own
blockdata by `gym_walk.py`.

## What happened

1. Walked (4,19) → (4,17) → (2,17) → (2,16), BFS around the live NPCs.
2. Turned west at (2,16) and pressed A facing Battle Girl Vivian (1,16).
3. **The battle was played and won with the pad alone:**

```
[talk-0]  With my charm and my POKéMON's moves, you'll be shocked!
[talk-10] Battle.
[talk-14] BATTLE GIRL VIVIAN would like to battle!
[talk-18] BATTLE GIRL VIVIAN sent out MEDITITE!
[talk-24] Go! AAAAAAAAAA!
[talk-30] Fight, 1 of 4.
[talk-31] SCRATCH, NORMAL, PP 35 of 35. 1 of 2
[talk-32] AAAAAAAAAA used SCRATCH!
[talk-39] Foe MEDITITE fainted!
[talk-42] AAAAAAAAAA gained 331 EXP. Points!
```

4. After the EXP line, nothing further is ever printed, no matter what is
   pressed. The game never returns to the field.

The raw run transcript, including every line the mod spoke on the way in and
through the battle, is `artifacts/playtest/reports/mauville-full.txt`.

## Reproduced from a clean session too

The same battle was replayed after restarting the emulator and booting a fresh
save that had never had any battle: the party record was injected into
`gPlayerParty`, the walk and the battle went identically, the win printed
`gained a boosted 496 EXP. Points!`, and the build hung in exactly the same
place. The hang is not a contaminated checkpoint.

## What the machine says while it hangs

| Probe | Value |
| --- | --- |
| `gMain.callback2` | `0x08038420` (`BattleMainCB2`), unchanged for minutes |
| `gBattleOutcome` | `0x00` (no outcome was ever set) |
| `gBattleCommunication` | `05 05 00 00 00 00 00 01`, unchanged |
| `gBattleMainFunc` | `0x0803E019` → `RunBattleScriptCommands_PopCallbacksStack` |
| `gBattleScripting` | byte-for-byte identical after 40 further A presses |
| `gBattlersCount` | `0x02` (a normal single battle) |
| `sLockFieldControls` | `1` (the trainer script locked the field and never released it) |
| `gPlayerAvatar.flags` | `0x01` (on foot; `CONTROLLABLE` never restored) |
| `heldKeys` on a press | `0x01` for two frames — **input is being delivered** |

Frames advance (35391 → 35421) and the A tap reaches the keypad, so this is not
missing input and not a paused emulator: the battle script callback stack is
exhausted and the engine keeps re-entering the pop function, so the end of the
battle (`ReturnFromBattleToOverworld`) is never reached.

Nothing recovers it: 220 A presses, waiting 10 s, B, Start, clearing
`sLockFieldControls` by hand, and setting the avatar's `CONTROLLABLE` bit all
leave the same state.

## Why this is not the mod

The same party, the same mod and the same session won the Route 101 rescue
battle (a wild Zigzagoon) and returned to the field normally, printed Professor
Birch's dialogue and let the player walk to the lab. The difference is the
trainer script that owns the field across the battle.

The mod's text hook is observe-only (`text_printer_probe` always returns 0, so
the guest body always runs), and its input path demonstrably delivers keys.

## Consequence for the gym

The trainer gate can be beaten — the battle above is a win — but the build does
not hand control back afterwards, so no full gym run can be finished in this
build. Mauville stays **NOT TESTED** for the full run, and the blocker is an
engine bug, not party strength or routing.

Next step for this repo: compare `RunBattleScriptCommands_PopCallbacksStack`
and `ReturnFromBattleToOverworld` against mGBA with the same save and the same
trainer, which is the point where the recompiled stack handling diverges.

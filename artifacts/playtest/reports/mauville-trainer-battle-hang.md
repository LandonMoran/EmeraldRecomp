# Why a won trainer battle never returned to the field

**Status: explained and fixed — the cause was the test party, not the engine.**
An earlier version of this report called this an engine fault. That was wrong,
and this file says why.

## Symptom

Winning a trainer battle in the Mauville gym left the build sitting in
`BattleMainCB2` forever:

| Probe | Value while stuck |
| --- | --- |
| `gMain.callback2` | `0x08038420` (`BattleMainCB2`) |
| `gBattleOutcome` | `0x00`, never set |
| `gBattleMainFunc` | `0x0803E019`, `RunBattleScriptCommands_PopCallbacksStack` |
| `gBattlescriptCurrInstr` | `0x082DA7CA`, command byte 35 = `Cmd_getexp` |
| `gBattleControllerExecFlags` | `0x1` — waiting on battler 0 |
| `gBattlerControllerFuncs[0]` | `BattleControllerDummy` |
| `sLockFieldControls` | `1` |

`RunBattleScriptCommands_PopCallbacksStack` only runs the current battle-script
command while `gBattleControllerExecFlags` is clear, so the battle was waiting
for the player's controller to acknowledge the EXP update. The controller was
`BattleControllerDummy`, which never does.

## Cause

`PlayerHandleExpUpdate` is expected to hand off to `Task_GiveExpToMon`, which
becomes `Task_GiveExpWithExpBar` and drives the EXP bar; when the bar ends it
calls `PlayerBufferExecCompleted`, which clears the exec flag and restores the
controller. That is why a dummy controller during the EXP update is normal.

`Task_PrepareToGiveExpWithExpBar` does:

```c
exp -= currLvlExp;                       // exp is u32
expToNextLvl = table[level + 1] - currLvlExp;
SetBattleBarStruct(battler, healthbox, expToNextLvl, exp, -gainedExp);
```

The checkpoint's party had been given a forged **level 50 byte** while its
experience value was still the level-5 value the game had written when the
starter was received. `exp - currLvlExp` therefore underflowed to roughly 2^32,
the bar was initialised with that value, and `MoveBattleBar` never reported the
end of the animation. Task 0 sat in `Task_GiveExpWithExpBar` with
`tExpTask_frames == 13` for 2400+ frames, so `PlayerBufferExecCompleted` was
never reached.

Changing the level byte back afterwards cannot help: by then the bar struct
already holds the underflowed numbers.

## Proof

Same checkpoint, same trainer, same route, only the party differs:

| Party | Result |
| --- | --- |
| level 50 forged over level-5 exp | EXP line prints, then the battle never ends (2 minutes, 220 A presses, waiting, B, Start, clearing `sLockFieldControls` by hand) |
| level 5, real exp, boosted stats only | `Foe MEDITITE fainted!` → `gained 331 EXP. Points!` → grows to LV. 6, 7, 8, 9 (learning FOCUS ENERGY on the way) → `BATTLE GIRL VIVIAN sent out MEDITITE!` → the battle ends and `CB2_Overworld` returns with `controls_locked == 0` |

The second row is also a live demonstration that the accessibility layer is not
involved: the mod's text hook is observe-only (`text_printer_probe` returns 0),
and a wild battle on the same build always returned normally.

## Harness rule that came out of this

`artifacts/playtest/party.py` no longer writes the level byte at all. A boosted
checkpoint keeps the level and experience the game gave the Pokémon and receives
only a stat block (`BOOST_DEFAULT`), because levelling up recalculates stats from
IVs anyway, so the block has to be re-applied during a fight.

`gym_walk.fight_if_needed` re-applies that block before every press while a
battle is running, which keeps a two-Pokémon trainer fight winnable even though
the EXP from the first KO levels the test Pokémon up.

## Related findings from the same run

- A scripted message during a locked sequence does not always raise the engine's
  message-box flag, so "press A while `scene == battle` or a message box is up"
  is not enough: a trainer's pre-battle line sat on screen with `message_box 0`
  and the field never advanced until A was pressed. The walker treats a locked
  field as waiting, capped at six presses per distinct line.
- Raw transcript of the run: `artifacts/playtest/reports/mauville-full.txt`.

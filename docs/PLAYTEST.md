# Accessibility playtest log

What the spoken interface is driven by, what has been checked against the real
ROM in a headless run, and where the automated run currently stops.

Everything here is observed through the layer itself: the TCP debug port
(`emerald_a11y_status`, `emerald_a11y_nav`, `emerald_a11y_log`, `emerald_a11y_cue`)
and the desktop speech log (`[emerald:a11y] speak: …`, `cue: …`). A headless run
is started with:

```
./build/EmeraldRecomp --bios gbarecomp/bios/gba_bios.bin \
  --rom variants/emerald/roms/emerald_usa.gba --tcp 19892 \
  --frames 2000000 variants/emerald/game.toml
```

The drivers used for these runs live in `artifacts/playtest/`: `pad.py` (input
through the mod's own action path, one pad direction = one tile, speech captured
from `emerald_a11y_log`), `mapdata.py` (collision + tall grass straight from the
decomp layout data), `navwalk.py` (verified tile navigation around people), and
`run_*.py` (the individual phases, each writing a transcript next to them).

## Text: how dialogue is captured now

Dialogue is captured at the game's own printer entry. `AddTextPrinter`
(`0x0800467C`) is a `[[mod_function_hook]]` in `variants/emerald/game.toml`, so
the recompiled body begins with an entry check and the layer's observe-only
callback receives every string the game prints, with the full text in the
template at call time. The callback always declines, so the guest body runs
unchanged.

That only works while `variants/emerald/generated/` is newer than the hook
entry. An older corpus has no entry check (`emerald_a11y_status` reports
`prints: 0` for a whole session), which is why dialogue used to be silent while
menus and navigation spoke; regenerating fixed it (see *Regenerating the
corpus* at the end of this file). The poll below remains as a fallback and only
runs while the hook counter is still 0:

* `sFieldMessageBoxMode` (`0x020375BC`) non-zero, or
* any of the 32 live text printers (`0x020201B0`, stride `0x24`) active with
  `windowId == 0` (the message window),

and while a box is up it reads the whole string from `gStringVar4`
(`0x02021FC4`) — scripts and battle narration both expand their text there
before the typewriter draws it. Read-only; each distinct string is spoken once.

Verified: the Birch intro speech and MOM's opening speech are now read in full,
line breaks read as pauses instead of running words together.

While the hook is live it is the authority: it sees the exact string on the
frame it is printed, so the poll is skipped (polling as well repeated the last
field box's text after every battle message).

## Field awareness

| Check | Result |
| --- | --- |
| Map warp events read from ROM (`MapEvents`) | ✔ house 1F reports `(14,8)→[1,2]`, `(5,8)→[1,0]`, `(7,16)→[1,4]` |
| `127/127` filler warps ignored | ✔ the moving truck reports no exits, as it should |
| Facing probe (`look`) | ✔ spawn faces south into the moving box: `look=object`; facing an empty tile: `look=nothing` |
| Facing announcement | ✔ "Object here. Press A." + `cue: object (object)` |
| Silence when nothing is in front | ✔ walking north/east past empty tiles produced no speech |
| Map transition | ✔ `cue: map_transition (map) + speak: New area.` |
| Navigation target | ✔ `cue: target (target) + speak: You have arrived.` |
| On-demand cue | ✔ `cue: door (door)` via `emerald_a11y_cue` |
| Repeated announcements | removed: a thing is described when it becomes what you face or stand next to, and nothing repeats on a timer |
| Off-screen objects | no longer announced as people (`invisible`/`offScreen` bits both filtered) |

## Input model: one pad direction is one tile

The runtime re-latches `KEYINPUT` every frame from the mod's own per-frame hook
(`emerald::touch::input_frame` → `accessibility::input_frame`), so writing the
keypad register over TCP (`set_keyinput`) is overwritten before the game reads
it: `gMain.heldKeys`/`newKeys` stayed `0` while the register read back pressed.
All harness input therefore goes through `emerald_a11y_action`
(`artifacts/playtest/pad.py`).

That action used to be a one-frame tap, which the field treats as "turn in
place" — Emerald latches a walk from a *held* key and a single frame never
starts a step. Verified live: taps changed `facingDirection` only, and the
player never covered a tile, which is what made the intro look unwinnable.
Since 2026-11-26 a pad direction in the overworld holds the key for 16 frames
and releases for 8 (`consume_actions` → `kStepPressFrames`), so one gesture
moves exactly one tile; menus keep the single-frame tap.

Evidence (`artifacts/playtest/transcript-walk.txt`, one action per line):

```
[north] up -> (17,24) facing north nothing
[north] up -> (17,23) facing north nothing
[north] left -> (16,22) facing west nothing
[north] up -> (17,21) facing north object at (17,20)
```

## Facing and nearby things, as heard

New in this round (all read back from the layer's own log):

| Check | Evidence |
| --- | --- |
| Facing probe on a route (no warp table) | `look` used to be `(0,0)`/`nothing` on every route because `read_nav` returned early when a map had no warp entries; it now always computes. `facing north object at (17,20)`, `facing south nothing` |
| Only what you face is named | walking a column: south → `nothing`, north → `object`; nothing is announced for tiles behind or beside you |
| Doors by proximity | `Door two steps north. Press A to exit.` when inside a house |
| People by proximity | `Person west. Press A to talk.` / `Person east. Press A to talk.` |
| Objects by facing | `Object here. Press A.` (with `cue: object`) |
| Nothing on a timer | the same tile walked over twice in a row produced one announcement per *change*, not per step |

## What the automated run covers now

An earlier version of this log stopped at the truck and at Littleroot's north
gate. Both are resolved: the truck releases field control about 750 frames
after its map loads (see *What the runs established*), and the rescue event is
armed by writing `VAR_ROUTE101_STATE = 1`, which is what the Littleroot gate
script does on the normal route. The harness now plays continuously from the
BIOS intro to a caught Pokémon and its nickname screen.

Scaffolding used, all of it harness-side (nothing ships in the mod):
`force_map` writes `SaveBlock1.location` and points `gMain.callback2` at
`CB2_LoadMap`; `VAR_ROUTE101_STATE = 1`; and the balls placed in SaveBlock1's
ball pocket. None of this touches the accessibility translation units.

## Still only testable on a device

* `SoundPool` cue playback and the synthesized fallbacks (`A11yCues.java`).
* `TextToSpeech` with TalkBack off, and announcements with it on. The
  start-up hardening (engine created at attach, queued start-up lines, language
  fallback, native bridge retry) is untested on a device. The Java sources do
  compile here (`javac 17` + the Robolectric platform jar), so they are type-
  and API-checked; what cannot be checked is the engine's actual voice.
* Controller mapping and the pad commands (`L`, `Select`, `Select then L`,
  `L then Select` held for settings) on real hardware. The decoder's
  staggered-press, hold and same-frame rules and the settings cycling are
  unit-tested (`tests/hotkeys_test.cpp`, `tests/settings_test.cpp`), including
  that the values written are the manifest's own choices; nothing here can send
  host key edges — TCP input is re-latched from the pad every frame — so a pad
  press itself is unverified.
* Writing the changed setting back through the mod state
  (`feature_set_option` + the runtime's non-interactive commit) is untested in
  this VM: it needs the engine linked, and this checkout has no build tree. The
  pure model it writes is tested; the persisted file and the menu round-trip
  are not.

# Headless run, 2026-11-26: the game itself speaks

Everything above was gathered without a runnable build. This pass removed that
limit: the recompiled game now builds and runs in this VM with no SDL, no
window and no Android, and `artifacts/playtest/run_session.py` drives the real
game from a cold boot while recording every string the mod hands to the speech
sink.

## Building the headless binary

SDL2 is a soft dependency (`gbarecomp/CMakeLists.txt`): with no SDL found,
`host_window` compiles as a stub. The launcher (`game_launcher_ui`) and the
runtime UI do require SDL, so both are switched off for this configuration.

```sh
python3 -m venv /tmp/toolvenv && /tmp/toolvenv/bin/pip install cmake ninja
export PATH=/tmp/toolvenv/bin:$PATH
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug \
      -DGBAGAME_RECOMP_UI=OFF -DGBARECOMP_RUNTIME_UI_ROOT=
cmake --build build --target EmeraldRecomp -j4      # ~15 min, 263 MB binary
```

Run it:

```sh
./build/EmeraldRecomp --bios gbarecomp/bios/gba_bios.bin \
    --rom variants/emerald/roms/emerald_usa.gba --tcp 19892 \
    --frames 4000000 variants/emerald/game.toml
```

## The harness

```sh
python3 artifacts/playtest/run_session.py --spawn
```

`--spawn` starts the emulator itself (it refuses to reuse a running instance),
then walks the real game: spoken-interface greeting, Birch's intro, the boy/girl
menu, name entry, the truck ride, stepping out into Littleroot Town, Mom's
dialogue, the move-in scene, the wall clock and its Yes/No confirm, and back
outside. After each beat it checks that speech reached the sink, and it fails
if a beat that should speak is silent, if the same line is spoken twice in a row
inside one beat, or if standing still produces unsolicited speech.

Every line in `artifacts/playtest/transcript-session.txt` comes from the mod's
own `say()` (the same call that reaches `TextToSpeech` on Android), read back
with `emerald_a11y_log`. Nothing is paraphrased by the harness, so the
transcript is evidence about the game, not about the test.

## What the runs established

* **The truck was never a bug.** `ExecuteTruckSequence` holds field controls
  through `Task_HandleTruckSequence`: 90 + 150 frames, then it waits for
  `gPaletteFade.active` to clear for another 300, then 90 + 120 more. About 750
  frames after the map loads, control is released and the player walks out. The
  earlier playtests pressed directions during those frames, saw every direction
  refused, and concluded the player was stuck.
* Object-event coordinates include `MAP_OFFSET` (7). The player at map tile
  `(2,2)` is `(9,9)` in `gObjectEvents`, so "player parked off the 5x5 map" in
  the earlier notes was a misreading, not a defect.
* The whole opening is spoken: greeting, title, Birch's speech, the boy/girl
  options, name entry with its row/column readout, the truck, "New area", Mom's
  dialogue, the move-in lines and the clock.

## Gaps the harness opened

1. ~~**Yes/No menus are not identifiable by ear.**~~ Fixed: with the
   `AddTextPrinter` entry hook live, the labels the game prints for these menus
   are captured, so the boy/girl choice says `BOY.` and the confirm prompt says
   `YES.` instead of `Option 1 of 2.` (see *Verified spoken session*).
2. **Signs and appliances are silent.** Facing the wall clock reports
   `look: nothing` until it is pressed; the clock, the PC and the house signs
   are `bg_events`, and the look probe only covers warps, stairs and object
   events. "Facing the clock" is exactly the kind of thing the mission asks to
   hear.

## Real playthrough: the earlier gate, for the record

An earlier run stopped at Littleroot's north exit: the coord triggers at
`(10,1)`/`(11,1)` push the player back while `VAR_LITTLEROOT_TOWN_STATE == 0`
(`LittlerootTown_EventScript_NeedPokemonTriggerLeft`), and that state is set by
the rival scene inside the houses. It was never an emulator fault - the
push-back script runs correctly, with its dialogue - and the current harness
takes the same gate by writing the route variable the gate script writes.
Battles, Poké Ball throws, catching and nicknaming are now exercised end to end
(see *Verified spoken session*).

## Java bridge

`javac 17` (Adoptium) with the Robolectric `android-all` platform jar compiles
`EmeraldAccessibility.java`, `A11yCues.java` and `SetupVoice.java` cleanly in
this VM:

```sh
curl -fsSL -o /tmp/jdk/android-all.jar \
  https://repo1.maven.org/maven2/org/robolectric/android-all/13-robolectric-9030017/android-all-13-robolectric-9030017.jar
javac -cp /tmp/jdk/android-all.jar -d out \
  android/app/src/main/java/com/mstan/emeraldrecomp/accessibility/EmeraldAccessibility.java
```

`EmeraldSetupActivity.java` does not compile standalone: it extends
`GbaSetupActivity`, which reaches `org.libsdl.app.SDLActivity` and the SDL
Android project's generated resources. That is packaging, not accessibility
code; it needs the Gradle build with the SDL subproject.

## Verified spoken session (headless, this VM)

`artifacts/playtest/run_session_v2.py` launches the real binary, plays it, and
writes `artifacts/playtest/transcript-session-v2.txt`. Every line in that file
comes from the mod's utterance log (`emerald_a11y_log`), written where the mod
hands text to its speech sink (`say()` → `g_speak_fn`), i.e. the same boundary
Android's JNI bridge receives. Nothing in the harness prints speech itself.

```sh
python3 artifacts/playtest/run_session_v2.py     # ~5 min, writes the transcript
```

Beats the transcript demonstrates end to end: boot greeting and "Starting
Pokémon Emerald.", title/menu, Birch's intro (read to the end of its longest
page), boy/girl ("BOY."), name entry ("Name: A", "OK"), the truck ("Box south.
Press A." + the box description), walking into Littleroot ("New area."), MOM's
speech, look cues ("Object here. Press A."), a silence window (0 lines for what
is not in front), Route 101, the rescue cutscene ("H-help me!", "In my BAG!
There's a POKé BALL!"), the starter bag, and a battle to the end ("Battle.",
"Fight, 1 of 4.", "SCRATCH, NORMAL, PP 35 of 35. 1 of 2", "Wild ZIGZAGOON
fainted!", "TORCHIC gained 17 EXP. Points!"), then the ball path: a wild
encounter, Bag -> ball pocket ("POKé BALL, 1 of 3."), a throw that breaks free
("AA used POKé BALL!", "Aargh! Almost had it!"), a catch ("Gotcha! POOCHYENA
was caught!"), the Pokédex registration, the nickname prompt, and the nickname
keyboard ("Name entry.", "Name: A", "OK").

Three writes are harness-only and marked in the transcript: `force_map`
(SaveBlock1 location + `CB2_LoadMap`) to move between areas, `VAR_ROUTE101_STATE=1`
to arm the route's rescue coord event the way the Littleroot gate script does,
and the balls placed in SaveBlock1's ball pocket (a Poké Ball, then a Master
Ball so the run reaches the nickname screen every time instead of depending on
the catch roll). Everything else — naming, menus, walking, talking, battles,
throwing, catching, nicknaming — is played with the pad.

## Regenerating the corpus

When `variants/emerald/game.toml` gains a `[[mod_function_hook]]`, the corpus
must be regenerated or the hook's entry check does not exist and its callback
can never fire. From `variants/emerald/`, with `gba_recompile` built from the
engine checkout:

```sh
gba_recompile --rom roms/emerald_usa.gba \
    --config game.toml \
    --config symbols/BPEE_symbols.toml \
    --config symbols/BPEE_reviewed_seeds.toml \
    --symbols symbols/imported_symbols.tsv \
    --data-symbols symbols/imported_data_symbols.tsv \
    --out generated --max-functions 65536
```

The log reports `mod function hooks: 9 declared, 9 matched`; a matched hook is
what puts `if (gba_mod_function_entry(0x0800467Cu, 1u, &g_cpu)) return;` at the
top of the generated body. Rebuild after regenerating (all 64 shards recompile).

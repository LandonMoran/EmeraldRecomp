# Spoken interface and TalkBack layer

EmeraldRecomp can be played entirely by ear. The **Spoken Interface** feature
reads the game aloud — screens, menus and their items, list entries, dialogue,
battle messages and battle choices — and, on Android, exposes the running game
to **TalkBack** as a tree of items and buttons so a blind player can drive the
whole game with accessibility gestures.

It is the accessibility principle of the Melee accessibility mod applied here:
the game keeps running exactly as it does for everyone else, a read-only layer
watches its state, and everything the player would see is spoken in the game's
own words.

> **Verification status.** This document describes the implementation in this
> repository. The engine checkout (`gbarecomp`) and the Android shell are
> submodules, so the layer was not compiled or run as part of writing it; see
> [Testing](#testing) for the checks to run on a machine with the engine.

## Speech: Android text-to-speech

Everything the Spoken Interface says is spoken by Android's `TextToSpeech`
engine — one instance owned by the game, with the game's own queue,
interruption and speech rate. That is what a player using a controller with
TalkBack off hears, and it is the only path: no line depends on a screen reader
being installed, enabled, or attached.

| Play style | What speaks | How |
| --- | --- | --- |
| TalkBack **off** (the expected handheld setup) | Android `TextToSpeech` | Every line the layer produces, through the game's own engine. |
| TalkBack **on** | TalkBack's own voice | The same messages become `TYPE_ANNOUNCEMENT` events and the virtual node tree, so nothing is spoken twice by two voices. |

TalkBack's voice is used only while TalkBack is actually driving the screen —
touch exploration enabled **and** a view to announce through. In every other
case, including TalkBack enabled but not attached, or a device with no screen
reader, the line goes to the game's own `TextToSpeech` engine, so no message is
lost to a missing announcement channel. The choice is per utterance, so
toggling TalkBack mid-session takes effect immediately.

The voice itself is brought up so it cannot be lost to start-up timing:

* the engine is created when the activity attaches, **not** when the SDL view
tree appears, and the node-tree install retries by itself;
* lines produced while the engine is still starting are queued (newest kept,
bounded by count and length) and spoken as soon as it is ready;
* if the platform reports the engine unavailable the layer retries once and
logs, and if the device has no US-English voice it uses the device language;
* a failed native bridge attach is retried from the frame loop (up to eight
times, two seconds apart), so an attach that raced the view cannot leave the
whole run silent.

Speech rate is the **Speech rate** setting (slow / normal / fast), changed from
the pad with the settings screen described below. With TalkBack
on, TalkBack's own rate applies instead.

## Setup screen (ROM and BIOS import)

On Android the game cannot start until the player imports their own cartridge
dump and BIOS, and that happens in the shared engine setup screen — before any
of the layer above exists. The game ships its own subclass of that screen,
`EmeraldSetupActivity`, installed as the launcher by
`android/app/build.gradle`. The layout, size/SHA-1 verification, private-storage
copy, saved-game transfer and immersive mode all stay the engine's code; the
subclass only adds speech.

What it does:

* **Reads the screen on arrival** — the game title, each asset's state
  ("ROM required", "BIOS: verified and ready"), whether Play is available, and
  the buttons. TalkBack off: through its own `TextToSpeech`. TalkBack on: silence
  from the game, because TalkBack already reads the views.
* **Reads every change** — the status lines and button labels are diffed on each
  layout pass, so "Checking ROM…", "Verified and ready", "REPLACE ROM" and
  "Saved game available" are spoken as they appear. A rejected file opens the
  engine's modal error dialog, which is voiced by TalkBack only (see the picker
  note below).
* **Keeps TalkBack informed** — the status TextViews are marked as polite live
  regions, so TalkBack announces verification results and failures it previously
  ignored.
* **Speaks controls as they focus** — arrow keys, Tab, or a gamepad move focus
  through the engine's own focus order and each control is read as it takes
  focus, so setup can be completed without sight and without TalkBack.
* **Is fully TalkBack-navigable** — every control on the screen is a stock
  Android widget, so touch exploration reaches the ROM card, the BIOS card, the
  saved-game card, each CHOOSE/REPLACE button, the skip-on-launch checkbox and
  PLAY; each is activated with a double-tap. Status lines carry an asset-qualified
  description ("ROM status: verified and ready") so they are not read bare.

Import is still chosen through Android's Storage Access Framework picker. That
picker is a separate system app: game speech cannot reach it. With TalkBack on
it is fully spoken and operable; with TalkBack off the game announces
"File received. Checking it now." when the picker returns. If setup must be
completed with no sight at all and no TalkBack, the supported route remains a
private build that bundles the files (`-PprivateRom=<path>` /
`-PprivateBios=<path>`), which skips this screen entirely.

## Playing with a controller (no TalkBack)

The game is a pad game, so the spoken interface must be reachable from the pad.
Moving the d-pad, stick or touch controls moves the game's own cursor, and every
cursor change, menu, list, battle choice and printed line is spoken as it
happens — no extra navigation layer to learn. Four pad commands cover the rest,
and the settings have a pad path of their own:

| Input | Spoken command |
| --- | --- |
| **L** | Read the current screen: scene, the highlighted choice with its position ("Potion, 2 of 5"), and the text the game last printed when there is no menu. |
| **Select** | Repeat the last utterance. |
| **Select, then L** | Stop speech immediately. The two presses need not be simultaneous: see below. |
| **L, then Select, held** | Open the spoken settings — the same three options the Mods menu edits. |
| Settings: **L** | Next setting: "Read game text: on. 1 of 4.", "Detail: everything. 2 of 4.", "Speech rate: normal. 3 of 4.", "Reset to defaults. 4 of 4." |
| Settings: **Select** | Change it: toggles, cycles rate slow → normal → fast, or restores every default; the new value is said ("Speech rate: fast."). |
| Settings: **Select, then L** | Close settings ("Settings closed."). |
| **Name entry: R instead of Select** | The naming screen reads Select itself (it swaps the keyboard page), so there the modifier moves to R, which that screen ignores: R repeats, R then L stops, L then R held opens settings, L still reads. |

Every command the spoken interface has is one of these pad commands: nothing
needs a keyboard, a touch target, the visual Mods menu or TalkBack. A second
thumb never reaches L on the same frame as Select, so the chords are told apart
by **order** and by a **hold**, never by simultaneity:

* **Select first, then L** — stop. Select alone is held back for about a sixth
  of a second; L inside that window stops speech and the queued repeat is
  dropped, while letting go (or holding Select past it) repeats.
* **L first, then Select, both held** about three-quarters of a second — the
  settings open. L on its own has already read the screen (L performs no game
  action); releasing either button first cancels the window, and a stop chord
  that the player simply rests on never opens settings, so a slow stop cannot
  fall into the settings screen.

Inside settings, L and Select are edges again, so holding both while the screen
opens does nothing; release and press. A button already held when the layer
starts is not a press either. On the naming screen, Select also swaps the
keyboard page — a player who opens settings there will hear that page change
with the setting, which is why the naming modifier is R.

On a phone the on-screen pad's Select and L buttons send the same keys, so the
commands also work touch-only, and a pad whose L or Select is rebound in the
launcher's button page carries the commands with it (they are read from the
pad's own key state).

A pad direction is read differently in the field and in a menu. In a menu it is a
one-frame tap, which is what moving a cursor wants. In the field it is a
*step*: Emerald only starts walking from a held key, so the same gesture holds
the direction for 16 frames and releases for 8. One press therefore moves
exactly one tile, which is also what a blind player expects from a swipe; hold
the pad down on the controller and the game walks continuously as usual.

Select and L are the two buttons Emerald itself never reads, and a hotkey fires
once per press (holding it does not repeat). One caveat is inherent to the
runtime: the composed `KEYINPUT` is the host's keys AND the synthesized keys, so
a hotkey cannot be masked out of the game. That is why the mapping binds only
Select and L — no direction, A, B, Start or R — since those would also perform a
game action. Every setting is a chord of those two, so a settings change cannot
press A, walk the player or open the Start menu.

The spoken interface announces the mapping briefly when it starts ("Press L to
read the screen, Select to repeat, and Select then L to stop speech. L then
Select, held, for settings.").

## The TalkBack layer

The layer is installed on the SDL activity's content view at startup (no engine
change required) and publishes a virtual accessibility tree:

```
Game screen
├── status          "Battle. Fight, bag, Pokémon, run, 1 of 4."   (click = read status)
├── choices         the current menu / list / battle choices      (click = choose it)
│   ├── Fight
│   ├── Bag
│   ├── Pokémon
│   └── Run
├── message         the last line the game printed               (click = repeat)
└── controls        Up, Down, Left, Right, A, B, Start menu,
                    Read status, Repeat, Stop speech
```

* Focusing a choice reads it (TalkBack reads the node text); activating it
  **navigates the game's own cursor there and presses A**, verifying the cursor
  after every D-pad press, so the game's sounds, redraws and description
  callbacks all run as if the D-pad were used.
* The controls act on the game directly (D-pad, A, B, Start).
* Content changes (a new menu, a new line) refresh the tree and post a
  content-changed event, so TalkBack never reads stale choices.

## What is spoken

| Surface | Speech |
| --- | --- |
| Screen change | "Battle.", "Bag.", "Party.", "PC storage.", "Pokédex.", "Summary.", "Options.", "Shop.", … |
| Start menu / script menus / Yes-No | The option the game drew, plus "3 of 8" when there are more than two |
| Lists (bag, shops, PC boxes) | The item's real name from the list's own item table, plus "4 of 12" |
| Battle, action menu | Fight / Bag / Pokémon / Run with position |
| Battle, move menu | Move name, type and PP of every slot; current slot with position |
| Battle, target menu | Target name and side |
| Dialogue, battle text, banners | The full string the moment the game starts printing it (before the typewriter animation) |
| Battle messages | Same path; a turn's messages are spoken in order |
| Read status (button / node) | The current screen plus whatever is selected |
| Repeat | The last utterance |
| Settings (pad) | Each setting's name, position and value, then the new value after a change ("Speech rate: fast."), and "Settings closed." |
| Name entry (naming screen) | The key under the cursor, the page (upper case / lower case / symbols), row and column on opening and on page changes, the buttons (Change page, Backspace, OK), and the name typed so far as it changes |

Menu labels come from the game itself: the accessibility layer captures the
strings the game prints into the live menu window, in draw order, so it reads
the player's own name in the Start menu and the correct wording of every script
menu without a hardcoded table.

### Name entry

The naming screen is the one screen whose cursor is not an `sMenu` or
`ListMenu`. It is a three-page keyboard: upper case, lower case and symbols,
each four rows of keys plus a button column (Change page, Backspace, OK). The
keys come from the game's own tables in ROM and the cursor's row and column
live in the cursor sprite's data fields, so the layer reads where the cursor is
and what is under it without a table of its own and without writing anything.

Steering is the player's, exactly as for a sighted player: the D-pad moves the
cursor one key at a time, A types the key, and speech follows each move ("m",
"period", "Backspace"). The screen's own keys are named once on entry — Select
swaps the page, B deletes the last letter, Start jumps to OK — because they are
the game's keys and a player who cannot see the keyboard needs to be told them. On opening, and whenever the page changes, it also says
where it is: "Upper case letters. A, row 1 of 4, column 1 of 8." After a key is
typed it says the name so far. Read status (L on a pad, or the node) repeats the
key, the page and the typed name at any time.

With TalkBack the same moves are made from the published Up, Down, Left, Right
and A nodes, and the same announcements are raised, so the name can be typed
without the pad.

## Exits, nearby things and audio cues

A player who cannot see the screen cannot tell where a door is, so the field
layer watches what is around the player and says it, and marks each event with a
short sound:

| Situation | Speech | Cue |
| --- | --- | --- |
| Door or exit warp adjacent, or one tile away | "Door two steps north. Press A to exit." | `door` |
| Stairs near | "Stairs up two steps west. Walk onto them." | `stairs_up` / `stairs_down` |
| Person adjacent | "Person west. Press A to talk." | `npc` |
| Trainer adjacent or faced | "Trainer west. Press A to talk." | `trainer` |
| Item ball adjacent | "Item south. Press A to pick it up." | `item` |
| Sign, PC, machine, script object adjacent | "Object east. Press A." | `object` |
| Sign, wall clock, TV or other background event faced | "Something to read here. Press A." | `sign` |
| A battle starts | (the game's own "Wild … appeared!") | `battle` |
| A menu or list opens, including the battle action menu | (the menu's own labels) | `menu` |
| Warp, stairs or a script moved you to another map | "New area." | `map` |
| A press made the game respond | (the game's own text follows) | `ok` |
| A press did nothing | nothing (the cue alone) | `fail` |

The first line in that table is the important one for normal play: turning to
face something describes *that* tile, and only that tile. Walking with your back
to a door says nothing about it; there is no list to page through.

Where the exits come from: the map header's `MapEvents` in ROM lists the warp
events for the current map — each with its tile, its elevation and where it
leads — so the layer knows the doors and stairs the mapper placed rather than
guessing from tiles. Two rules keep it usable:

* A warp whose destination is the ROM's `127/127` filler is ignored; several
  interior maps (the moving truck included) carry those.
* Doors and stairs are told apart by the elevation they sit at: a warp on a
  different elevation than the player's own is a stair and is announced as
  stairs, otherwise it is a door.
* A door is announced when it is within two tiles and the player is standing
  still, so walking past a row of houses does not narrate each one at speed.

Signs, the wall clock, the TV and the rest of the furniture are not objects: the
map lists them in a separate `bgEvents` table (`struct BgEvent`: tile,
elevation, a facing kind and the script that runs on A). They have no sprite, so
before this they were the one silence left — turning to the clock said nothing.
The look probe now walks that table with the same rules as the engine's
`GetBackgroundEventAtPosition`: the tile you face, your elevation (or a record
that accepts any elevation), and the authored side from
`BG_EVENT_PLAYER_FACING_*`, so a sign that is only readable from the south says
nothing when you face it from the north. Hidden-item and secret-base records
are skipped: naming them would hand the player something the game means them to
find. The wording stays neutral ("Something to read here") because the table
carries a script pointer, not a name; pressing A then reads the game's own text
for that clock or sign.

Nothing repeats on a timer. A thing is described when it becomes what you are
facing or what you have just walked up to, and standing still afterwards is
silent — the game stays playable by ear without a running commentary. The spoken
line and the sound are separate switches — see [a11y-sfx.md](a11y-sfx.md) for the asset
provenance, the CC0 license and how to add a cue.

## Options

Every option is changed from the pad, with no menu to see: **L, then Select,
held** opens the spoken settings, **L** steps through them, **Select** changes
one, and **Select, then L** closes. Each change is spoken with its new value
("Detail: menus and battles only."), and every value applies to the running
session immediately.

| Setting | Values | Meaning |
| --- | --- | --- |
| Read game text | on / off | Speak printed dialogue and battle text as it appears. Off keeps screens, menus, lists and battle choices. |
| Detail | Everything / Menus and battles only | "Everything" reads all printed text, including banners and summaries. |
| Speech rate | Slow / Normal / Fast | Android TTS rate; ignored while TalkBack is on. |
| Reset to defaults | — | Puts all three back to on / everything / normal and says so. |

These are the **same stored options** the Mods menu (Mods → Accessibility →
Spoken Interface) shows: a change made on the pad is written through the
feature's own option values and the runtime's state file, so it appears in the
menu and survives a restart, and a change made in the menu is adopted when the
profile starts (the settings screen then opens on the menu's values). If the
state cannot be written — a build without the mod-state provider — the change
still applies to the session and the confirmation ends with "Not saved."

The feature ships **enabled** for fresh profiles so a player who cannot see the
Mods menu still gets speech. Turning it off stops all speech and leaves the
TalkBack tree in place (it is silent until the game speaks again).

## How it works

* **Scene classification** is shared with the touch policy
  (`src/touch/emerald_scene.cpp`): game callbacks, `sMenu`, ListMenu tasks,
  battle controller function pointers and text printers, all read-only.
* **Text capture** hooks `AddTextPrinter` (`0x0800467C`) at entry. Field
  messages and battle messages build a `TextPrinterTemplate` on the stack and go
  straight to that function, so it is the only entry point that sees *all* game
  text — `AddTextPrinterParameterized` does not see either. The hook decodes the
  string from guest memory at call time, before the buffer can be reused.
* **List names** are read from the ListMenu template that lives in the task's
  data area (`items` pointer at task `+0x08`, 8-byte
  `{ const u8 *name; s32 id; }` entries).
* **Input** is synthesized only: `KeySynth` taps, the same mechanism the touch
  policy and the D-pad use. Nothing writes guest memory, VRAM, palettes, saves
  or ROM, and no guest function is called.
* **Threads**: the accessibility UI (Android) queues commands into a small
  mutex-protected buffer; the emulation frame drains it, so no Java callback
  ever touches game state directly.

### Files

| File | Role |
| --- | --- |
| `src/accessibility/emerald_a11y.h` | Interface: frame hook, actions, speech sink |
| `src/accessibility/emerald_a11y.cpp` | State watching, text capture, speech content, navigation |
| `src/accessibility/emerald_a11y_android.cpp` | JNI bridge to `TextToSpeech`, the activity and the cue player |
| `src/accessibility/emerald_nav.cpp` | Exits, stairs, what the player faces, nearby people/items/objects, map transitions |
| `docs/PLAYTEST.md` | What has been checked against the ROM, and where automated play stops |
| `src/accessibility/emerald_cues.cpp` | Event → cue mapping, cooldowns, priorities |
| `docs/a11y-sfx.md` | Cue assets: sources, licenses, hashes, fallbacks |
| `android/app/src/main/java/com/mstan/emeraldrecomp/accessibility/A11yCues.java` | `SoundPool` playback and synthesized fallbacks |
| `src/mods/emerald_accessibility_plugin.cpp` | Mod activation and options |
| `android/app/src/main/java/com/mstan/emeraldrecomp/accessibility/EmeraldAccessibility.java` | TTS, announcements, virtual node tree |
| `android/app/src/main/java/com/mstan/emeraldrecomp/accessibility/EmeraldSetupActivity.java` | Spoken launcher: setup screen narration, live regions, focus speech |
| `android/app/src/main/java/com/mstan/emeraldrecomp/accessibility/SetupVoice.java` | TTS/announcement helper for the setup screen |
| `android/app/build.gradle` | Derives the app manifest from the engine's, rewriting only the launcher activity |
| `mods/preloaded/packages/pokemon-emerald.accessibility.spoken-ui/` | The catalog entry |

The Java sources are added to the app module by `android/app/build.gradle`; the
engine's shell is untouched.

## Testing

Desktop builds speak to stderr (`[emerald:a11y] speak: …`), which makes the
content testable without a device. The TCP debug port (19892) exposes the layer:

```
{"cmd":"emerald_a11y_status"}                  scene, status, items, selection
{"cmd":"emerald_a11y_log"}                     the recent utterances, with frames
{"cmd":"emerald_a11y_action","action":"down"}  drive input: up/down/left/right/
                                               confirm/cancel/start/read_status/
                                               repeat/stop/select/next/prev
{"cmd":"emerald_a11y_speak","text":"test"}     inject an utterance
{"cmd":"emerald_a11y_nav"}                     map, position, facing, the tile being
                                               looked at, warps, nearest exit,
                                               adjacent person/item/object
{"cmd":"emerald_a11y_cues"}                    the cue table (name, asset, cooldown,
                                               priority, description)
{"cmd":"emerald_a11y_cue","name":"door"}      play one cue on demand
{"cmd":"emerald_a11y_target","x":9,"y":9}   announce "You have arrived." on that tile
{"cmd":"emerald_a11y_target","clear":1}      drop the target
```

Cues are logged as `[emerald:a11y] cue: <name> (<asset>)` and cue-plus-speech
lines read `cue: npc (npc) + speak: Person south. Press A to talk.`, so the whole
mapping can be checked headlessly.

A useful check is a scripted route (the existing touch scenarios) with the log
pulled afterwards: every scene the route enters should produce one screen
announcement, every menu open one item announcement, and every dialogue line
exactly one utterance. The Java layer needs a device: confirm that TalkBack off
speaks through `TextToSpeech`, that TalkBack on announces instead, and that
activating a choice node moves the in-game cursor.

## Limits

* The **desktop** pre-boot launcher (the engine's Dear ImGui recomp-ui screen)
  is not covered; it belongs to the engine, not the game. On Android the ROM and
  BIOS setup screen does speak (see above).
* Android's Storage Access Framework file picker is a system app and cannot be
  voiced by the game; use TalkBack for it, or a build with bundled files.
* Screens are announced by name; contents are read when the game prints them or
  when a menu/list is open. The naming screen's keyboard is read (above); other
  free-form screens without an sMenu/ListMenu, such as the PokéNav map cursor,
  have no item labels yet and speak only their printed text.
* The overworld is announced as "Overworld"; area names arrive through the
  game's own map-name banner, which is spoken as text.
* Link battles and records replay through the same battle windows; they are
  spoken like any battle.
* Touch exploration gestures compete with the game's own touch controls. The
  design assumption is TalkBack off for gameplay (game speaks, touch controls
  work) or TalkBack on with the virtual nodes and buttons (no direct touch).

## Verified against the game (headless session)

`artifacts/playtest/run_session_v2.py` drives the real binary and records what
reaches the speech sink; see `docs/PLAYTEST.md` for the beats. The run covers
the whole spoken path: boot, title, intro, name entry, the truck, Littleroot,
Route 101, the rescue, the starter battle, a wild encounter, the battle Bag, a
Poké Ball throw, a catch, the Pokédex registration and the nickname keyboard.
Fixes that session produced:

* text is captured at `AddTextPrinter` (`0x0800467C`) again: the generated
  corpus now carries the hook's entry check, so battle narration ("Wild
  ZIGZAGOON appeared!", "TORCHIC used SCRATCH!", "fainted", EXP), script
  message boxes and menu labels speak with the exact string the game prints;
* the `gStringVar4` poll is a fallback for a corpus without that check only, so
  a field box's text is no longer repeated after every battle message;
* one printer call can carry several lines; each printed line is its own label,
  so prompts say "YES."/"NO." and "BOY."/"GIRL." instead of "Option 1 of 2";
* a pad direction in the field holds long enough for the turn *and* the walk,
  so one press is one tile even when the step starts by turning;
* the opening truck's moving box is announced as a box, not a person;
* the title screen / main menu line is announced once, not twice;
* printed text is read in full (the game's message buffers are 1000 bytes), so
  the intro's longest page no longer stops mid-sentence;
* the naming screen's keyboard rows are not read as dialogue; its own reader
  speaks the key under the cursor, the typed name and OK.

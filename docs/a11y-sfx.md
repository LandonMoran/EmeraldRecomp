# Accessibility audio cues: assets and mapping

The spoken interface plays short sound cues for events that matter when you
cannot see the screen. The cues come from the accessibility layer only: they are
mixed outside the emulated console, so Emerald's own music, sound effects and
menus are untouched.

* Event detection lives in `src/accessibility/emerald_nav.cpp` (what is nearby:
  warps, stairs, people, items, map changes).
* The event → sound mapping and the anti-repetition rules live in
  `src/accessibility/emerald_cues.cpp` (`kCueTable`).
* Turning a sound name into audio lives in the app:
  `android/app/src/main/java/com/mstan/emeraldrecomp/accessibility/A11yCues.java`.
* The files themselves are in `android/app/src/main/assets/a11y/sfx/`.

Because detection, mapping and playback are three separate pieces, adding a cue
is a table row plus an asset — no change to the game, the menus or the
navigation code.

## Mapping

| Cue | Event | Asset | Spoken alongside (optional) |
| --- | --- | --- | --- |
| `door` | A door or exit warp is within two tiles, or the player faces one | `door.ogg` | "Door here. Press A to exit." / "Door two steps north. Press A to exit." |
| `stairs_up` | Stairs that lead up are near | `stairs_up.ogg` | "Stairs up … Walk onto them." |
| `stairs_down` | Stairs that lead down are near | `stairs_down.ogg` | "Stairs down … Walk onto them." |
| `map_transition` | The map changed (door, stairs, script warp) | `map.ogg` | "New area." plus the area's own speech |
| `npc` | A person is adjacent | `npc.ogg` | "Person west. Press A to talk." |
| `object` | An interactive object is adjacent | `object.ogg` | "Object east. Press A." |
| `sign` | A sign, the wall clock or the TV is in front of the player | `sign.ogg` | "Something to read here. Press A." |
| `trainer` | A trainer (not an ordinary person) is near | `trainer.ogg` | "Trainer west. Press A to talk." |
| `item` | A collectible item ball is adjacent | `item.ogg` | "Item south. Press A to pick it up." |
| `target` | A navigation target is reached | `target.ogg` | "You have arrived." |
| `ok` | A press produced a response (dialogue, menu, warp) | `ok.ogg` | (the game's own text) |
| `fail` | A press produced nothing | `fail.ogg` | — |

**Only events Emerald is silent about get a cue.** Menus and their cursor moves,
list scrolling, and the start of a battle all have the game's own effects and
music already, so nothing is layered on top of them — a second sound there would
only fight the one the player is already hearing. A sign, the wall clock, a TV or
a trainer standing in front of you makes no sound at all, which is exactly what
these cues are for.

Speech and cues are independent switches: with "Read game text" off you still
get the cues; with cue play disabled you still get the announcements.

## Anti-repetition

* Each cue has its own cooldown in `kCueTable` (in frames, 60 fps), so a door
  does not retrigger while you stand next to it.
* A global gap of 12 frames separates any two cues, and higher-priority cues
  (`door`, `map_transition`, `interact_ok`, `interact_fail`) win over ambience.
* A nearby person/item/object is announced again only when it changes (different
  tile or different kind). Nothing repeats on a timer, so standing still is
  silent.
* The cue layer never plays more than two streams at once (`SoundPool`
  `maxStreams = 2`), so cues cannot pile up.

## Assets

There are two kinds of file here, and neither has any restriction on use.

### Generated for this project (sign, trainer)

Two cues were synthesized for this layer rather than licensed: no third-party
sample is involved, they are original arithmetic waveforms, and they are
dedicated to the public domain under **CC0 1.0**. The generator is committed at
`tools/make_a11y_cues.py` (deterministic; needs `numpy` and `soundfile` only to
regenerate), so anyone can rebuild or retune them and check that the files match:

    python3 tools/make_a11y_cues.py

| File | Shape | SHA-1 | Bytes |
| --- | --- | --- | --- |
| `sign.ogg` | paper rustle under a soft two-note chime (C6, G6) | `d8a56352bb9a625b4d3d0b5f58488673b07d91d4` | 5182 |
| `trainer.ogg` | two firm descending blips (G5, C5) | `7a10a593ad802c0430e53bf30691e49729457003` | 4371 |

### Kenney Interface Sounds (the original ten)

All ten files come from one pack, **Kenney · Interface Sounds 1.0**
(<https://kenney.nl/assets/interface-sounds>), released under **CC0 1.0
Universal** (<https://creativecommons.org/publicdomain/zero/1.0/>). CC0 places
the work in the public domain: no attribution is required, and none of the
files carry a share-alike or notice requirement. The pack's own `License.txt`
is kept next to the assets as
`android/app/src/main/assets/a11y/sfx/LICENSE-kenney-interface-sounds.txt`.

Kenney asks (optionally) to be credited; this document and the app's about text
credit "Kenney (kenney.nl)" as a courtesy.

| File | Original in pack | SHA-1 | Bytes |
| --- | --- | --- | --- |
| `door.ogg` | `open_001.ogg` | `3a6618eb9346042410a3081404d4696593539b5e` | 9834 |
| `stairs_up.ogg` | `maximize_001.ogg` | `0b4b11b40ad04369fe6bb8fc4838c3e87f024a49` | 12111 |
| `stairs_down.ogg` | `minimize_001.ogg` | `fff6d3e123067ecd6980b44430c9af7a26cd073c` | 11924 |
| `map.ogg` | `switch_003.ogg` | `0a7fc8581201c09034c315d0898154b3e7e3e96f` | 9653 |
| `npc.ogg` | `question_001.ogg` | `fcf5f69154431e52fc6a2250c3f40a6678853d89` | 11700 |
| `object.ogg` | `click_002.ogg` | `7bc0eb2c71afe88c77d066b35a0bc75c5ef80fd4` | 4275 |
| `item.ogg` | `pluck_001.ogg` | `c658b24e88542f4cb04029cd3fef0bda8959ecc7` | 6317 |
| `target.ogg` | `tick_001.ogg` | `4a02fc8e21a4db678c3f082f4ea8c4904bcde72c` | 4497 |
| `ok.ogg` | `confirmation_001.ogg` | `778f174aeb2eb8c2e456bfdb9ab5b50bb766a911` | 8968 |
| `fail.ogg` | `error_001.ogg` | `82b764e3bcaf2c0ae3b4d17e469f662e94aa9818` | 7373 |

The originals are 44.1 kHz mono Ogg Vorbis, between half a second and a second
and a half long, and are copied unmodified — only the names change. The four
generated files are the same format, 0.26–0.30 s long. Whole directory: 128 KB.

## No asset? Synthesized fallback

`A11yCues` asks `SoundPool` for `a11y/sfx/<name>.ogg`. If the file is missing
(unpackaged build, trimmed APK) or the platform refuses the stream, it falls
back to a `ToneGenerator` tone chosen per event class, so a packaging mistake
degrades a cue instead of silencing it:

| Cue | Tone |
| --- | --- |
| `ok`, `target` | `TONE_PROP_ACK` |
| `fail` | `TONE_PROP_NACK` |
| `item` | `TONE_PROP_BEEP2` |
| `door`, `map` | `TONE_PROP_PROMPT` |
| `stairs_up` / `stairs_down` | `TONE_DTMF_9` / `TONE_DTMF_6` |
| `npc`, `object`, `sign` | `TONE_PROP_BEEP` |
| `trainer` | `TONE_PROP_ACK` |

Missing assets are logged once per name (`no asset for cue '…'`) and the tone
takes over from then on.

## Adding a cue

1. Add a row to `kCueTable` in `src/accessibility/emerald_cues.cpp`: name,
   asset name, cooldown in frames, priority, description.
2. Drop the audio in `android/app/src/main/assets/a11y/sfx/<asset>.ogg` — or add
   the cue to `tools/make_a11y_cues.py` and generate it, which keeps the
   provenance trivially clean.
3. Record its source, author, license, link and SHA-1 in the tables above.
4. Give it a fallback tone in `A11yCues.java` so a missing asset stays audible.
5. Call `play_cue(Cue::YourName)` from whichever detector sees the event.

Nothing else changes: the desktop/headless build logs
`[emerald:a11y] cue: <name> (<asset>)` for every cue, so the mapping is testable
without a device.

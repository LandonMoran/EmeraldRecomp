# EmeraldRecomp — Pokémon Emerald, Recompiled

<a href="https://recomplauncher.com/game/emeraldrecomp"><picture><source media="(prefers-color-scheme: dark)" srcset="https://recomplauncher.com/assets/press/launcher/badge-light.svg"><img alt="Get it on RecompLauncher" src="https://recomplauncher.com/assets/press/launcher/badge-dark.svg" height="48"></picture></a>

> _This recompilation is a **byproduct of developing
> [gbarecomp](https://github.com/mstan/gbarecomp)** — the games are the proving ground, the framework is the goal.
> **These are in-development previews, not finished ports — expect rough
> edges**, and depth will keep landing over months, not days. My time for any
> one title is limited, so I ask for your patience. Contributions are welcome —
> testing, issues, and PRs to the game or framework all help and will
> accelerate this game's polish. More on the why at:
> [Recomp + AI: 5 Months Later »](https://1379.tech/recomp-ai-5-months-later/)_

Static recompilation of **Pokémon Emerald** (Game Boy Advance) to native PC, built
on the [`gbarecomp`](https://github.com/mstan/gbarecomp) framework.

Its Gen3 siblings live in
[`FireRedLeafGreenRecomp`](https://github.com/mstan/FireRedLeafGreenRecomp) (FireRed + LeafGreen) and
[`RubySapphireRecomp`](https://github.com/mstan/RubySapphireRecomp) (Ruby + Sapphire).

> ### Status — playable bring-up, self-improving, and playable by ear
>
> This is a **static-recompilation base + runner**, not a finished port. Emerald
> **boots through the BIOS intro to the title screen and into gameplay**. It is
> **early** — not every code path is statically recompiled yet, and content has
> not been exhaustively tested. (Emerald's RTC and its larger battle/contest engine
> are the notable deltas from the other Gen3 games.)
>
> **It gets better the more you play.** Any code path the static recompiler hasn't
> covered runs through a built-in **interpreter the first time it's hit**, then is
> **JIT-compiled to native** (in-process, no toolchain needed) and **remembered on
> disk** — so the next launch runs it natively from the start. Interpreted once,
> native ever after; coverage grows toward fully-native as the game is played. See
> [How it self-improves](#how-it-self-improves).
>
> The build also carries a **spoken interface** for blind players and a
> playtest harness that drives it over TCP, and both are audited rather than
> asserted: every claim in [the playability audit](docs/PLAYABILITY_AUDIT.md)
> names the line the game spoke and the transcript it came from, and those
> transcripts live in [the playtest evidence directory](artifacts/playtest/README.md).
> As of this build all eight Hoenn gyms have been cleared by ear, travel names
> the road before you commit to it ("Route 116 east."), and catching a Pokémon
> is proven end to end, party and ball-count decrement included. What is still
> open is listed in the same audit.

---

## Screenshots

Captured stills of the native build (no emulator) are on the store page:
[EmeraldRecomp on RecompLauncher](https://recomplauncher.com/game/emeraldrecomp).
The two images this section used to embed were never committed to the repo, so
they are linked rather than embedded - a relative path that resolves beats a
picture that does not load.

---

## What "static recompilation" means here

The ROM's **ARM7TDMI machine code is statically translated to native C** — every
function the game runs becomes a real generated C function. Unlike most recomp
projects, **the GBA BIOS is recompiled and executed too** (not HLE'd or stubbed),
so the boot sequence and interrupt/SWI handlers run as real recompiled code. The
rest of the console — the PPU (graphics), APU + M4A sound engine, DMA, timers, the
cartridge flash save chip + RTC, and hardware I/O — is modeled by the `gbarecomp`
runtime.

Only **symbol metadata** (function names, addresses, sizes) from the
[`pret/pokeemerald`](https://github.com/pret/pokeemerald) decompilation enters this
repo — never its C source, build output, or toolchain. **The ROM is never
redistributed**; you supply your own legally-dumped copy.

## ROM

| Target          | Game            | ROM (USA) | SHA-1                                      | Debug port |
|-----------------|-----------------|-----------|-------------------------------------------|------------|
| `EmeraldRecomp` | Pokémon Emerald | USA       | `f3ae088181bf583e55daf962a92bb46f4f1d07b7` | 19892      |

The runtime **refuses to launch on an unrecognized ROM** — the SHA-1 must match.

## Quick start

1. Download the latest `EmeraldRecomp-windows-x64` zip from
   [Releases](https://github.com/mstan/EmeraldRecomp/releases) and extract it (or build from source — see below).
2. Run `EmeraldRecomp`.
3. Supply your own **legally-obtained** Pokémon Emerald (USA) ROM when prompted.
   The path is cached next to the exe for future launches.
4. Play. Early on you may briefly see the interpreter warm up new code paths; once
   warmed (and cached), they run native.

## Android saved games

Use **Saved game** on the launch screen to import or export a raw `.sav` file
with Android's file picker. Quit the game to return to that screen. If setup
is normally skipped, press and hold the app icon and choose **Saved game**
on launchers that support app shortcuts.

Import accepts a 128 KiB Emerald native save and keeps the previous save as
an exportable backup. Execution save states are separate. Save transfers stay
locked while the game is running, including while it is backgrounded.

**Mods → Gameplay Diagnostics → Record Gameplay** controls the bounded local
troubleshooting recorder. It starts enabled and remembers your choice
independently of adaptive widescreen.

## Multiplayer: Link Cable and Wireless Adapter

EmeraldRecomp supports **two-player Emerald ↔ Emerald netplay** with a virtual
**Link Cable** or **Wireless Adapter**. Each peer simulates both GBAs and the
local link hardware; `recomp-net` exchanges controller inputs using delay-sync
or rollback. LAN / Direct IP and Internet lobbies use the same simulation.

1. Use matching builds and the supported Emerald USA ROM on both machines.
2. Open **Netplay**, create or join a lobby, and use a separate trainer save
   for each player.
3. The host selects **Lobby Settings → Connection type**: **Link Cable**
   (default) or **Wireless Adapter**. All players inherit the host's choice.
4. Start the session, then use the corresponding upstairs Pokémon Center
   desk. Wireless Adapter enables the **Union Room**; the original game's
   progression and party requirements still apply.

Cable multiplayer has been play-tested. Wireless currently has validated Union
Room entry, mutual discovery and contact, deterministic replay, and input
netplay under simulated latency/jitter. Full wireless trades/battles and all
RFU recovery behavior have not yet been qualified. See the engine's
[wireless validation and limits](https://github.com/mstan/gbarecomp/blob/main/docs/WIRELESS.md).

**v0.1.1** binaries include experimental Wireless Adapter Union Room support;
**v0.1.0** contains cable support only. Merging source does not replace old
release downloads. FireRed/LeafGreen/Ruby/Sapphire cross-version linking,
larger lobbies and Single-Pak multiboot are future work.

## Controls

| GBA button | Keyboard      |
|------------|---------------|
| D-Pad      | Arrow keys    |
| A          | Z             |
| B          | X             |
| Start      | Enter         |
| Select     | Backspace     |

Save states: **Shift+F1–F9** save to a slot, **F1–F9** load it. On Android (a
phone has no function keys) the game's settings menu carries them: open it with
a **Back gesture on the overworld**, a pad's **L3/R3** click or the
**Start+Select** chord, and use **Assist Tools → State slot / Save state / Load
state**. The app also keeps one automatic suspend point: backgrounding the game
and being killed by Android resumes where you left off.

Without sight the menu is not needed: in the overworld, **tap the top-left
corner of the game image** and the game speaks a save-state sheet — tap saves
the slot, swipe up loads it, swipe left or right changes the slot, a two-finger
tap closes it — and each action ends with what actually happened ("Saved to
slot 3.", "Loaded slot 3.", "Nothing saved in slot 3."). The menu itself is
unchanged, and the sheet is a touch feature (TalkBack's touch exploration takes
the corner tap, so snapshots are for TalkBack-off play).

## Accessibility: spoken interface

EmeraldRecomp can be played by ear. **Mods → Accessibility → Spoken
Interface** (enabled on fresh profiles; on Android its three options are on the
launcher screen, before play) reads screens, menus and their items,
bag and shop lists, dialogue, battle messages, battle choices and the name-entry
keyboard aloud. On Android the game speaks through its own **text to speech**,
with or without TalkBack running.

There is deliberately **no accessibility tree over the running game**: with one,
TalkBack owns the pad, the keyboard and touches, and a controller can no longer
play. The game screen is hidden from accessibility services and the game speaks
for itself. The **setup screen before the game** keeps its normal Android tree,
so TalkBack reads and drives it as usual.

With a **controller** there is nothing extra to learn: moving the d-pad/stick
moves the game's own cursor, and every cursor change, menu, list, battle choice
and printed line is spoken as it happens. Three pad commands cover the rest —
**L** reads the current screen, **Select** repeats the last utterance, and
**Select, then L** stops speech (the two presses need not be simultaneous).
On an Xbox pad that is **LB**, **View**, and **View then LB**.

The spoken settings — read game text, detail, speech rate — are deliberately
**not** on the pad, so no combination pressed while playing can change how the
game talks. On Android they are on the launcher screen: quit the game to return
there. On desktop they are in the Mods menu.

On Android the first-launch **setup screen speaks too**: the game subclasses
the engine's ROM/BIOS import screen, so it is narrated and its status changes
are announced before the game exists, and TalkBack's live regions are kept
current for the same screen. See
[docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md) for what is spoken, the mod
options and the TCP test commands, and
[docs/PLAYABILITY_AUDIT.md](docs/PLAYABILITY_AUDIT.md) for how much of the game
has actually been played that way - the audit names the spoken line behind every
claim and is blunt about the parts that are still missing. All eight of Hoenn's
gyms have now been cleared by ear, each with the leader's badge read back out of
the save block (see the audit's gym table). Travel names the road before you
walk it, doors say what they lead to, and catching a Pokémon is proven from the
purchase through the party listing with the ball pocket decrement read out of
the save block. What is still open is listed in the same audit, including
Mossdeep's statue-rotation search, which is modelled and exercised but not yet
solved end to end. The runs behind every row are indexed in
[the playtest evidence directory](artifacts/playtest/README.md).

## How it self-improves

`gbarecomp`'s coverage is honest: a path that wasn't statically recompiled is
**bridged through the interpreter** the first time, *loudly*, then healed:

- **First hit:** the interpreter runs the missed function (correct, just not
  native) and the runtime records it.
- **Heal:** the function is **JIT-compiled to native in-process** via a
  toolchain-less backend (sljit) — no compiler required on your machine.
- **Persist:** the healed path is written to a per-ROM cache
  (`recomp_cache/<rom-sha1>/`), so **the next launch re-JITs it up front** and it
  runs native from the start.

The result is a game that converges toward fully-native execution the more it's
played, and **stays** improved across launches. A handful of instruction patterns
the JIT can't lower yet stay on the interpreter (precision over recall); those are
emitter gaps that close over time. Self-improvement is on by default; set
`GBARECOMP_SELFHEAL_RECOMPILE=0` for a pure-interpreter run.

## Building from source

The [overworld widescreen experiment](docs/WIDESCREEN_EXPERIMENT.md)
adds Fit to window, 16:9, 21:9 and 32:9 choices through the Mods catalog. This
version expands scenery and live NPC visibility. Starting with v0.0.6, Fit also
fills portrait windows, overworld menus anchor to the viewport edges, and door
animations retain expanded scenery. Distant object spawning and
field effects retain the game's original limits; unsupported scenes use the
original centered view. Fresh installations enable the bundled mod with Fit
to window; existing saved mod choices are preserved.

**Prerequisites (Windows):** [MSYS2](https://www.msys2.org/) with the mingw64
toolchain (`gcc`/`g++`), CMake 3.16+, Ninja, and SDL2 (mingw64 package). Builds
are invoked from PowerShell with the mingw64 toolchain on `PATH`.

**1. Clone this repo next to `gbarecomp`** (the game repo builds against the
sibling engine checkout on `main`):

```
git clone https://github.com/mstan/gbarecomp.git
git clone https://github.com/mstan/EmeraldRecomp.git
cd EmeraldRecomp
```

**2. Supply your ROM** at `variants/emerald/roms/emerald_usa.gba` (SHA-1 above).
ROMs are gitignored and never committed.

**3. Recompile + build.** The committed `variants/emerald/symbols/*.toml` are the
importer output, so you can regenerate the C and build directly:

```
# from PowerShell, mingw64 on PATH
gba_recompile --rom variants/emerald/roms/emerald_usa.gba \
              --config variants/emerald/symbols/emerald_usa.toml \
              --out variants/emerald/generated
cmake -S . -B build -G Ninja
cmake --build build --target EmeraldRecomp
```

(`gba_recompile` is built from the `gbarecomp` checkout; see that repo's README.)
The recompiled translation unit is large — expect a multi-minute compile.

The BIOS recompilation output is build-local too, so the `gbarecomp` checkout is
never left with modified files:

```
./build/gbarecomp_build/gba_recompile --bios gbarecomp/bios/gba_bios.bin \
    --config gbarecomp/bios/gba_bios.toml --out build/generated_bios
cmake -S . -B build -DGBARECOMP_GENERATED_BIOS_DIR=$PWD/build/generated_bios
```

## License

For this project's code covered by the [PolyForm Noncommercial License](LICENSE),
[PERMISSIONS.md](PERMISSIONS.md) grants standing permission for voluntary
donations, sponsorships, and advertising revenue, including support for broader
development initiatives. Payment must not buy access to the software, games
built with it, or their updates, features, or game content, including early access.

Matthew Stanley has authority from the relevant copyright holders to grant
these permissions for the project's PolyForm-covered code. Third-party
components and code explicitly licensed under other terms retain those terms.

PolyForm Noncommercial 1.0.0 — see [`LICENSE`](LICENSE). Third-party
components retain their own licenses.

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md) | The spoken interface: what is spoken, the pad commands, settings, name entry, save states without sight |
| [docs/PLAYABILITY_AUDIT.md](docs/PLAYABILITY_AUDIT.md) | What has actually been proven playable by ear, row by row, with the spoken lines quoted and the transcripts named - and what is still missing before release |
| [docs/PUZZLE_PLAYTEST.md](docs/PUZZLE_PLAYTEST.md) | The gym and environment puzzle test log behind the audit: each room, what the mod said, what it turned on |
| [docs/PLAYTEST.md](docs/PLAYTEST.md) | The test harness: how runs are driven over TCP, what is automated, what still needs a device |
| [docs/a11y-sfx.md](docs/a11y-sfx.md) | The audio cue design alongside the speech |
| [docs/NETPLAY.md](docs/NETPLAY.md) | Wireless/netplay validation and its limits |
| [docs/ANDROID_APK_CI.md](docs/ANDROID_APK_CI.md) | The Android build and its CI |
| [docs/WIDESCREEN_EXPERIMENT.md](docs/WIDESCREEN_EXPERIMENT.md) | The optional widescreen mod |
| [artifacts/playtest/README.md](artifacts/playtest/README.md) | The playtest evidence directory: every committed transcript, what it proves, and the drivers that produced it |
| [artifacts/puzzles/INVENTORY.md](artifacts/puzzles/INVENTORY.md) | The puzzle inventory generated from the decompilation: which maps carry triggers and map-script hooks |
| [CONTRIBUTING.md](CONTRIBUTING.md) | What a contribution has to be licensed under |
| [PERMISSIONS.md](PERMISSIONS.md) | The standing additional permissions on the PolyForm-covered code |
| [CLAUDE.md](CLAUDE.md) | The execution contract this repo builds and verifies under |
| [tools/linux/README.md](tools/linux/README.md) | The Linux AppImage package readme |
| [tools/android-licenses/README.md](tools/android-licenses/README.md) | The NDK notice staged into the Android package |
| [variants/emerald/generated/README.md](variants/emerald/generated/README.md) | Why the recompiler's C output is generated locally and never committed |
| [the bundled widescreen package](mods/preloaded/packages/pokemon-emerald.enhancement.widescreen/0.2.0/README.md) | What the preloaded mod package requires and changes |

## Repository map

| Path | What is there |
| --- | --- |
| `src/` | The game-specific mod: accessibility speech, navigation, puzzles, cues, touch input, dev tools |
| `variants/emerald/` | ROM config, the imported symbol metadata, and the generated recompilation output (local only) |
| `mods/preloaded/` | The mod packages shipped inside the build |
| `tools/` | Release packaging, Android licensing notices, the decompilation symbol importer |
| [`docs/`](docs/) | Everything long-form: the accessibility reference, the playtest harness, the puzzle log, the audit, netplay, Android CI, widescreen |
| [`artifacts/playtest/`](artifacts/playtest/README.md) | The harness and the committed transcripts every audit claim points at |
| [`artifacts/puzzles/`](artifacts/puzzles/INVENTORY.md) | The generated puzzle inventory and the plans derived from it |

The engine is not in this repo: the build links against a sibling
[`gbarecomp`](https://github.com/mstan/gbarecomp) checkout, which owns the
recompiler, the GBA hardware models and its own documentation.

## Legal

This project contains **no copyrighted ROM data, no Nintendo BIOS, and no decomp
source** — only original recompiler/runtime code and symbol metadata. **You must
supply your own legally-dumped ROM** (and BIOS, where the runtime requires one).
Pokémon and Emerald are trademarks of Nintendo / Game Freak / The Pokémon Company;
this project is an unaffiliated, non-commercial preservation and research effort.

---

<p align="center">
  <sub><b>R.A.I.D. — Retro AI Development</b> · a Discord for AI-assisted retro reverse-engineering, decomp &amp; recomp</sub>
</p>

<p align="center">
  <a href="https://discord.gg/Ad9BwSzctP"><img src=".github/raid-discord.png" alt="Join the Retro AI Development (R.A.I.D.) Discord" width="200"></a>
</p>

## RecompLauncher

The release manifest starts the Windows executable or Linux AppImage with your
Pokémon Emerald USA ROM through `--rom`. Choose your own GBA BIOS in the game
setup on first launch.

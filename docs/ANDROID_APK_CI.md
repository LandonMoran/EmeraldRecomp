# Building the Android APK on GitHub Actions

The APK can be built on a runner, but not from the repository alone: EmeraldRecomp
is **statically recompiled**, so the game's code is translated from a cartridge
dump at build time and compiled into `libmain.so`.

```
gba_recompile --rom variants/emerald/roms/emerald_usa.gba … --out variants/emerald/generated
cmake --build … --target EmeraldRecomp        # or gradlew :app:assembleDebug
```

`variants/*/generated/` and `variants/*/roms/` are gitignored, so a fresh clone
(and therefore a runner) has no game code to link — the link fails with
`undefined … gf_ReadFlash_Core` and friends. The workflow solves that by fetching
the owner's own dump from a private place, checking its SHA-1, recompiling, and
caching the derived corpus.

What the player does at run time is unchanged: install the APK, import ROM + BIOS,
play. The APK contains translated code derived from the owner's dump; it never
contains the ROM itself, and the workflow refuses to upload an APK that does.

## What to add (one secret, one variable)

### 1. Put the ROM where the build can reach it

Pick one. There is no browser step: a runner has no signed-in browser, and
Google's copy-confirm pages need JavaScript and cookies, so the build asks the
plain download endpoint for bytes and fails loudly when it gets HTML back.

**Private repository (simplest)**

1. Create a private repo, e.g. `your-name/emerald-rom`.
2. Upload the dump as `emerald_usa.gba` (16,777,216 bytes,
   SHA-1 `f3ae088181bf583e55daf962a92bb46f4f1d07b7`).

**Release asset in a private repo**

1. Create a release in that private repo and attach the dump.
2. Note the asset's numeric id (`https://api.github.com/repos/OWNER/REPO/releases`
   lists them, or it is the last number in the asset's browser URL).

Do **not** put it in this public repository, even encrypted: an encrypted copy of
a commercial ROM is still a copy of it.

**Google Drive (shared by link, no token)**

1. Right-click the file in Drive → **Share** → **Anyone with the link** →
   Viewer.
2. Use `drive:<file-id>`, e.g.
   `drive:1Kev3HlrxtkN2GMUGukirCtMN1BLnrjMx` (the id is in the share URL:
   `https://drive.google.com/file/d/<id>/view`).

No secret is needed for this form. Trade-offs: **anyone with the link can
download the ROM**, Drive occasionally serves "can't scan this file" or
"too many downloads" pages to anonymous requests, and a link can be revoked at
will — so it is convenient, not permanent. The script detects an HTML answer and
fails with that explanation (exit 5) instead of hashing a web page. A private
repo or release asset with `EMERALD_ROM_TOKEN` is the more reliable choice, and
any other permanent host works too via `url:` (an R2/S3 object with a long random
path, for instance).

#### Keeping the link itself secret

Storing the whole spec as the **secret** `EMERALD_ROM_SOURCE` (e.g.
`drive:1Kev3…`) does work: the workflow reads it into an environment variable,
masks it (`::add-mask::`), and the fetch script never prints the spec — only its
form (`drive:...`) — so the id does not appear in the log.

Be clear about what that buys. The Drive file is still served to **anonymous**
requests once it is link-shared; the secret hides *where* it is, not *what it is*.
Anyone who ever sees the value — a collaborator editing a workflow, a pasted log,
a shared screen, a fork with a modified file that prints it — can download the ROM
for good, and there is no way to revoke that other than unsharing and rotating
the link. A token, by contrast, is scoped to one repo and revocable in seconds,
and the file is never downloadable without it. If the goal is "not publicly
downloadable", use `repo:`/`asset:` with `EMERALD_ROM_TOKEN`; if the goal is
"not casually discoverable", the secret-held Drive link is fine.

### 2. Create a read-only token

GitHub → Settings → Developer settings → **Fine-grained personal access tokens**
→ Generate new token:

- Repository access: **Only select repositories** → the private repo above.
- Permissions → Repository permissions → **Contents: Read-only**. Nothing else.

### 3. Add the secret and the variable

Repository → **Settings → Secrets and variables → Actions**:

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `EMERALD_ROM_TOKEN` | the fine-grained token from step 2 |
| Variable **or** Secret | `EMERALD_ROM_SOURCE` | one of the forms below |
| Secret (Drive/public URL only) | *none needed* | leave `EMERALD_ROM_TOKEN` unset |

`EMERALD_ROM_SOURCE` may be stored either way; if both exist the secret wins.
Use the secret if you want the location itself (a Drive id, a private URL) kept
out of the settings page people can read.

`EMERALD_ROM_SOURCE` forms (the variable is not secret — it is just a location):

```
repo:your-name/emerald-rom:emerald_usa.gba        # file from a private repo (token)
asset:your-name/emerald-rom:123456789             # release asset by numeric id (token)
drive:1Kev3HlrxtkN2GMUGukirCtMN1BLnrjMx          # Google Drive, shared by link
url:https://example.com/path/emerald_usa.gba      # any direct URL
file:/path/on/a/self-hosted/runner/emerald.gba    # self-hosted runners
```

The download may be the raw 16 MiB dump **or a zip of it** — the Drive copy is
`Pokemon - Emerald Version (USA, Europe).zip`, 6,976,143 bytes. A zip is
unpacked, its single `.gba` is taken, and the SHA-1 is checked against the
extracted file. That also means a 7 MB zip can be uploaded to the private repo
instead of the 16 MiB dump.

Optionally override the expected dump with a variable `EMERALD_ROM_SHA1`; the
default is the USA dump this repository's symbols are built for
(`f3ae088181bf583e55daf962a92bb46f4f1d07b7`).

### 4. Run it

Actions → **Android APK** → *Run workflow*.

The APK appears as the `emeraldrecomp-debug-apk` artifact on the run. Debug
builds are large (~150 MB) because they keep full symbols.

## What the workflow does

1. Checks out the game and its engine submodules (recursive).
2. Installs SDK 35, build-tools 35, NDK 27.1.12297006, CMake 3.22.1.
3. Restores the cache: `variants/emerald/roms/emerald_usa.gba` +
   `variants/emerald/generated`, keyed on
   `emerald-corpus-<rom-sha1>-<hash of game.toml + symbols/*>`.
   A `game.toml` hook change or a new ROM changes the key, so the corpus is
   rebuilt instead of silently reused.
4. On a cache miss, `tools/android/fetch_rom.sh` downloads the ROM with the
   token, checks the SHA-1, and fails loudly on a mismatch.
5. On a cache miss, configures the project (`-DGBAGAME_RECOMP_UI=OFF` so the
   runner needs no desktop GL), builds `gba_recompile`, and regenerates
   `variants/emerald/generated`.
6. Refuses to continue if the corpus produced fewer than two shards.
7. Builds `:app:assembleDebug`, and on failure re-prints the tail of the Gradle
   log as error annotations (CI logs otherwise need a sign-in to read).
8. Fails if the APK contains anything matching `*.gba`, `*.sav` or `*.gbs`, then
   uploads the APK and (optionally) the Gradle log.

## Testing the fetch script without any secret

```sh
# success path, hash checked against the real dump
EMERALD_ROM_SOURCE=file:/path/to/emerald_usa.gba \
  bash tools/android/fetch_rom.sh /tmp/rom.gba

# wrong dump is rejected and leaves no partial file behind
EMERALD_ROM_SOURCE=file:/path/to/another.gba \
  bash tools/android/fetch_rom.sh /tmp/rom2.gba   # exits 4
```

## Cost and cache notes

- The cache stores the ROM and the derived corpus (both repo-scoped and
  encrypted at rest by GitHub). If you would rather not keep the ROM in the
  Actions cache, run the workflow with `use_cache: false` — the recompile then
  costs a few extra minutes per run (build `gba_recompile` ≈1 min, recompile
  ≈1 min on a runner, then the native build).
- Each cached run still compiles 67 generated shards for arm64; expect roughly
  10–20 minutes on a standard runner.
- A release build is not produced here yet: it needs a signing keystore
  (a secret), which is a separate change.

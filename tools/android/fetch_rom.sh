#!/usr/bin/env bash
# fetch_rom.sh — put the player's own cartridge dump where the build expects it.
#
# The ROM is never committed (variants/*/roms/ is gitignored) and is needed only
# by whoever builds: static recompilation turns the ROM's code into the app, so
# the build machine needs one copy. This script fetches that copy from a place
# the repository owner controls.
#
#   usage: fetch_rom.sh <output-path> [expected-sha1]
#
#   EMERALD_ROM_SOURCE (required), one of:
#       repo:<owner>/<repo>:<path>        file from a repository (private ok)
#       asset:<owner>/<repo>:<asset-id>   release asset by numeric id
#       drive:<file-id>                   Google Drive file shared by link
#       url:<https-url>                   any direct URL
#       file:<path>                       a local file (tests, self-hosted runner)
#
#   EMERALD_ROM_TOKEN (optional): a token with read access to that source.
#       Used for repo:/asset: always, and for url:/drive: when set (Drive API
#       download). Never echoed, never written anywhere.
#
# The download may be the raw .gba or a zip of it (the Drive copy is a 7 MB
# zip); a zip is unpacked and its single .gba hashed. The SHA-1 gate is the
# point of the script: this repository's recompiled code only matches one dump.
#
# Exits non-zero on download failure, HTML-instead-of-file (a Drive link that is
# not shared publicly), or SHA-1 mismatch, and leaves no partial file behind.
set -euo pipefail

out="${1:?usage: fetch_rom.sh <output-path> [expected-sha1]}"
expected="${2:-${EMERALD_ROM_SHA1:-f3ae088181bf583e55daf962a92bb46f4f1d07b7}}"
source_spec="${EMERALD_ROM_SOURCE:-}"
token="${EMERALD_ROM_TOKEN:-}"

if [ -z "$source_spec" ]; then
    echo "fetch_rom.sh: EMERALD_ROM_SOURCE is not set (see docs/ANDROID_APK_CI.md)" >&2
    exit 2
fi

mkdir -p "$(dirname "$out")"
raw="${out}.download"
tmp="${out}.partial"
trap 'rm -f "$raw" "$tmp" "$out.rom.zip"' EXIT

fetch() {
    local url="$1" accept="${2:-}"
    local -a args=(-fsSL --retry 3 --retry-delay 2 -o "$raw" "$url")
    if [ -n "$accept" ]; then args+=(-H "Accept: $accept"); fi
    if [ -n "$token" ]; then args+=(-H "Authorization: Bearer $token"); fi
    curl "${args[@]}"
}

case "$source_spec" in
    repo:*)
        rest="${source_spec#repo:}"
        repo="${rest%%:*}"
        path="${rest#*:}"
        if [ "$repo" = "$rest" ] || [ -z "$path" ]; then
            echo "fetch_rom.sh: expected repo:<owner>/<repo>:<path>, got '$source_spec'" >&2
            exit 2
        fi
        fetch "https://api.github.com/repos/${repo}/contents/${path}" \
              "application/vnd.github.raw"
        ;;
    asset:*)
        rest="${source_spec#asset:}"
        repo="${rest%%:*}"
        id="${rest#*:}"
        case "$id" in
            ''|*[!0-9]*)
                echo "fetch_rom.sh: expected asset:<owner>/<repo>:<numeric-id>, got '$source_spec'" >&2
                exit 2
                ;;
        esac
        fetch "https://api.github.com/repos/${repo}/releases/assets/${id}" \
              "application/octet-stream"
        ;;
    drive:*)
        # The plain "uc?export=download" endpoint. Works for a file shared as
        # "Anyone with the link"; a private file answers with a sign-in page,
        # which is detected below rather than silently hashing HTML.
        id="${source_spec#drive:}"
        if [ -z "$id" ]; then
            echo "fetch_rom.sh: expected drive:<file-id>, got '$source_spec'" >&2
            exit 2
        fi
        fetch "https://drive.google.com/uc?export=download&id=${id}"
        ;;
    url:*)
        fetch "${source_spec#url:}"
        ;;
    file:*)
        cp "${source_spec#file:}" "$raw"
        ;;
    *)
        echo "fetch_rom.sh: unknown EMERALD_ROM_SOURCE '$source_spec' (repo:, asset:, drive:, url:, file:)" >&2
        exit 2
        ;;
esac

if [ ! -s "$raw" ]; then
    echo "fetch_rom.sh: the download was empty" >&2
    exit 3
fi

# A sign-in page, an error page or a quota notice is not a ROM.
if head -c 512 "$raw" | grep -qiE '<!doctype html|<html|<head'; then
    echo "fetch_rom.sh: got an HTML page instead of the file." >&2
    case "$source_spec" in
        drive:*)
            echo "  The Drive file is not shared publicly. Either set" >&2
            echo "  'Anyone with the link' on it, or keep it private and use" >&2
            echo "  repo:/asset: with EMERALD_ROM_TOKEN." >&2
            ;;
        *)
            echo "  Check the URL: it may need a token, or it may be a preview page." >&2
            ;;
    esac
    exit 5
fi

# Accept the raw dump or a zip of it (the Drive copy is a zip).
src="$raw"
if head -c 4 "$raw" | grep -q 'PK'; then
    if ! command -v unzip > /dev/null; then
        echo "fetch_rom.sh: the download is a zip but unzip is missing" >&2
        exit 6
    fi
    entries="$(unzip -Z1 "$raw" | grep -i '\.gba$' || true)"
    count="$(printf '%s\n' "$entries" | grep -c . || true)"
    if [ "$count" != "1" ]; then
        echo "fetch_rom.sh: expected exactly one .gba inside the zip, found $count" >&2
        exit 6
    fi
    unzip -p "$raw" "$entries" > "$out.rom.zip"
    src="$out.rom.zip"
    echo "fetch_rom.sh: unpacked $(printf '%s' "$entries") from the zip"
fi

cp "$src" "$tmp"

actual="$(sha1sum "$tmp" | cut -d' ' -f1)"
if [ "$actual" != "$expected" ]; then
    echo "fetch_rom.sh: SHA-1 mismatch" >&2
    echo "  expected $expected" >&2
    echo "  actual   $actual" >&2
    echo "  This build's recompiled code is tied to one dump; check the source." >&2
    exit 4
fi

mv "$tmp" "$out"
echo "fetch_rom.sh: $out ($(wc -c < "$out") bytes, sha1 $actual)"

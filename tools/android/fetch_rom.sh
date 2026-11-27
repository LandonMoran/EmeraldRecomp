#!/usr/bin/env bash
# fetch_rom.sh — put the player's own cartridge dump where the build expects it.
#
# The ROM is never committed (variants/*/roms/ is gitignored) and never needed
# at run time by anyone but the person building: static recompilation turns the
# ROM's code into the app, so the build machine needs one copy. This script
# fetches that copy from a place only the repository owner can read.
#
#   usage: fetch_rom.sh <output-path> [expected-sha1]
#
#   EMERALD_ROM_SOURCE (required), one of:
#       repo:<owner>/<repo>:<path>        raw file from a repository (private ok)
#       asset:<owner>/<repo>:<asset-id>   release asset by numeric id
#       url:<https-url>                   any direct URL (token sent if set)
#       file:<path>                       a local file (tests, self-hosted runner)
#
#   EMERALD_ROM_TOKEN (optional): a token with read access to that source.
#       Sent only to github.com / api.github.com or to the url: host, never
#       echoed, and never written anywhere.
#
# Exits non-zero on download failure or SHA-1 mismatch, and leaves no partial
# file behind.
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
tmp="${out}.partial"
trap 'rm -f "$tmp"' EXIT

fetch() {
    local url="$1" accept="${2:-}"
    local -a args=(-fsSL --retry 3 --retry-delay 2 -o "$tmp" "$url")
    if [ -n "$accept" ]; then args+=(-H "Accept: $accept"); fi
    if [ -n "$token" ]; then args+=(-H "Authorization: Bearer $token"); fi
    curl "${args[@]}"
}

case "$source_spec" in
    repo:*)
        # repo:owner/name:path/to/file
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
        # asset:owner/name:asset-id
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
    url:*)
        fetch "${source_spec#url:}"
        ;;
    file:*)
        cp "${source_spec#file:}" "$tmp"
        ;;
    *)
        echo "fetch_rom.sh: unknown EMERALD_ROM_SOURCE '$source_spec' (repo:, asset:, url:, file:)" >&2
        exit 2
        ;;
esac

if [ ! -s "$tmp" ]; then
    echo "fetch_rom.sh: the download was empty" >&2
    exit 3
fi

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

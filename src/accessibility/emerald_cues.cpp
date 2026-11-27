// emerald_cues.cpp — audio-cue table and rate limiting. See emerald_cues.h.
//
// Asset provenance (sources, authors, licenses, hashes) is documented in
// docs/a11y-sfx.md; the packaged files live in
// android/app/src/main/assets/a11y/sfx/. A cue whose asset is missing still
// works: the Android player synthesizes a short fallback tone, and desktop
// builds log the cue.

#include "emerald_cues.h"

#include <cstddef>
#include <cstdio>
#include <cstring>
#include <string>

#include "emerald_a11y.h"   // Action, speak_now

namespace emerald::accessibility {
namespace {

// ── The mapping: event → asset + rate limits ─────────────────────────────
// Extend by adding a row (and an enumerator). `asset` is a base name; the
// packaged file is <asset>.ogg. Cooldowns are in frames at 60 Hz.
struct CueSpec {
    const char* name;
    const char* asset;
    int cooldown;
    int priority;
    const char* description;
};

constexpr CueSpec kCueTable[] = {
    // name              asset            cool  pri  description
    {"door",             "door",          180,  3,  "a door or exit warp is adjacent"},
    {"stairs_up",        "stairs_up",     120,  3,  "stairs leading up are adjacent"},
    {"stairs_down",      "stairs_down",   120,  3,  "stairs leading down are adjacent"},
    {"map_transition",   "map",            90,  4,  "the map changed (new area)"},
    {"npc",              "npc",           240,  2,  "a person is adjacent"},
    {"object",           "object",        240,  2,  "an interactive object is adjacent"},
    {"item",             "item",          180,  3,  "a collectible is adjacent"},
    {"target",           "target",        120,  2,  "a navigation target was reached"},
    {"interact_ok",      "ok",             40,  1,  "an interaction produced game text"},
    {"interact_fail",    "fail",          120,  2,  "an interaction produced nothing"},
    {"sign",             "sign",          240,  2,  "a sign, clock or TV: something to read"},
    {"trainer",          "trainer",       240,  3,  "a trainer, not just a person"},
    {"battle",           "battle",        600,  5,  "a battle started"},
    {"menu",             "menu",           60,  1,  "a menu or list opened"},
};

static_assert(static_cast<int>(Cue::Count) ==
                  static_cast<int>(sizeof(kCueTable) / sizeof(kCueTable[0])),
              "kCueTable must have one row per Cue enumerator");

constexpr int kGlobalGapFrames = 12;      // no two cues closer than this
constexpr int kInteractDeadline = 45;     // frames to wait for text after A
constexpr int kMaxSaid = 160;

CueFn g_sink = nullptr;
bool g_spoken = true;

bool g_has_cued = false;
int g_last_cue_frame = -100000;
// Every slot starts far in the past, so the first cue of a session is never
// suppressed by its own cooldown (a zero-filled array would mute each cue until
// its cooldown had elapsed).
struct LastFrameOf {
    int v[static_cast<int>(Cue::Count)];
    LastFrameOf() {
        for (int i = 0; i < static_cast<int>(Cue::Count); ++i) v[i] = -100000;
    }
    int& operator[](int i) { return v[i]; }
    const int& operator[](int i) const { return v[i]; }
};
LastFrameOf g_last_frame_of;
int g_priority_of_last = -1;

bool g_expect_open = false;
int g_expect_deadline = 0;
int g_frame = 0;

const CueSpec& spec_of(Cue cue) {
    const int i = static_cast<int>(cue);
    if (i < 0 || i >= static_cast<int>(Cue::Count)) return kCueTable[0];
    return kCueTable[i];
}

}  // namespace

const char* cue_name(Cue cue) { return spec_of(cue).name; }
const char* cue_asset(Cue cue) { return spec_of(cue).asset; }
int cue_cooldown_frames(Cue cue) { return spec_of(cue).cooldown; }
int cue_priority(Cue cue) { return spec_of(cue).priority; }

int cue_table_size() { return static_cast<int>(sizeof(kCueTable) / sizeof(kCueTable[0])); }

const char* cue_table_row(int index) {
    if (index < 0 || index >= cue_table_size()) return nullptr;
    static std::string row;
    const CueSpec& s = kCueTable[index];
    row = std::string(s.name) + "|" + s.asset + "|" + std::to_string(s.cooldown) +
          "|" + std::to_string(s.priority) + "|" + s.description;
    return row.c_str();
}

void install_cue_sink(CueFn fn) { g_sink = fn; }

bool spoken_alongside() { return g_spoken; }
void set_spoken_alongside(bool on) { g_spoken = on; }

void play_cue(Cue cue, const char* say) {
    const int i = static_cast<int>(cue);
    if (i < 0 || i >= static_cast<int>(Cue::Count)) return;
    const CueSpec& spec = kCueTable[i];

    // Per-cue cooldown: the same event must not retrigger while the player is
    // still standing on it.
    if (g_frame - g_last_frame_of.v[i] < spec.cooldown) return;

    // Global gap: unless this cue outranks whatever just sounded, drop it
    // rather than queue (a queued cue would be stale by the time it plays).
    if (g_has_cued && g_frame - g_last_cue_frame < kGlobalGapFrames &&
        spec.priority <= g_priority_of_last) {
        return;
    }

    g_last_frame_of.v[i] = g_frame;
    g_last_cue_frame = g_frame;
    g_has_cued = true;
    g_priority_of_last = spec.priority;

    const char* spoken = nullptr;
    if (g_spoken && say && say[0]) spoken = say;

    if (g_sink) {
        g_sink(spec.asset, spoken, 0);
    } else {
        std::fprintf(stderr, "[emerald:a11y] cue: %s (%s)%s%s\n", spec.name, spec.asset,
                     spoken ? " + speak: " : "", spoken ? spoken : "");
    }
    if (spoken) speak_now(spoken, false);
}

void note_action(int action) {
    // Only A is an interaction. B (cancel) frequently does nothing on purpose,
    // and reporting that as a failed interaction would just add noise.
    const Action a = static_cast<Action>(action);
    if (a != Action::Confirm) return;
    g_expect_open = true;
    g_expect_deadline = g_frame + kInteractDeadline;
}

void note_game_text() {
    if (!g_expect_open) return;
    g_expect_open = false;
    play_cue(Cue::InteractOk, nullptr);
}

void cues_frame() {
    ++g_frame;
    if (g_expect_open && g_frame > g_expect_deadline) {
        g_expect_open = false;
        play_cue(Cue::InteractFail, nullptr);
    }
}

void cues_reset() {
    g_has_cued = false;
    g_last_cue_frame = -100000;
    g_priority_of_last = -1;
    for (int i = 0; i < static_cast<int>(Cue::Count); ++i) g_last_frame_of[i] = -100000;
    g_expect_open = false;
    g_expect_deadline = 0;
    g_frame = 0;
}

}  // namespace emerald::accessibility

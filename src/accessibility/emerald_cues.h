// emerald_cues.h — audio cues for the Pokémon Emerald accessibility layer.
//
// Sounds are played OUTSIDE the game through the accessibility layer (Android:
// SoundPool via the JNI bridge; desktop: logged so headless runs surface them).
// Emerald's own audio, menus and save data are never touched.
//
// The mapping from event to asset lives in one table (emerald_cues.cpp,
// kCueTable) so it can be extended without touching detection or navigation
// code: add an enumerator, add a table row, drop the asset next to the others,
// and the player picks it up by name.
//
// Every cue is rate-limited twice: a per-cue cooldown, and a global minimum
// gap so two events in the same moment cannot overlap. A higher-priority cue
// may interrupt the gap; everything else waits and is dropped rather than
// queued, so the ears never lag behind the game.

#pragma once

#include <cstdint>

namespace emerald::accessibility {

// Event classes the layer can announce with a sound. Keep the numeric values
// stable: the Android player maps assets by name, but tests and logs use these.
enum class Cue : int {
    Door = 0,           // a door / exit warp is adjacent
    StairsUp,           // stairs that change floor upward
    StairsDown,         // stairs that change floor downward
    MapTransition,      // the map changed (new area)
    Npc,                // a person is adjacent
    Object,             // an interactive object / sign / machine is adjacent
    Item,               // a collectible (item ball) is adjacent
    Target,             // a navigation target was reached
    InteractOk,         // an interaction produced game text
    InteractFail,       // an interaction produced nothing
    Sign,               // a sign, the wall clock, the TV: something to read
    Trainer,            // a trainer, not just a person
    Battle,             // a battle started
    Menu,               // a menu or list opened
    Count
};

const char* cue_name(Cue cue);

// Asset base name inside the packaged sfx directory (no extension). The Java
// player resolves "<asset>.ogg"; when it is absent it synthesizes a fallback
// tone, so a missing asset degrades instead of failing.
const char* cue_asset(Cue cue);

// Frames (60 Hz) before the same cue may sound again, and its relative
// priority when two cues land in the same frame.
int cue_cooldown_frames(Cue cue);
int cue_priority(Cue cue);

// Platform sink. `asset` is a cue_asset() name, `say` an optional string to
// speak alongside the sound (null when the caller already spoke). When no sink
// is installed, cues are logged as "[emerald:a11y] cue: <name> (<asset>)".
using CueFn = void (*)(const char* asset, const char* say, int interrupt);
void install_cue_sink(CueFn fn);

// Play a cue. `say` is spoken alongside the sound when the spoken-announcement
// option is on (default on); pass null to keep it silent.
void play_cue(Cue cue, const char* say = nullptr);

// Interaction outcomes. `note_action` records that the player asked for an
// interaction; the next printed game text confirms it (InteractOk) or the
// deadline expiring means nothing happened (InteractFail).
void note_action(int action);   // emerald::accessibility::Action as int
void note_game_text();
void cues_frame();              // ages the pending expectation; call once per frame
void cues_reset();

// Optional spoken announcements alongside the sounds (the sounds still play).
bool spoken_alongside();
void set_spoken_alongside(bool on);

// Introspection for docs and tests: rows of "name|asset|cooldown|priority".
int cue_table_size();
const char* cue_table_row(int index);

}  // namespace emerald::accessibility

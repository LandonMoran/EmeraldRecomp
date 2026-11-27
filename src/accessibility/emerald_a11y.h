// emerald_a11y.h — spoken UI and TalkBack layer for Pokémon Emerald.
//
// The accessibility layer is a screen reader for the game: it watches the same
// read-only guest state the touch policy classifies (callbacks, menus, lists,
// battle controllers, text printers), turns changes into speech, and accepts
// navigation commands from Android's accessibility services (TalkBack virtual
// nodes) or from the TCP debug port.
//
// Two speech paths exist on purpose:
//
//   * Game → speech. Every string the game itself draws is captured at the
//     text-printer entry point and spoken in full, before the typewriter
//     animation runs. Menus, lists and battle cursors are announced with the
//     label the game is showing, not a screenshot guess.
//   * TalkBack → game. A virtual accessibility node tree (status, the current
//     items, and the buttons) is published by the Android bridge; activating a
//     node becomes a synthesized key press. The player can therefore drive the
//     game entirely from TalkBack gestures.
//
// The layer never writes guest memory and never calls guest functions: speech
// is read-only, and the game is steered exclusively through the engine's key
// synthesizer (the same mechanism the touch policy uses).
//
// Speech routing is decided at the platform layer, and Android text to speech
// is the voice for everything: with TalkBack (touch exploration) actually
// driving the screen, announcements go through accessibility events so
// TalkBack's own voice and verbosity apply; in every other case -- TalkBack off,
// no screen reader, or no view to announce through -- the game speaks the same
// lines through its own Android TextToSpeech instance, which is created when
// the activity attaches rather than when the view tree appears.

#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace gbarecomp {
struct TouchFrameInfo;
}

namespace emerald::accessibility {

// TalkBack virtual-node commands. The same numbers are used by
// android/app/src/main/java/com/mstan/emeraldrecomp/accessibility/
// EmeraldAccessibility.java — keep the two lists in step.
enum class Action : int {
    Up = 1,
    Down = 2,
    Left = 3,
    Right = 4,
    Confirm = 5,
    Cancel = 6,
    Start = 7,
    ReadStatus = 8,
    Repeat = 9,
    StopSpeech = 10,
    SelectItem = 11,   // arg = absolute item index on the current surface
    NextItem = 12,
    PrevItem = 13,
    // Save states. arg = slot 1..9 for the save/load commands (0 = the slot the
    // spoken sheet is on); the cycle command has no argument.
    SaveState = 14,
    LoadState = 15,
    NextStateSlot = 16,
    StateMenu = 17,    // open/close the spoken save-state sheet
};
const char* action_name(Action action);

// RunOptions wiring. Calls the touch policy first (it classifies the frame and
// routes gestures), then speaks/announces this frame's changes and services
// queued accessibility actions. The returned key mask is the touch policy's.
std::uint16_t input_frame(const gbarecomp::TouchFrameInfo* frame);
int tcp_command(const char* request, void (*write)(void*, const char*, std::size_t),
                void* ctx);

// Platform bridge (Android: TextToSpeech + accessibility node tree). Returns
// true once a bridge is live; false on desktop or when it cannot attach.
bool install_platform_bridge();
void shutdown_platform_bridge();
bool talkback_available();

// Sink registered by the platform bridge. All strings are UTF-8.
//   speak   — queue or interrupt an utterance (interrupt != 0 flushes first)
//   update  — publish the current node tree ("items" is '\n'-separated)
//   stop    — stop speech immediately
//   rate    — set the speech rate multiplier
using SpeakFn = void (*)(const char* text, int interrupt);
using UpdateFn = void (*)(const char* status, const char* items, int selected,
                          const char* message);
void install_sink(SpeakFn speak, UpdateFn update, void (*stop)(), void (*rate)(float));

// Speak through the active sink (also used by the platform greeting and tests).
void speak_now(const char* text, bool interrupt);

// Controller hotkeys. The game is played with a pad, so the spoken screen has
// to be reachable from the pad itself — not only from TalkBack gestures or the
// TCP port. Every frame reads the host's own key state (TouchFrameInfo's
// host_keyinput, active-low, before synthesis):
//
//   L                       read the current screen (scene, selection, position)
//   Select                  repeat the last utterance
//   Select, then L          stop speech
//
// Save states are not on the pad either: they are the touch sheet below, the
// TalkBack buttons, or the runtime's own menu rows.
//
// A real pad never presses both chord buttons on the same frame, so the chords
// are separated by order and by a hold (emerald_hotkeys.h): Select alone waits
// a short window, and L inside it stops speech and drops the pending repeat.
//
// The spoken save-state sheet opens from a tap in the top-left corner of the
// game image (a deliberate, single-finger gesture; a tap there has no meaning
// in the field), and only while the overworld is free of menus, lists and
// battles. Inside it: tap saves, swipe up loads, swipe left/right changes the
// slot, and a two-finger tap closes it. Every action ends with the outcome —
// "Saved to slot 3.", "Loaded slot 3.", "Nothing saved in slot 3."
//
// Settings are not on the pad. The three options (read game text, detail,
// speech rate) are set on the launcher before play, or in the game's own Mods
// menu, and activate_from_options() reads the persisted values at start-up — so
// no combination pressed while playing can change how the game talks.
//
// Select and L are the two buttons Emerald itself never reads, with one
// exception: the naming screen reads Select (it swaps the keyboard page), so
// there the repeat modifier is R and Select is left to the game. Hotkeys are
// still delivered to the game (composed KEYINPUT is host AND synth, so nothing
// can be masked out); that is why no direction, A, B, Start or R is bound on
// other screens — a hotkey must never perform a game action as a side effect.
const char* controller_hotkeys_help();

// Queue a command from the accessibility service / TCP (thread-safe).
void push_action(Action action, int arg = 0);

// ── Save states (spoken) ─────────────────────────────────────────────────
//
// The runtime owns save states and reaches them from two places: rows in its
// settings menu, and the edge-triggered F1..F9 / Shift+F1..F9 slot hotkeys.
// Both arrive as the same host event, and a game cannot call the runtime's
// snapshot code, so the layer delivers the hotkey the host already understands
// and reads back the file the engine wrote (emerald_state_slots.h). Nothing in
// the menu changes: this is a second, spoken way in.
//
// A host event queue only exists while the game window runs (the pad and touch
// input both arrive through it). The platform bridge installs the sink that
// types the slot key; without one the layer says save states are unavailable
// in this session instead of claiming a save happened.
using SlotHotkeyFn = void (*)(int slot, int save);
void install_slot_hotkey(SlotHotkeyFn fn);

// The launch arguments, as the runtime parses them. Used only to name the file
// a slot lives in, so a spoken confirmation can say what actually happened.
void set_launch_arguments(const std::vector<std::string>& args);

// The slot the spoken save/load path uses (1..9).
int state_slot();
void set_state_slot(int slot);

// Mod plugin surface (src/mods/emerald_accessibility_plugin.cpp).
void activate_from_options();
// Adopt the persisted option values (as the launcher or the Mods menu wrote
// them) and apply them. Called at activation.
void adopt_options(const char* game_text, const char* detail, const char* rate);
void reset();
void register_text_probe();   // observes AddTextPrinter; safe to call repeatedly
void enable(bool on);
bool enabled();
void set_speak_game_text(bool on);
void set_verbosity(int level);   // 0 = menus/battle/screens only, 1 = all text
void set_rate(float rate);       // 0.5f .. 2.0f

}  // namespace emerald::accessibility

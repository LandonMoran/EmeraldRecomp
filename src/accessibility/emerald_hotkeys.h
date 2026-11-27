// emerald_hotkeys.h — pad-only commands for the spoken interface.
//
// Every command the spoken interface has is a pad command: no keyboard, no
// TalkBack, no visual menu. Emerald reads neither Select nor L, and the runtime
// composes KEYINPUT as host AND synthesized keys, so a hotkey cannot be masked
// out of the game -- those two buttons are the only ones a command may use, and
// every command is a chord of them:
//
//   L                              read the current screen
//   Select (R while naming)        repeat the last utterance
//   Select first, then L           stop speech
//
// Settings are deliberately *not* a pad command. Changing a setting needs a save
// and a deliberate trip back to the launcher (Android) or the game's own Mods
// menu, so no combination of buttons pressed while playing can change how the
// game talks. That keeps the pad surface to three commands a player can learn
// once, and makes an accidental chord harmless.
//
// A physical pad never lands two presses on the same frame, so the stop chord is
// told apart by order and by a hold, never by simultaneity:
//
//   * Select alone is remembered for a short window instead of firing at once:
//     L inside the window turns the press into "stop speech" and drops the
//     pending repeat, while letting go (or holding past the window) repeats.
//   * L alone reads immediately.
//
// The decoder is pure (no engine state, no allocation) so the staggered-press
// rules are tested without a pad: tests/hotkeys_test.cpp.
#pragma once

#include <cstdint>

#include "input_synth.h"

namespace emerald::accessibility {

enum class Hotkey : int {
    None = 0,
    Read,       // L: read the current screen
    Repeat,     // Select (R while naming): repeat the last utterance
    Stop,       // Select, then L: silence immediately
};

class HotkeyTracker {
public:
    static constexpr std::uint16_t kMask = gbarecomp::kGbaKeyAll;
    // ~170 ms at 60 frames/s: long enough for a second thumb to reach L, short
    // enough that a repeat does not feel like a dropped press.
    static constexpr int kChordFrames = 10;

    // Seed with the host's current key state so a button already held when the
    // layer starts (or restarts) is not read as a fresh press.
    void reset(std::uint16_t host) {
        host_ = static_cast<std::uint16_t>(host & kMask);
        waiting_ = false;
        waited_ = 0;
    }

    // Once per guest frame. `host` is the pad's own key state, active-low and
    // before synthesis. `naming` selects the naming screen's modifier.
    Hotkey poll(std::uint16_t host, bool naming) {
        const std::uint16_t pressed = static_cast<std::uint16_t>(~host & kMask);
        const std::uint16_t was_pressed = static_cast<std::uint16_t>(~host_ & kMask);
        const std::uint16_t edge = static_cast<std::uint16_t>(pressed & ~was_pressed);
        host_ = static_cast<std::uint16_t>(host & kMask);
        // The naming screen reads Select itself (it swaps the keyboard page), so
        // there the modifier is R, which that screen ignores.
        const std::uint16_t modifier =
            naming ? gbarecomp::kGbaKeyR : gbarecomp::kGbaKeySelect;
        const std::uint16_t l = gbarecomp::kGbaKeyL;

        if ((edge & l) && (pressed & modifier)) {       // Select first, then L
            waiting_ = false;
            return Hotkey::Stop;
        }
        if (edge & l) {
            waiting_ = false;
            return Hotkey::Read;
        }
        if (edge & modifier) {                          // Select alone: repeat?
            waiting_ = true;
            waited_ = 0;
            return Hotkey::None;
        }
        if (!waiting_) return Hotkey::None;
        if ((pressed & modifier) == 0) {                // released alone: repeat
            waiting_ = false;
            return Hotkey::Repeat;
        }
        if (++waited_ >= kChordFrames) {                // held past the window
            waiting_ = false;
            return Hotkey::Repeat;
        }
        return Hotkey::None;
    }

private:
    std::uint16_t host_ = kMask;
    bool waiting_ = false;
    int waited_ = 0;
};

}  // namespace emerald::accessibility

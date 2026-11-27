// tests/hotkeys_test.cpp — the pad command decoder (emerald_hotkeys.h).
//
// A physical pad never lands two presses on the same frame, so every chord has
// to survive staggered presses: Select then L stops, L then Select held opens
// the spoken settings, Select alone repeats. These cases pin that down without
// a pad, an emulator or text to speech.
#include "accessibility/emerald_hotkeys.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>

using emerald::accessibility::Hotkey;
using emerald::accessibility::HotkeyTracker;

namespace {

constexpr std::uint16_t kA = gbarecomp::kGbaKeyA;
constexpr std::uint16_t kL = gbarecomp::kGbaKeyL;
constexpr std::uint16_t kR = gbarecomp::kGbaKeyR;
constexpr std::uint16_t kSelect = gbarecomp::kGbaKeySelect;

void require(bool pass, const char* message) {
    if (!pass) {
        std::fprintf(stderr, "hotkeys: %s\n", message);
        std::exit(1);
    }
}

// One guest frame with `held` down (active-high, as a pad reports it).
Hotkey frame(HotkeyTracker& tracker, std::uint16_t held, bool naming = false) {
    return tracker.poll(static_cast<std::uint16_t>(~held & HotkeyTracker::kMask), naming);
}

// Poll a held combination until something fires, returning the frame offset
// (1-based) or -1. Fails the test if anything other than `expect` fires.
int wait_for(HotkeyTracker& tracker, std::uint16_t held, Hotkey expect, int limit,
             bool naming = false) {
    for (int i = 1; i <= limit; ++i) {
        const Hotkey got = frame(tracker, held, naming);
        if (got == Hotkey::None) continue;
        require(got == expect, "unexpected command while holding");
        return i;
    }
    return -1;
}

}  // namespace

int main() {
    {   // L reads once per press; holding it does not repeat the read.
        HotkeyTracker t;
        require(frame(t, kL) == Hotkey::Read, "L must read");
        for (int i = 0; i < 30; ++i)
            require(frame(t, kL) == Hotkey::None, "held L must stay silent");
        require(frame(t, 0) == Hotkey::None, "releasing L must stay silent");
        require(frame(t, kL) == Hotkey::Read, "L again must read");
    }
    {   // Select alone is the repeat, delivered on release.
        HotkeyTracker t;
        require(frame(t, kSelect) == Hotkey::None, "Select waits for the chord");
        require(frame(t, 0) == Hotkey::Repeat, "Select alone repeats on release");
        require(frame(t, 0) == Hotkey::None, "the repeat fires once");
    }
    {   // Select then L (a real pad's staggered presses) stops, never repeats.
        HotkeyTracker t;
        require(frame(t, kSelect) == Hotkey::None, "Select waits");
        require(frame(t, kSelect | kL) == Hotkey::Stop, "Select then L stops");
        require(frame(t, kSelect | kL) == Hotkey::None, "the stop fires once");
        require(frame(t, kSelect) == Hotkey::None, "nothing is left pending");
        require(frame(t, 0) == Hotkey::None, "no repeat after a stop");
    }
    {   // Both arriving on one frame is the stop chord.
        HotkeyTracker t;
        require(frame(t, kSelect | kL) == Hotkey::Stop, "simultaneous chord stops");
        // Resting on the stop chord must not repeat or do anything else.
        for (int i = 0; i < 60; ++i)
            require(frame(t, kSelect | kL) == Hotkey::None,
                    "a held stop chord stays silent");
    }
    {   // Holding Select past the window repeats without waiting for release.
        HotkeyTracker t;
        require(frame(t, kSelect) == Hotkey::None, "Select waits");
        require(wait_for(t, kSelect, Hotkey::Repeat, HotkeyTracker::kChordFrames) ==
                    HotkeyTracker::kChordFrames,
                "held Select repeats once, after the chord window");
        require(frame(t, kSelect) == Hotkey::None, "held Select does not repeat again");
        require(frame(t, 0) == Hotkey::None, "releasing after a held repeat is silent");
    }
    {   // Naming: Select belongs to the game, so R is the modifier there.
        HotkeyTracker t;
        require(frame(t, kSelect, true) == Hotkey::None, "naming: Select is the game's");
        require(frame(t, kSelect | kR, true) == Hotkey::None, "naming: R waits for the chord");
        require(frame(t, kSelect | kR | kL, true) == Hotkey::Stop, "naming: R then L stops");
        HotkeyTracker u;
        require(frame(u, kR, true) == Hotkey::None, "naming: R waits");
        require(frame(u, 0, true) == Hotkey::Repeat, "naming: R alone repeats");
        require(frame(u, kL, true) == Hotkey::Read, "naming: L still reads");
    }
    {   // A pad held from before the layer starts is not a fresh press.
        HotkeyTracker t;
        t.reset(static_cast<std::uint16_t>(~kL & HotkeyTracker::kMask));
        require(frame(t, kL) == Hotkey::None, "held L at start is not a press");
        require(frame(t, 0) == Hotkey::None, "releasing it is silent");
        require(frame(t, kL) == Hotkey::Read, "L pressed after the start reads");
    }
    {   // Nothing pressed during play can change a setting: L and Select
        // held together repeat the last utterance and nothing else.
        HotkeyTracker t;
        require(frame(t, kL) == Hotkey::Read, "L first reads the screen");
        require(frame(t, kL | kSelect) == Hotkey::None, "L then Select waits");
        require(wait_for(t, kL | kSelect, Hotkey::Repeat,
                         HotkeyTracker::kChordFrames + 4) ==
                    HotkeyTracker::kChordFrames,
                "holding both repeats the last utterance");
        for (int i = 0; i < 60; ++i)
            require(frame(t, kL | kSelect) == Hotkey::None,
                    "however long it is held, it does nothing else");
    }
    {   // A chord already down at start is not a press.
        HotkeyTracker t;
        t.reset(static_cast<std::uint16_t>(~(kL | kSelect) & HotkeyTracker::kMask));
        for (int i = 0; i < 60; ++i)
            require(frame(t, kL | kSelect) == Hotkey::None,
                    "a held-at-start chord does nothing");
        require(frame(t, 0) == Hotkey::None, "releasing the held chord is silent");
    }
    {   // Gameplay keys never produce a command on their own.
        HotkeyTracker t;
        for (int i = 0; i < 5; ++i)
            require(frame(t, kA) == Hotkey::None, "A belongs to the game");
    }
    std::printf("hotkeys: ok\n");
    return 0;
}

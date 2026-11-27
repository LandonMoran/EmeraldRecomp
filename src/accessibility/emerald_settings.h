// emerald_settings.h — the spoken interface's three options as plain data.
//
// The options live in the mod's own state (mods/state.toml) and every editor
// writes the same values:
//
//   game-text  on/off              speak the text the game prints
//   verbosity  everything/menus    everything = all printed text, menus = only
//                                  screens, menus, lists and battles
//   rate       slow/normal/fast    TextToSpeech rate multiplier
//
// On Android they are set on the launcher screen before play; the game's Mods
// menu edits the same values. There is no pad path: a button combination can
// never change how the game talks, so an accidental chord is harmless.
//
// Everything here is pure (no engine state, no allocation beyond a short
// string), so the value names and the persisted wording are unit-tested with
// g++ alone (tests/settings_test.cpp).
#pragma once

#include <string>

namespace emerald::accessibility {

// The mod package and feature that own these options; the same identity the
// manifest and the Mods menu use.
constexpr const char* kSpokenUiPackage = "pokemon-emerald.accessibility.spoken-ui";
constexpr const char* kSpokenUiFeature = "spoken-ui";

// Option ids, exactly as
// mods/preloaded/packages/pokemon-emerald.accessibility.spoken-ui/1.0.0/
// manifest.toml spells them (tests/settings_test.cpp checks the manifest).
constexpr const char* kGameTextOption = "game-text";
constexpr const char* kDetailOption = "verbosity";
constexpr const char* kRateOption = "rate";

// Live values: what the layer does right now. `rate` indexes the manifest's
// slow / normal / fast choices.
struct SpokenSettings {
    bool read_game_text = true;
    bool detail_everything = true;
    int rate = 1;
};

inline const char* rate_value(int index) {
    switch (index) {
        case 0: return "slow";
        case 2: return "fast";
        default: return "normal";
    }
}

inline float rate_multiplier(int index) {
    switch (index) {
        case 0: return 0.8f;
        case 2: return 1.3f;
        default: return 1.0f;
    }
}

// Values written by the launcher (or by the Mods menu, or by an older profile)
// back into live settings. An absent value means "take the manifest default".
inline bool game_text_on(const char* value) {
    if (!value || !value[0]) return true;
    return !(value[0] == 'o' && value[1] == 'f' && value[2] == 'f' && !value[3]);
}

inline bool detail_everything(const char* value) {
    if (!value || !value[0]) return true;
    return std::string(value) != "menus";
}

inline int rate_index(const char* value) {
    if (!value || !value[0]) return 1;
    const std::string v(value);
    if (v == "slow") return 0;
    if (v == "fast") return 2;
    return 1;
}

}  // namespace emerald::accessibility

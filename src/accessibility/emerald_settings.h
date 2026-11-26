// emerald_settings.h — the spoken interface's settings as pad-editable data.
//
// The Mods menu and the pad change the same three options (read game text,
// detail, speech rate). A pad change is applied to the live session and written
// back through the engine's own mod state, so the menu shows the new value and
// it survives a restart; a menu change is read back by
// activate_from_options() when the profile starts.
//
// Everything here is pure (no engine state, no allocation beyond a short
// string): the item order, the spoken labels and the persisted wording are
// decided without touching the runtime, so the cycling rules are unit-tested
// with g++ alone (tests/settings_test.cpp).
#pragma once

#include <string>

namespace emerald::accessibility {

// The mod package and feature that own these options; the same identity the
// manifest and the Mods menu use.
constexpr const char* kSpokenUiPackage = "pokemon-emerald.accessibility.spoken-ui";
constexpr const char* kSpokenUiFeature = "spoken-ui";

// Option ids and their values, exactly as
// mods/preloaded/packages/pokemon-emerald.accessibility.spoken-ui/1.0.0/
// manifest.toml spells them (tests/settings_test.cpp checks the manifest).
constexpr const char* kGameTextOption = "game-text";
constexpr const char* kDetailOption = "verbosity";
constexpr const char* kRateOption = "rate";

enum class SettingItem : int {
    ReadGameText = 0,
    Detail = 1,
    SpeechRate = 2,
    ResetDefaults = 3,
};
constexpr int kSettingItemCount = 4;

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

inline const char* detail_value(bool everything) {
    return everything ? "everything" : "menus";
}

inline const char* game_text_value(bool on) { return on ? "on" : "off"; }

// Values written by the menu (or by an older profile) back into live settings.
// An absent value means "take the manifest default".
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

inline void reset_settings(SpokenSettings* settings) {
    if (settings) *settings = SpokenSettings{};
}

inline const char* setting_name(int item) {
    switch (item) {
        case 0: return "Read game text";
        case 1: return "Detail";
        case 2: return "Speech rate";
        default: return "Reset to defaults";
    }
}

// The line that reports an item's current value.
inline std::string setting_speech(int item, const SpokenSettings& settings) {
    switch (item) {
        case 0:
            return std::string("Read game text: ") +
                   game_text_value(settings.read_game_text) + ".";
        case 1:
            return std::string("Detail: ") +
                   (settings.detail_everything ? "everything."
                                               : "menus and battles only.");
        case 2:
            return std::string("Speech rate: ") + rate_value(settings.rate) + ".";
        default:
            return "Reset to defaults. Select resets everything.";
    }
}

// Apply one Select press on an item and return what to say about the result.
inline std::string cycle_setting(int item, SpokenSettings* settings) {
    if (!settings) return {};
    switch (item) {
        case 0: settings->read_game_text = !settings->read_game_text; break;
        case 1: settings->detail_everything = !settings->detail_everything; break;
        case 2: settings->rate = (settings->rate + 1) % 3; break;
        default:
            reset_settings(settings);
            return "Settings reset to defaults. Read game text on, detail "
                   "everything, speech rate normal.";
    }
    return setting_speech(item, *settings);
}

// The persisted option an item writes, or nullptr for the reset row (which
// writes all three).
inline const char* setting_option_id(int item) {
    switch (item) {
        case 0: return kGameTextOption;
        case 1: return kDetailOption;
        case 2: return kRateOption;
        default: return nullptr;
    }
}

inline const char* setting_option_value(int item, const SpokenSettings& settings) {
    switch (item) {
        case 0: return game_text_value(settings.read_game_text);
        case 1: return detail_value(settings.detail_everything);
        case 2: return rate_value(settings.rate);
        default: return nullptr;
    }
}

}  // namespace emerald::accessibility

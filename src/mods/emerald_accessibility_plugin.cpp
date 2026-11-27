// emerald_accessibility_plugin.cpp — mod activation for the spoken interface.
//
// The mod catalog ships "Spoken Interface" preloaded and enabled, so a player
// who relies on speech does not have to find it in an inaccessible Mods menu.
// Its three options are set on the launcher screen before play (Android) or in
// the Mods menu, never from the pad; both edit the same values:
//
//   game-text  on/off     speak the game's printed dialogue and battle text
//   verbosity  everything/menus   everything = all printed text, menus = only
//                         screens, menus, lists and battles
//   rate       slow/normal/fast   TextToSpeech rate multiplier
//
// The C++ spoken-UI core and its TalkBack bridge are compiled into every
// Emerald build; this file only arms them when the feature is active.

#include <string>

#include "accessibility/emerald_a11y.h"
#include "accessibility/emerald_settings.h"
#include "mod_runtime.h"

namespace {

const char* option(const char* id) {
    return gba_mod_option_value(emerald::accessibility::kSpokenUiPackage,
                                emerald::accessibility::kSpokenUiFeature, id);
}

}  // namespace

namespace emerald::accessibility {

void activate_from_options() {
    enable(true);
    register_text_probe();
    // The Mods menu's persisted values, adopted into the live settings the pad
    // edits too, so the menu and the pad are one setting rather than two.
    adopt_options(option(kGameTextOption), option(kDetailOption), option(kRateOption));
    // The player is holding a pad, not a TalkBack phone: say how to reach the
    // read/repeat/stop and settings commands before the first menu appears.
    std::string greeting = "Spoken interface on. ";
    greeting += controller_hotkeys_help();
    speak_now(greeting.c_str(), true);
}

}  // namespace emerald::accessibility

GBA_MOD_CONSTRUCTOR(emerald_register_accessibility_plugin) {
    // Register the text-printer probe at static-init time so a later reset
    // callback never has to add a hook while the engine walks its hook list.
    emerald::accessibility::register_text_probe();
    gba_mod_register_reset_callback(emerald::accessibility::reset);
    gba_mod_register_activation_plugin("pokemon-emerald.spoken-ui",
                                       emerald::accessibility::activate_from_options);
}

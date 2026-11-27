// tests/settings_test.cpp — the spoken settings model (emerald_settings.h).
//
// The launcher and the Mods menu write one setting, not two: these cases pin
// the value names, that the launcher's editor and the game agree on them, and
// that they are the choices the shipped manifest declares.
#include "accessibility/emerald_settings.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>

using emerald::accessibility::detail_everything;
using emerald::accessibility::kDetailOption;
using emerald::accessibility::kGameTextOption;
using emerald::accessibility::kRateOption;
using emerald::accessibility::rate_index;
using emerald::accessibility::rate_multiplier;
using emerald::accessibility::rate_value;
using emerald::accessibility::SpokenSettings;

namespace {

void require(bool pass, const char* message) {
    if (!pass) {
        std::fprintf(stderr, "settings: %s\n", message);
        std::exit(1);
    }
}

bool same(const std::string& got, const char* want) { return got == want; }

bool same(const char* got, const char* want) {
    return got && std::strcmp(got, want) == 0;
}

std::string manifest_text() {
#ifdef EMERALD_SPOKEN_UI_MANIFEST
    const char* path = EMERALD_SPOKEN_UI_MANIFEST;
#else
    const char* path =
        "mods/preloaded/packages/pokemon-emerald.accessibility.spoken-ui/1.0.0/"
        "manifest.toml";
#endif
    std::ifstream file(path);
    std::ostringstream text;
    text << file.rdbuf();
    return text.str();
}

bool manifest_has(const std::string& manifest, const char* key, const char* value) {
    return manifest.find(std::string(key) + " = \"" + value + "\"") !=
           std::string::npos;
}

}  // namespace

int main() {
    {   // Defaults are the manifest defaults.
        const SpokenSettings s;
        require(s.read_game_text, "default reads game text");
        require(s.detail_everything, "default detail is everything");
        require(s.rate == 1, "default rate is normal");
        require(same(rate_value(0), "slow") && same(rate_value(1), "normal") &&
                    same(rate_value(2), "fast"),
                "rate values are the manifest's");
        require(rate_multiplier(0) == 0.8f && rate_multiplier(1) == 1.0f &&
                    rate_multiplier(2) == 1.3f,
                "rate multipliers");
    }
    {   // Values the menu wrote parse back into live settings.
        require(!emerald::accessibility::game_text_on("off"), "parses off");
        require(emerald::accessibility::game_text_on("on"), "parses on");
        require(emerald::accessibility::game_text_on(nullptr), "missing is the default");
        require(!detail_everything("menus"), "parses menus");
        require(detail_everything("everything"), "parses everything");
        require(detail_everything(""), "empty detail is the default");
        require(rate_index("slow") == 0 && rate_index("normal") == 1 &&
                    rate_index("fast") == 2 && rate_index("") == 1,
                "parses rate");
    }
    {   // The option ids and every value written are choices the manifest ships.
        const std::string manifest = manifest_text();
        require(!manifest.empty(), "manifest readable");
        require(manifest_has(manifest, "id", kGameTextOption), "manifest has game-text");
        require(manifest_has(manifest, "id", kDetailOption), "manifest has verbosity");
        require(manifest_has(manifest, "id", kRateOption), "manifest has rate");
        for (const char* value : {"on", "off"})
            require(manifest_has(manifest, "value", value), "game-text choice");
        for (const char* value : {"everything", "menus"})
            require(manifest_has(manifest, "value", value), "detail choice");
        for (const char* value : {"slow", "normal", "fast"})
            require(manifest_has(manifest, "value", value), "rate choice");
        require(manifest.find("id = \"spoken-ui\"") != std::string::npos,
                "manifest feature id matches the persisted identity");
    }
    std::printf("settings: ok\n");
    return 0;
}

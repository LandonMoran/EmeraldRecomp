// tests/state_slots_test.cpp — the spoken save/load naming and path rule
// (src/accessibility/emerald_state_slots.h).
//
// The layer speaks "Saved to slot N." only after the file the engine writes has
// changed, so the slot path it looks at has to be the engine's own rule
// (runtime.cpp slot_path): --state-dir/stateN, else <rom>.stateN. These cases
// pin that rule, the slot cycle, and the sentences the player hears.
#include "accessibility/emerald_state_slots.h"

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace slots = emerald::accessibility;

namespace {

void require(bool pass, const char* message) {
    if (!pass) {
        std::fprintf(stderr, "state slots: %s\n", message);
        std::exit(1);
    }
}

bool same(const std::string& got, const char* want) { return got == want; }

std::string write_temp_toml() {
    const char* path = "/tmp/emerald_state_slots_test.toml";
    std::FILE* file = std::fopen(path, "wb");
    require(file != nullptr, "cannot write the temporary game.toml");
    std::fputs(
        "# test config\n"
        "[game]\n"
        "name = \"Pokemon Emerald Version\"\n"
        "short_name = \"emerald\"\n"
        "\n"
        "[rom]\n"
        "path = \"roms/emerald_usa.gba\"   # user-provided\n"
        "\n"
        "[save]\n"
        "path = \"saves/emerald.sav\"\n",
        file);
    std::fclose(file);
    return path;
}

}  // namespace

int main() {
    // ── Slots ────────────────────────────────────────────────────────────
    require(slots::clamp_state_slot(0) == 1, "slot 0 clamps to 1");
    require(slots::clamp_state_slot(10) == slots::kStateSlotCount,
            "slot 10 clamps to the last slot");
    require(slots::next_state_slot(1) == 2, "next slot");
    require(slots::next_state_slot(slots::kStateSlotCount) == 1,
            "the slot cycle wraps");
    require(slots::prev_state_slot(1) == slots::kStateSlotCount,
            "the reverse cycle wraps");

    // ── Paths (runtime.cpp slot_path) ────────────────────────────────────
    require(same(slots::state_slot_path("state", "roms/emerald_usa.gba", 3),
                 "state/state3"),
            "--state-dir names stateN, not <rom>.stateN");
    require(same(slots::state_slot_path("", "roms/emerald_usa.gba", 9),
                 "roms/emerald_usa.state9"),
            "the default slot sits next to the ROM");
    require(same(slots::state_slot_path("", "/data/app/files/roms/emerald.usa.gba", 1),
                 "/data/app/files/roms/emerald.usa.state1"),
            "only the extension is replaced, not the first dot");
    require(same(slots::state_slot_path("", "emerald_usa", 2), "emerald_usa.state2"),
            "a ROM without an extension still gets one");
    require(slots::state_slot_path("", "", 1).empty(),
            "no ROM and no --state-dir means no path to look at");
    require(same(slots::state_slot_path("dir/", "rom.gba", 4), "dir/state4"),
            "a trailing separator is not doubled");

    // ── Launch paths ─────────────────────────────────────────────────────
    const std::string toml = write_temp_toml();
    require(same(slots::rom_path_from_toml(toml), "roms/emerald_usa.gba"),
            "[rom] path is read without its comment");

    {
        const std::vector<std::string> args = {"EmeraldRecomp", "--bios",
                                               "gbarecomp/bios/gba_bios.bin",
                                               "--rom", "variants/emerald/roms/emerald_usa.gba",
                                               "variants/emerald/game.toml"};
        const slots::LaunchPaths paths = slots::launch_paths_from_args(args);
        require(same(paths.rom, "variants/emerald/roms/emerald_usa.gba"),
                "--rom wins over the TOML");
        require(paths.state_dir.empty(), "no --state-dir means next to the ROM");
    }
    {
        const std::vector<std::string> args = {"EmeraldRecomp", "--state-dir",
                                               "/tmp/states", "--rom", "rom.gba"};
        const slots::LaunchPaths paths = slots::launch_paths_from_args(args);
        require(same(paths.state_dir, "/tmp/states"), "--state-dir is read");
    }
    {
        // Android: the shell stages the game.toml as a relative argument and
        // changes into the app's storage, so the ROM comes from the TOML and is
        // resolved against the TOML's own directory.
        const std::vector<std::string> args = {"main",
                                               "variants/emerald/game.toml",
                                               "--no-launcher"};
        const std::string relative_toml = "variants/emerald/game.toml";
        // Point the same arguments at the temporary config we just wrote.
        std::vector<std::string> patched = args;
        patched[1] = toml;
        const slots::LaunchPaths paths = slots::launch_paths_from_args(patched);
        require(same(paths.rom, "/tmp/roms/emerald_usa.gba"),
                "the TOML's [rom] path resolves against the TOML's directory");
        require(same(slots::state_slot_path(paths.state_dir, paths.rom, 5),
                     "/tmp/roms/emerald_usa.state5"),
                "the derived slot path is the engine's");
        (void)relative_toml;
    }

    // ── Wording ──────────────────────────────────────────────────────────
    require(same(slots::slot_save_request(3), "Saving to slot 3."), "save request");
    require(same(slots::slot_saved(3), "Saved to slot 3."), "save confirmation");
    require(same(slots::slot_save_failed(3), "Slot 3 did not save."), "save failure");
    require(same(slots::slot_load_request(2), "Loading slot 2."), "load request");
    require(same(slots::slot_loaded(2), "Loaded slot 2."), "load confirmation");
    require(same(slots::slot_load_failed(2), "Slot 2 could not be loaded."),
            "load failure");
    require(same(slots::slot_missing(8), "Nothing saved in slot 8."),
            "empty slot");
    require(same(slots::slot_pick(4), "Slot 4."), "slot picker");
    require(slots::slot_sheet_speech(1).find("Tap to save") != std::string::npos,
            "the sheet names the tap gesture");
    require(slots::slot_sheet_speech(1).find("swipe up to load") != std::string::npos,
            "the sheet names the load gesture");
    require(slots::slot_sheet_after_slot_speech(6).find("Slot 6.") == 0,
            "a slot change leads with the slot");

    std::remove(toml.c_str());
    std::printf("state slots: ok\n");
    return 0;
}

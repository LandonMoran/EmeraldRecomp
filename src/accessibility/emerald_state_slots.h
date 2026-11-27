// emerald_state_slots.h — state slots for the spoken save/load path.
//
// The engine owns save states: it snapshots the whole machine for slots 1..9
// (RunOptions::save_state_slot_count) and writes them next to the ROM as
// "<rom>.stateN", or as "<state-dir>/stateN" when --state-dir is given. The
// runtime exposes them two ways — rows in the settings menu, and the
// edge-triggered F1..F9 (load) / Shift+F1..F9 (save) hotkeys — and both end in
// the same host event (host_window.h: HostWindow::Events::save_slot/load_slot).
//
// The spoken interface speaks the outcome, so it has to know which file a slot
// names: this header mirrors the engine's slot_path() (runtime.cpp) exactly, so
// the layer can look at the file the engine just wrote without guessing a path.
//
// Everything here is pure — no engine state, no emulation — so the naming, the
// path rule and the wording are unit-tested with g++ alone
// (tests/state_slots_test.cpp).
#pragma once

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace emerald::accessibility {

// RunOptions::save_state_slot_count in src/main.cpp. The menu reaches slot 10;
// the hotkeys (and therefore the spoken path) cover 1..9.
constexpr int kStateSlotCount = 9;

inline int clamp_state_slot(int slot) {
    if (slot < 1) return 1;
    if (slot > kStateSlotCount) return kStateSlotCount;
    return slot;
}

// Slot cycling wraps so a player can hold one direction to reach every slot.
inline int next_state_slot(int slot) {
    return clamp_state_slot(slot) >= kStateSlotCount ? 1 : clamp_state_slot(slot) + 1;
}

inline int prev_state_slot(int slot) {
    return clamp_state_slot(slot) <= 1 ? kStateSlotCount : clamp_state_slot(slot) - 1;
}

inline std::string path_dirname(const std::string& path) {
    const std::size_t slash = path.find_last_of("/\\");
    if (slash == std::string::npos) return std::string();
    return path.substr(0, slash);
}

inline std::string path_join(const std::string& dir, const std::string& name) {
    if (dir.empty()) return name;
    if (dir.back() == '/' || dir.back() == '\\') return dir + name;
    return dir + "/" + name;
}

// runtime.cpp slot_path():
//   --state-dir <dir>  ->  <dir>/state<N>
//   otherwise          ->  <rom path with its extension replaced by .state<N>
inline std::string state_slot_path(const std::string& state_dir,
                                   const std::string& rom, int slot) {
    const std::string name = "state" + std::to_string(clamp_state_slot(slot));
    if (!state_dir.empty()) return path_join(state_dir, name);
    if (rom.empty()) return std::string();
    std::string base = rom;
    const std::size_t slash = base.find_last_of("/\\");
    const std::size_t dot = base.find_last_of('.');
    if (dot != std::string::npos && (slash == std::string::npos || dot > slash))
        base.resize(dot);
    return base + "." + name;
}

inline std::string trim_copy(const std::string& text) {
    std::size_t first = 0, last = text.size();
    while (first < last && (text[first] == ' ' || text[first] == '\t' ||
                            text[first] == '\r' || text[first] == '\n'))
        ++first;
    while (last > first && (text[last - 1] == ' ' || text[last - 1] == '\t' ||
                            text[last - 1] == '\r' || text[last - 1] == '\n'))
        --last;
    return text.substr(first, last - first);
}

// "[rom] path" out of a game.toml: the same value the runtime reads to find the
// cartridge, and the only input it uses besides the command line.
inline std::string rom_path_from_toml(const std::string& toml_path) {
    std::FILE* file = std::fopen(toml_path.c_str(), "rb");
    if (!file) return std::string();
    std::string text;
    char buffer[4096];
    std::size_t got = 0;
    while ((got = std::fread(buffer, 1, sizeof(buffer), file)) > 0)
        text.append(buffer, got);
    std::fclose(file);

    bool in_rom = false;
    std::size_t start = 0;
    while (start <= text.size()) {
        std::size_t end = text.find('\n', start);
        if (end == std::string::npos) end = text.size();
        const std::string line = trim_copy(text.substr(start, end - start));
        start = end + 1;
        if (line.empty() || line[0] == '#') {
            if (end == text.size()) break;
            continue;
        }
        if (line[0] == '[') {
            in_rom = line == "[rom]";
            if (end == text.size()) break;
            continue;
        }
        if (in_rom) {
            const std::size_t eq = line.find('=');
            if (eq == std::string::npos) continue;
            if (trim_copy(line.substr(0, eq)) != "path") continue;
            const std::string value = trim_copy(line.substr(eq + 1));
            if (!value.empty() && value.front() == '"') {
                const std::size_t close = value.find('"', 1);
                if (close != std::string::npos)
                    return value.substr(1, close - 1);
            }
            // Bare value: a trailing "# ..." is a comment, not part of the path.
            const std::size_t hash = value.find('#');
            return trim_copy(hash == std::string::npos ? value
                                                       : value.substr(0, hash));
        }
        if (end == text.size()) break;
    }
    return std::string();
}

// Where the engine will write state slots for this process. Resolved from the
// same two inputs as the runtime: --state-dir / --rom on the command line, else
// the game.toml argument's [rom] path, resolved relative to that file.
struct LaunchPaths {
    std::string state_dir;   // --state-dir, empty when unset
    std::string rom;         // resolved cartridge path, empty when unknown
};

inline LaunchPaths launch_paths_from_args(const std::vector<std::string>& args) {
    LaunchPaths paths;
    std::string toml;
    for (std::size_t i = 1; i < args.size(); ++i) {
        const std::string& arg = args[i];
        if (arg == "--rom" && i + 1 < args.size()) {
            paths.rom = args[++i];
        } else if (arg == "--state-dir" && i + 1 < args.size()) {
            paths.state_dir = args[++i];
        } else if (arg.size() > 5 && arg.compare(arg.size() - 5, 5, ".toml") == 0) {
            toml = arg;   // the last positional .toml is the game config
        }
    }
    if (paths.rom.empty() && !toml.empty()) {
        const std::string from_toml = rom_path_from_toml(toml);
        if (!from_toml.empty()) {
            const std::string dir = path_dirname(toml);
            const bool absolute = from_toml[0] == '/' || from_toml[0] == '\\' ||
                                  (from_toml.size() > 1 && from_toml[1] == ':');
            // The runtime resolves a TOML-relative path against the TOML's own
            // directory; a relative --rom is taken from the working directory.
            paths.rom = (absolute || dir.empty()) ? from_toml
                                                  : path_join(dir, from_toml);
        }
    }
    return paths;
}

// ── Wording ──────────────────────────────────────────────────────────────
// One place for the sentences so the layer, the tests and the docs agree.

inline std::string slot_save_request(int slot) {
    return "Saving to slot " + std::to_string(clamp_state_slot(slot)) + ".";
}

inline std::string slot_saved(int slot) {
    return "Saved to slot " + std::to_string(clamp_state_slot(slot)) + ".";
}

inline std::string slot_save_failed(int slot) {
    return "Slot " + std::to_string(clamp_state_slot(slot)) + " did not save.";
}

inline std::string slot_load_request(int slot) {
    return "Loading slot " + std::to_string(clamp_state_slot(slot)) + ".";
}

inline std::string slot_loaded(int slot) {
    return "Loaded slot " + std::to_string(clamp_state_slot(slot)) + ".";
}

inline std::string slot_load_failed(int slot) {
    return "Slot " + std::to_string(clamp_state_slot(slot)) +
           " could not be loaded.";
}

inline std::string slot_missing(int slot) {
    return "Nothing saved in slot " + std::to_string(clamp_state_slot(slot)) + ".";
}

inline std::string slot_pick(int slot) {
    return "Slot " + std::to_string(clamp_state_slot(slot)) + ".";
}

// The spoken sheet that the corner tap opens: what it is, which slot it will
// use, and the four gestures that drive it.
inline std::string slot_sheet_speech(int slot) {
    return "Save state, slot " + std::to_string(clamp_state_slot(slot)) +
           ". Tap to save, swipe up to load, swipe left or right to change "
           "slot, two-finger tap to close.";
}

inline std::string slot_sheet_after_slot_speech(int slot) {
    return "Slot " + std::to_string(clamp_state_slot(slot)) +
           ". Tap to save, swipe up to load.";
}

// Spoken when the running session has no host event queue to deliver the slot
// hotkey to (headless runs, or a build without the SDL host window).
inline const char* slot_unavailable_speech() {
    return "Save states need the game window. They are not available in this "
           "session.";
}

}  // namespace emerald::accessibility

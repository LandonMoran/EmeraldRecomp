// emerald_map_names.h — where the player is, in words.
//
// The guest keeps no map name: the map header carries a layout, music and a
// region-map section, and the layout carries size and blocks. The town banner a
// sighted player reads comes from data the ROM never needs again after boot, so
// the names are compiled in from the decomp's map metadata instead
// (tools/gen_map_names.py) and looked up by the map group and number the game
// has loaded.

#pragma once

#include <cstdint>

namespace emerald::accessibility {

struct MapNameEntry {
    std::uint8_t group;
    std::uint8_t num;
    const char* symbol;   // "MauvilleCity_PokemonCenter_1F"
    const char* spoken;   // "Mauville City Pokémon Center 1F"
};

// The spoken name for a loaded map, or nullptr when the table has no entry.
const char* map_name_spoken(int group, int num);
// The decomp symbol, for logs and the puzzle JSON.
const char* map_name_symbol(int group, int num);

}  // namespace emerald::accessibility

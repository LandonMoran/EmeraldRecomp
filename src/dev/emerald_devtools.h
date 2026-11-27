// emerald_devtools.h — developer-only testing commands.
//
// These commands exist so a puzzle can be tested without playing to it: warp
// the running game to a chosen map tile, read one variable or flag, and dump a
// diagnostic snapshot of the field. They are NOT part of the player-facing
// experience and are removed from normal builds by CMake:
//
//   cmake ... -DEMERALD_DEVTOOLS=ON
//
// The warp deliberately does not poke the player's coordinates. It writes the
// same SaveBlock warp record `SetContinueGameWarp`/`ApplyCurrentWarp` produce
// and then hands control to the game's own `CB2_LoadMap`, so the map loads
// through the normal path: `CB2_LoadMap` -> `CB2_DoChangeMap` ->
// `LoadMapFromWarp` -> the map's `MAP_SCRIPT_ON_TRANSITION` /
// `MAP_SCRIPT_ON_LOAD` scripts -> object spawning -> `SetPlayerCoordsFromWarp`
// -> back to `CB1_Overworld`/`CB2_Overworld`. Coordinate-only teleports skip
// all of that and leave invalid puzzle state; this does not.
//
// Warp destination, in the terms the game uses:
//   SaveBlock1.pos            (+0x00) s16 x, s16 y        map tile
//   SaveBlock1.location       (+0x04) mapGroup, mapNum, warpId, x, y
//   SaveBlock1.continueGameWarp (+0x0C) same shape, used by Continue/whiteout
// `warpId = 0xFF` (WARP_ID_NONE) makes the load use the explicit x/y instead
// of a warp event's stored coordinates, which is what a scripted warp does.

#pragma once

#include <cstddef>

namespace emerald::dev {

#if defined(EMERALD_DEVTOOLS)

bool enabled();

// Handles `emerald_dev_*` commands; returns 1 when the request was one of ours
// and 0 so the caller can pass it to the accessibility layer.
int tcp_command(const char* request, void (*write)(void*, const char*, std::size_t),
                void* ctx);

// Per-frame service for a warp in flight (load verification, facing turn).
void frame();

void reset();

#else

inline bool enabled() { return false; }
inline int tcp_command(const char*, void (*)(void*, const char*, std::size_t), void*) {
    return 0;
}
inline void frame() {}
inline void reset() {}

#endif

}  // namespace emerald::dev

// emerald_nav.h — exit / door / stair awareness for the Emerald accessibility
// layer.
//
// Emerald keeps the current map's interactive geometry in the map header: a
// pointer to MapEvents in ROM, which lists warp tiles (doors, stairs, cave
// mouths) with their coordinates, elevation and destination map. Reading that
// gives a blind player what a sighted one gets from the screen: which exits
// this room has, where the nearest one is, and which button opens it.
//
// The layer only READS guest memory. Nothing here writes to the game or steers
// it; announcements are spoken through the accessibility sink.

#pragma once

#include <cstdint>
#include <string>

#include "touch/emerald_guest.h"

namespace emerald::touch { struct SceneState; }

namespace emerald::accessibility {

struct WarpInfo {
    int x = 0, y = 0;
    int elevation = 0;
    int warpId = 0;
    int mapGroup = -1, mapNum = -1;
    bool stair = false;      // differs in elevation from the player: a floor change
    bool goesUp = false;     // stair that leads to a higher elevation
};

// What sits on the tile the player is looking at. The field layer announces
// this only when the player looks at it (turns to face it, or walks up to it
// facing it), so nothing is described behind the player's back.
enum LookKind {
    LookNone = 0,
    LookDoor,
    LookStairsUp,
    LookStairsDown,
    LookPerson,
    LookItem,
    LookObject,
    LookReadable,   // a background event: a sign, the wall clock, the TV
};

struct NavState {
    bool ok = false;
    int x = 0, y = 0;        // player tile
    int facing = 0;          // 1..4 = south, north, west, east (pokeemerald order)
    int elevation = 0;
    int mapGroup = -1, mapNum = -1;

    int warpCount = 0;
    WarpInfo warps[8];

    int nearestWarp = -1;    // index into warps, -1 when the map has none in range
    int warpDx = 0, warpDy = 0, warpDist = 0;

    // Closest non-player object event standing on the player's tile or next to
    // it (people, item balls, signs and machines that are objects).
    int npcDist = 0;         // 0 when nothing is adjacent
    int npcDx = 0, npcDy = 0;
    int npcGraphics = 0;
    bool npcIsItem = false;
    bool npcIsTrainer = false;

    // The tile directly in front of the player (facing probe).
    int lookX = 0, lookY = 0;
    int lookKind = LookNone;
    int lookGraphics = 0;
    bool lookIsTrainer = false;   // LookPerson that will challenge the player
};

// Read the player's tile and this map's warp events. Side-effect free.
bool read_nav(const emerald::guest::Mem& m, NavState* out);

// "north" / "north-east" / ... for a tile delta (screen axes: +y is south).
const char* compass(int dx, int dy);

// Facing (1..4 = south, north, west, east) to a tile step.
void facing_step(int facing, int* dx, int* dy);

// Full state as one JSON object (TCP `emerald_a11y_nav`, and the playtest bot).
std::string nav_json(const NavState& n);

// Per-frame announcements: map changes, approaching a door or stairs, and
// standing next to a person, item or interactive object.
void nav_frame(const emerald::touch::SceneState& scene, const emerald::guest::Mem& m);

// Forget what has been announced (called when the layer is reset/toggled).
void nav_reset();

// Ask to be told when the player reaches a tile (navigation targets: route
// steps, scripted tests, a player-set bookmark). Clears itself on arrival.
void nav_set_target(int mapGroup, int mapNum, int x, int y);
void nav_clear_target();

}  // namespace emerald::accessibility

// emerald_terrain.h — what a metatile does to movement, and what to say about
// it.
//
// Split out of emerald_puzzle.cpp so the mapping can be unit-tested with no
// guest attached: a behaviour byte goes in, a terrain class, a jump vector and
// a spoken sentence come out. Nothing here reads memory or speaks.

#pragma once

namespace emerald::accessibility {

enum class Terrain : int {
    Plain = 0,
    Ice,              // MB_ICE
    ThinIce,          // MB_THIN_ICE: breaks under you
    CrackedIce,       // MB_CRACKED_ICE
    SlideEast,        // MB_SLIDE_*: stepping on it slides you that way
    SlideWest,
    SlideNorth,
    SlideSouth,
    CrackedFloor,     // MB_CRACKED_FLOOR (Sky Pillar)
    CrackedFloorHole, // MB_CRACKED_FLOOR_HOLE: already open
    WarpPanel,        // Mossdeep gym warp panels, Trick House floors
    Pit,              // MB_LAVARIDGE_GYM_1F_WARP: the floor gives way
    Vent,             // MB_LAVARIDGE_GYM_B1F_WARP: steam throws you back up
    // MB_JUMP_*: one-way ledges. They carry collision, so a collision-only
    // reading calls them walls, but the player jumps them from the opposite
    // side. The direction in the name is the way you jump, which is the one
    // fact a player without sight cannot otherwise get: Lavaridge's basement
    // box is entered over a ledge and there is no other door.
    LedgeEast,
    LedgeWest,
    LedgeNorth,
    LedgeSouth,
    LedgeNorthEast,
    LedgeNorthWest,
    LedgeSouthEast,
    LedgeSouthWest,
    ArrowWarp,        // directional warp arrows
    GymDoor,          // MB_PETALBURG_GYM_DOOR
    SealedDoor,       // closed Sootopolis / Sky Pillar / Trick House puzzle door
    MuddySlope,       // Mach Bike
    BumpySlope,
    Rail,
    DeepWater,
    Waterfall,
    Current,
    TrashCan,
    Sand,
    Ash,
    HotSprings,
    Count
};

// A behaviour byte (MB_*) to the terrain class the puzzle layer reasons about.
Terrain terrain_of_behavior(int behavior);

// "pit", "ledge_south", ... for diagnostics and the status payload.
const char* terrain_name(Terrain t);

// One sentence, spoken when the tile becomes the one you face or stand on.
const char* terrain_speech(Terrain t);

// The eight MB_JUMP_* classes. They carry collision like a wall but are crossed
// by jumping, so nothing that only reads collision can tell them apart.
bool is_ledge(Terrain t);

// The tile delta a ledge throws you by, in map tiles: +y is south. (0, 0) for
// every terrain that is not a ledge.
void ledge_jump(Terrain t, int* jx, int* jy);

}  // namespace emerald::accessibility

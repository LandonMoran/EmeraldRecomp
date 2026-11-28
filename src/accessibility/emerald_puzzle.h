// emerald_puzzle.h — reusable puzzle awareness for the Emerald accessibility
// layer.
//
// Emerald's gyms and dungeons are not menus: their affordances are terrain
// (ice, cracked floors, warp panels) and geometry that changes while you stand
// in the room (Mauville's barriers, Fortree's turnstiles, Petalburgh's doors,
// Mossdeep's statues). A sighted player reads all of that off the screen. This
// module gives the voice the same three facts, from the game's own data:
//
//   1. What the tile you face or stand on is, from the metatile behavior byte
//      the engine itself uses for movement (MapGridGetMetatileBehaviorAt).
//      Behaviors are the game's constants, not per-gym guesses, so every map
//      gets the same reading for free.
//   2. When the room's walkable geometry changes, by diffing the packed map
//      grid the engine renders from (gBackupMapLayout, which the map scripts
//      rewrite with `setmetatile`). That is what makes a switch press audible
//      without knowing which switch it was.
//   3. When the game moves the player without input — an ice slide, a warp
//      panel, a fall — so a forced move cannot silently relocate the player.
//
// Everything here READS guest memory. Nothing is written and no guest function
// is called. Announcements are deliberately sparse: ordinary ground, ordinary
// objects and ordinary walking stay silent.

#pragma once

#include <cstdint>
#include <string>

#include "touch/emerald_guest.h"

namespace emerald::touch { struct SceneState; }

namespace emerald::accessibility {

// Terrain classes that change how the player can move. Each value maps from the
// engine's metatile behavior byte (include/constants/metatile_behaviors.h),
// never from a map id.
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

const char* terrain_name(Terrain t);

// One sentence, spoken when the tile becomes the one you face or stand on.
const char* terrain_speech(Terrain t);

struct PuzzleState {
    bool ok = false;
    int mapGroup = -1, mapNum = -1;
    int x = 0, y = 0;               // player map tile (SaveBlock1.pos)
    Terrain underfoot = Terrain::Plain;
    Terrain facing = Terrain::Plain;
    int coordEventCount = 0;        // trigger tiles on this map
    int triggerDist = -1;           // nearest one, Manhattan (-1 = none)
    int triggerDx = 0, triggerDy = 0;
    bool onTrigger = false;         // standing on a trigger tile
    bool triggerRaised = false;     // the nearest trigger is impassable (a raised
                                    // switch; a flat one can be stepped on)
    int changedBlocks = 0;          // geometry diff on the latest settled frame
    int openedBlocks = 0, closedBlocks = 0;
    int totalChanges = 0;           // how many times this map's room has changed
    int lastMoveTiles = 0;          // last forced (input-free) move
    bool puzzleMap = false;         // this map's geometry has changed once

    // Passability of the four neighbouring tiles. This is the same fact the
    // layer speaks as "Blocked east." when a step is refused, so a harness can
    // route a maze without guessing and without reading anything the player
    // cannot hear.
    bool openN = false, openE = false, openS = false, openW = false;

    // Neighbouring tiles that are ledges: bit 0 north, 1 east, 2 south, 3 west.
    // A ledge is blocked to walk into but crossable by jumping, so it is the
    // one blocked direction the read key must not call a wall.
    int ledgeMask = 0;

    // The grid those answers came from, and the raw blocks, for diagnosing a
    // read that disagrees with the game.
    int gridWidth = 0, gridHeight = 0;
    unsigned gridBlocks = 0;
    unsigned blockN = 0, blockE = 0, blockS = 0, blockW = 0;
};

// Read terrain, triggers and the local geometry snapshot. Side-effect free.
bool read_puzzle(const emerald::guest::Mem& m, PuzzleState* out);

// Full state as one JSON object (dev diagnostics; not spoken).
std::string puzzle_json(const PuzzleState& p);

// One sentence for the read key, for the puzzles that cannot be understood a
// step at a time: where the nearest trigger tile is, whether it is raised or
// flat, and which of the four ways out of this tile are open. Empty when this
// map has no puzzle, so an ordinary field reads exactly as it always did.
//
// Mauville Gym is the case that asked for it: four floor switches, only one of
// them flat at a time, and a beam maze that redraws when the map reloads. Being
// told "Plate two steps west, raised. Open north and south." is the difference
// between exploring and guessing.
std::string puzzle_context_speech(const PuzzleState& p);

// Per-frame announcements. `host_keys` is the pad's own active-low key mask for
// this frame, used only to tell a player-driven walk from a forced move.
void puzzle_frame(const emerald::touch::SceneState& scene, const emerald::guest::Mem& m,
                  std::uint16_t host_keys);

void puzzle_reset();

}  // namespace emerald::accessibility

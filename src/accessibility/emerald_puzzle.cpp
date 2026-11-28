// emerald_puzzle.cpp — see emerald_puzzle.h.
//
// Addresses and struct offsets come from the pinned pokemerald revision the
// rest of the layer uses (src/touch/emerald_guest.h):
//
//   gMapHeader             MapHeader    @0x02037318
//     +0x00                const struct MapLayout *mapLayout
//     +0x04                const struct MapEvents *events
//   struct MapLayout       width s32 @0, height s32 @4, border * @8,
//                          map * @0x0C, primaryTileset * @0x10,
//                          secondaryTileset * @0x14
//   struct Tileset         ... metatileAttributes * @0x10
//   struct MapEvents       coordEventCount u8 @2, coordEvents * @0x0C
//   struct CoordEvent      s16 x, s16 y, u8 elevation, (pad), u16 trigger,
//                          u16 index, const u8 *script          (16 bytes)
//   gBackupMapLayout       s32 width @+0, s32 height @+4, u16 *map @+8
//                          (@0x03005DC0) — the live, script-editable grid.
//   Map grid block         bits 0-9 metatile, 10-11 collision, 12-15 elevation
//   Metatile attribute     bits 0-7 behavior, 12-15 layer type
//
// The grid comes from the header's live layout, with the backup copy taking
// over whenever it describes the same map. Both halves matter: the backup is
// what makes a switch press visible (map scripts change the room with
// `setmetatile`, which writes that copy), and the header is what keeps the
// report honest on a map nothing has rewritten yet, where the backup still
// holds the previous room and every tile of this one looks walkable.

#include "emerald_puzzle.h"

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

#include "emerald_a11y.h"   // speak_now
#include "emerald_nav.h"    // compass, facing_step
#include "touch/emerald_guest.h"
#include "touch/emerald_scene.h"   // SceneKind / SceneState
#include "touch/emerald_touch.h"   // core().synth.idle()

namespace emerald::accessibility {
namespace {

namespace addr = emerald::guest::addr;
using emerald::guest::Mem;

constexpr std::uint32_t kBackupMapLayout = 0x03005DC0;
constexpr std::uint32_t kMapLayoutPtr = 0x00;
constexpr std::uint32_t kMapEventsPtr = 0x04;
constexpr std::uint32_t kMapEventsCoordCount = 0x02;
constexpr std::uint32_t kMapEventsCoordEvents = 0x0C;

constexpr std::uint32_t kLayoutMap = 0x0C;
constexpr std::uint32_t kLayoutPrimary = 0x10;
constexpr std::uint32_t kLayoutSecondary = 0x14;
constexpr std::uint32_t kTilesetAttributes = 0x10;
constexpr int kPrimaryMetatiles = 512;

constexpr std::uint32_t kCoordEventSize = 16;
constexpr int kCoordEventMax = 64;

constexpr int kMapOffset = 7;          // object events are stored +7
constexpr int kMapOffsetW = kMapOffset * 2 + 1;   // gBackupMapLayout padding
constexpr int kMapOffsetH = kMapOffset * 2;
constexpr int kScanRadius = 8;         // geometry window: 17 x 17 tiles
constexpr int kSettleFrames = 20;      // frames of standing still before a diff

// ── Metatile behaviors (include/constants/metatile_behaviors.h) ───────────
constexpr int kMbNormal = 0x00;
constexpr int kMbDeepSand = 0x06;
constexpr int kMbBattlePyramidWarp = 0x0D;
constexpr int kMbMossdeepGymWarp = 0x0E;
constexpr int kMbInteriorDeepWater = 0x11;
constexpr int kMbDeepWater = 0x12;
constexpr int kMbWaterfall = 0x13;
constexpr int kMbSootopolisDeepWater = 0x14;
constexpr int kMbOceanWater = 0x15;
constexpr int kMbIce = 0x20;
constexpr int kMbSand = 0x21;
constexpr int kMbAshGrass = 0x24;
constexpr int kMbThinIce = 0x26;
constexpr int kMbCrackedIce = 0x27;
constexpr int kMbHotSprings = 0x28;
constexpr int kMbLavaridgeB1FWarp = 0x29;
constexpr int kMbSlideEast = 0x44;
constexpr int kMbSlideWest = 0x45;
constexpr int kMbSlideNorth = 0x46;
constexpr int kMbSlideSouth = 0x47;
constexpr int kMbTrickHousePuzzle8Floor = 0x48;
// MB_JUMP_EAST..MB_JUMP_SOUTHWEST are 0x38..0x3F, in the header's order.
constexpr int kMbJumpEast = 0x38;
constexpr int kMbJumpWest = 0x39;
constexpr int kMbJumpNorth = 0x3A;
constexpr int kMbJumpSouth = 0x3B;
constexpr int kMbJumpNorthEast = 0x3C;
constexpr int kMbJumpNorthWest = 0x3D;
constexpr int kMbJumpSouthEast = 0x3E;
constexpr int kMbJumpSouthWest = 0x3F;
constexpr int kMbEastCurrent = 0x50;
constexpr int kMbWestCurrent = 0x51;
constexpr int kMbNorthCurrent = 0x52;
constexpr int kMbSouthCurrent = 0x53;
constexpr int kMbEastArrowWarp = 0x62;
constexpr int kMbWestArrowWarp = 0x63;
constexpr int kMbNorthArrowWarp = 0x64;
constexpr int kMbSouthArrowWarp = 0x65;
constexpr int kMbCrackedFloorHole = 0x66;
constexpr int kMbAquaHideoutWarp = 0x67;
constexpr int kMbLavaridge1FWarp = 0x68;
constexpr int kMbWaterSouthArrowWarp = 0x6D;
constexpr int kMbDeepSouthWarp = 0x6E;
constexpr int kMbClosedSootopolisDoor = 0x8B;
constexpr int kMbTrickHousePuzzleDoor = 0x8C;
constexpr int kMbPetalburgGymDoor = 0x8D;
constexpr int kMbMuddySlope = 0xD0;
constexpr int kMbBumpySlope = 0xD1;
constexpr int kMbCrackedFloor = 0xD2;
constexpr int kMbIsolatedVerticalRail = 0xD3;
constexpr int kMbIsolatedHorizontalRail = 0xD4;
constexpr int kMbVerticalRail = 0xD5;
constexpr int kMbHorizontalRail = 0xD6;
constexpr int kMbTrashCan = 0xE4;
constexpr int kMbSkyPillarClosedDoor = 0xEA;

// ── Grid ─────────────────────────────────────────────────────────────────

struct Grid {
    bool ok = false;
    int width = 0, height = 0;
    std::uint32_t blocks = 0;   // EWRAM pointer to the u16 grid
    // The engine's own working copy (gBackupMapLayout) pads the map by
    // MAP_OFFSET on the west/north, so a tile's index is (x + off_x, y + off_y)
    // in a grid MAP_OFFSET_W/MAP_OFFSET_H wider and taller than the map.
    int off_x = 0, off_y = 0;
};

Grid grid_of(const Mem& m) {
    Grid g;
    // The map the player is actually on comes from the header. The backup copy
    // is left over from whatever map was loaded before until a script rewrites
    // the room, so reading it first reported another map's size and made every
    // tile look walkable.
    const std::uint32_t layout = m.u32(addr::gMapHeader + kMapLayoutPtr);
    if (layout >= 0x08000000u) {
        g.width = static_cast<int>(m.u32(layout));
        g.height = static_cast<int>(m.u32(layout + 4));
        g.blocks = m.u32(layout + 12);   // MapLayout.map, after border
    }
    // setmetatile (gym beams, turnstiles, statues) writes into the backup copy,
    // so take its block pointer once it describes the same map. The header's
    // layout usually still points at the ROM original, which never sees those
    // writes.
    //
    // The backup is not the same shape as the map. The engine copies the map
    // into a padded buffer (MAP_OFFSET tiles on the west and north, and one
    // extra column east) so a screenful near the edge still reads sensible
    // neighbours, and it stores width + MAP_OFFSET_W by height + MAP_OFFSET_H.
    // Comparing it against the unpadded size rejected every map, fell back to
    // the ROM copy, and made the beams in Mauville Gym look like they never
    // moved — the plates fired and nothing was spoken.
    const int backup_w = static_cast<int>(m.u32(kBackupMapLayout));
    const int backup_h = static_cast<int>(m.u32(kBackupMapLayout + 4));
    const std::uint32_t backup_blocks = m.u32(kBackupMapLayout + 8);
    if (backup_w == g.width + kMapOffsetW && backup_h == g.height + kMapOffsetH &&
        backup_blocks >= 0x02000000u && backup_blocks < 0x02040000u) {
        g.blocks = backup_blocks;
        g.width = backup_w;
        g.height = backup_h;
        g.off_x = kMapOffset;
        g.off_y = kMapOffset;
    }
    // Map data can live in EWRAM (a map a script has rewritten) or in ROM (the
    // original; the gym reads straight out of ROM because nothing has written
    // to it yet). Requiring EWRAM here made every tile on a ROM-backed map look
    // walkable, which is exactly the map a beam maze is built on.
    const bool readable_map = (g.blocks >= 0x02000000u && g.blocks < 0x02040000u) ||
                              (g.blocks >= 0x08000000u && g.blocks < 0x0A000000u);
    g.ok = g.width > 0 && g.width <= 512 && g.height > 0 && g.height <= 512 &&
           readable_map;
    return g;
}

std::uint16_t block_at(const Mem& m, const Grid& g, int x, int y) {
    if (!g.ok || x < 0 || y < 0) return 0x03FF;
    const int gx = x + g.off_x, gy = y + g.off_y;
    if (gx < 0 || gy < 0 || gx >= g.width || gy >= g.height) return 0x03FF;
    return m.u16(g.blocks + static_cast<std::uint32_t>((gy * g.width + gx) * 2));
}

bool passable_block(std::uint16_t block) {
    return (block & 0x0C00) == 0;
}

// Metatile behavior of a map tile, through the map's own tilesets. Returns
// MB_NORMAL when the layout is not readable (before the first map load).
int behavior_at(const Mem& m, int x, int y) {
    const Grid g = grid_of(m);
    const std::uint16_t block = block_at(m, g, x, y);
    if (block == 0x03FF) return kMbNormal;      // MAPGRID_UNDEFINED
    const int metatile = block & 0x03FF;
    const std::uint32_t layout = m.u32(addr::gMapHeader + kMapLayoutPtr);
    if (layout < 0x08000000u) return kMbNormal;
    const std::uint32_t tileset = m.u32(layout + (metatile < kPrimaryMetatiles
                                                      ? kLayoutPrimary
                                                      : kLayoutSecondary));
    if (tileset < 0x08000000u) return kMbNormal;
    const std::uint32_t attributes = m.u32(tileset + kTilesetAttributes);
    if (attributes < 0x08000000u) return kMbNormal;
    const int index = metatile < kPrimaryMetatiles ? metatile
                                                   : metatile - kPrimaryMetatiles;
    return m.u16(attributes + static_cast<std::uint32_t>(index * 2)) & 0xFF;
}

bool is_ledge(Terrain t) {
    return t == Terrain::LedgeEast || t == Terrain::LedgeWest ||
           t == Terrain::LedgeNorth || t == Terrain::LedgeSouth ||
           t == Terrain::LedgeNorthEast || t == Terrain::LedgeNorthWest ||
           t == Terrain::LedgeSouthEast || t == Terrain::LedgeSouthWest;
}

// The way a ledge throws you. Cardinally simple; the diagonals are the same
// step plus a corner.
void ledge_jump(Terrain t, int* jx, int* jy) {
    *jx = *jy = 0;
    switch (t) {
        case Terrain::LedgeEast: *jx = 1; break;
        case Terrain::LedgeWest: *jx = -1; break;
        case Terrain::LedgeNorth: *jy = -1; break;
        case Terrain::LedgeSouth: *jy = 1; break;
        case Terrain::LedgeNorthEast: *jx = 1; *jy = -1; break;
        case Terrain::LedgeNorthWest: *jx = -1; *jy = -1; break;
        case Terrain::LedgeSouthEast: *jx = 1; *jy = 1; break;
        case Terrain::LedgeSouthWest: *jx = -1; *jy = 1; break;
        default: break;
    }
}

Terrain terrain_of_behavior(int behavior) {
    switch (behavior) {
        case kMbIce: return Terrain::Ice;
        case kMbThinIce: return Terrain::ThinIce;
        case kMbCrackedIce: return Terrain::CrackedIce;
        case kMbSlideEast: return Terrain::SlideEast;
        case kMbSlideWest: return Terrain::SlideWest;
        case kMbSlideNorth: return Terrain::SlideNorth;
        case kMbSlideSouth: return Terrain::SlideSouth;
        case kMbCrackedFloor: return Terrain::CrackedFloor;
        case kMbCrackedFloorHole: return Terrain::CrackedFloorHole;
        // Lavaridge's two are not panels you choose to use: one drops you to
        // the basement and one throws you back up, and the gym is a maze of
        // them. They keep their own names so the cue can say which is which.
        case kMbLavaridge1FWarp: return Terrain::Pit;
        case kMbLavaridgeB1FWarp: return Terrain::Vent;
        // Ledges block movement like a wall but are crossable from the far
        // side, so they get their own classes and say which way they jump.
        case kMbJumpEast: return Terrain::LedgeEast;
        case kMbJumpWest: return Terrain::LedgeWest;
        case kMbJumpNorth: return Terrain::LedgeNorth;
        case kMbJumpSouth: return Terrain::LedgeSouth;
        case kMbJumpNorthEast: return Terrain::LedgeNorthEast;
        case kMbJumpNorthWest: return Terrain::LedgeNorthWest;
        case kMbJumpSouthEast: return Terrain::LedgeSouthEast;
        case kMbJumpSouthWest: return Terrain::LedgeSouthWest;
        case kMbMossdeepGymWarp:
        case kMbAquaHideoutWarp:
        case kMbBattlePyramidWarp:
        case kMbTrickHousePuzzle8Floor:
            return Terrain::WarpPanel;
        case kMbEastArrowWarp:
        case kMbWestArrowWarp:
        case kMbNorthArrowWarp:
        case kMbSouthArrowWarp:
        case kMbWaterSouthArrowWarp:
        case kMbDeepSouthWarp:
            return Terrain::ArrowWarp;
        case kMbPetalburgGymDoor: return Terrain::GymDoor;
        case kMbClosedSootopolisDoor:
        case kMbTrickHousePuzzleDoor:
        case kMbSkyPillarClosedDoor:
            return Terrain::SealedDoor;
        case kMbMuddySlope: return Terrain::MuddySlope;
        case kMbBumpySlope: return Terrain::BumpySlope;
        case kMbIsolatedVerticalRail:
        case kMbIsolatedHorizontalRail:
        case kMbVerticalRail:
        case kMbHorizontalRail: return Terrain::Rail;
        case kMbInteriorDeepWater:
        case kMbDeepWater:
        case kMbSootopolisDeepWater:
        case kMbOceanWater: return Terrain::DeepWater;
        case kMbWaterfall: return Terrain::Waterfall;
        case kMbEastCurrent:
        case kMbWestCurrent:
        case kMbNorthCurrent:
        case kMbSouthCurrent: return Terrain::Current;
        case kMbTrashCan: return Terrain::TrashCan;
        case kMbSand:
        case kMbDeepSand: return Terrain::Sand;
        case kMbAshGrass: return Terrain::Ash;
        case kMbHotSprings: return Terrain::HotSprings;
        default: return Terrain::Plain;
    }
}

// ── Player ───────────────────────────────────────────────────────────────

struct Player {
    bool ok = false;
    int mapGroup = -1, mapNum = -1;
    int x = 0, y = 0;        // map tile (SaveBlock1.pos: what the map grid uses)
    int facing = 0;          // 1 south, 2 north, 3 west, 4 east
    int elevation = 0;
};

Player read_player(const Mem& m) {
    Player p;
    const std::uint32_t sb1 = m.u32(addr::gSaveBlock1Ptr);
    if (sb1 < 0x02000000u || sb1 >= 0x02040000u) return p;
    p.x = m.s16(sb1 + 0x00);
    p.y = m.s16(sb1 + 0x02);
    p.mapGroup = m.u8(sb1 + 0x04);
    p.mapNum = m.u8(sb1 + 0x05);
    const int id = m.u8(addr::gPlayerAvatar + 5);
    if (id < 16) {
        const std::uint32_t o = addr::gObjectEvents + static_cast<std::uint32_t>(id) * 0x24;
        p.facing = m.u8(o + 0x18) & 0x0F;
        p.elevation = m.u8(o + 0x0B) & 0x0F;
    }
    p.ok = true;
    return p;
}

// ── Triggers (coord events) ──────────────────────────────────────────────

struct Trigger {
    int x = 0, y = 0, elevation = 0;
};

int read_triggers(const Mem& m, Trigger* out, int max) {
    const std::uint32_t events = m.u32(addr::gMapHeader + kMapEventsPtr);
    if (events < 0x08000000u) return 0;
    const int count = m.u8(events + kMapEventsCoordCount);
    const std::uint32_t table = m.u32(events + kMapEventsCoordEvents);
    if (table < 0x08000000u) return 0;
    int n = 0;
    for (int i = 0; i < count && i < kCoordEventMax && n < max; ++i) {
        const std::uint32_t c = table + static_cast<std::uint32_t>(i) * kCoordEventSize;
        Trigger t;
        t.x = m.s16(c);
        t.y = m.s16(c + 2);
        t.elevation = m.u8(c + 4);
        out[n++] = t;
    }
    return n;
}

// ── Announcement state ───────────────────────────────────────────────────

struct Tracker {
    int frame = 0;
    bool have_map = false;
    int mapGroup = -1, mapNum = -1;

    bool have_pos = false;
    int last_x = 0, last_y = 0;
    int still = 0;                 // consecutive frames with no movement

    bool have_snapshot = false;
    int snap_x = 0, snap_y = 0;
    std::vector<std::uint16_t> snapshot;

    int announced_underfoot = -1;   // Terrain value last spoken for the tile
    int announced_underfoot_x = -999, announced_underfoot_y = -999;
    int announced_facing = -1;
    int announced_facing_x = -999, announced_facing_y = -999;

    int forced_tiles = 0;
    int forced_dx = 0, forced_dy = 0;
    int forced_idle = 0;

    bool puzzle_map = false;        // geometry has changed on this map
    int trigger_notice_x = -999, trigger_notice_y = -999;
    // Latest nearest-trigger reading, so the read key can describe it.
    int trigger_dist = -1, trigger_dx = 0, trigger_dy = 0;
    bool trigger_on = false, trigger_raised = false;
    int underfoot_notice_x = -999, underfoot_notice_y = -999;
    int hazard_x = -999, hazard_y = -999;   // last pit/vent announced
    int ledge_x = -999, ledge_y = -999;     // last ledge announced

    int last_opened = 0, last_closed = 0, last_changed = 0;
    int total_changes = 0;   // room changes seen on this map (diagnostics)
    int last_move_tiles = 0;

    // Refused steps: a press that ends without the player leaving the tile.
    bool press_active = false;
    int press_x = 0, press_y = 0;      // the direction that was pressed
    bool press_moved = false;
    int block_dx = 0, block_dy = 0;    // the last refused direction, spoken
    int block_x = -999, block_y = -999;
    int block_value = -1;
};
Tracker g_t;

void snapshot_window(const Mem& m, const Player& p) {
    g_t.snapshot.clear();
    const Grid g = grid_of(m);
    if (!g.ok) {
        g_t.have_snapshot = false;
        return;
    }
    g_t.snapshot.reserve((2 * kScanRadius + 1) * (2 * kScanRadius + 1));
    for (int dy = -kScanRadius; dy <= kScanRadius; ++dy)
        for (int dx = -kScanRadius; dx <= kScanRadius; ++dx)
            g_t.snapshot.push_back(block_at(m, g, p.x + dx, p.y + dy));
    g_t.snap_x = p.x;
    g_t.snap_y = p.y;
    g_t.have_snapshot = true;
}

void reset_map_state() {
    g_t.have_snapshot = false;
    g_t.snapshot.clear();
    g_t.announced_underfoot = -1;
    g_t.announced_facing = -1;
    g_t.announced_underfoot_x = g_t.announced_underfoot_y = -999;
    g_t.announced_facing_x = g_t.announced_facing_y = -999;
    g_t.forced_tiles = 0;
    g_t.forced_dx = g_t.forced_dy = 0;
    g_t.forced_idle = 0;
    g_t.puzzle_map = false;
    g_t.trigger_notice_x = g_t.trigger_notice_y = -999;
    g_t.underfoot_notice_x = g_t.underfoot_notice_y = -999;
    g_t.last_opened = g_t.last_closed = g_t.last_changed = 0;
    g_t.last_move_tiles = 0;
    g_t.press_active = false;
    g_t.press_moved = false;
    g_t.block_dx = g_t.block_dy = 0;
    g_t.block_x = g_t.block_y = -999;
    g_t.block_value = -1;
}

}  // namespace

const char* terrain_name(Terrain t) {
    switch (t) {
        case Terrain::Ice: return "ice";
        case Terrain::ThinIce: return "thin_ice";
        case Terrain::CrackedIce: return "cracked_ice";
        case Terrain::SlideEast: return "slide_east";
        case Terrain::SlideWest: return "slide_west";
        case Terrain::SlideNorth: return "slide_north";
        case Terrain::SlideSouth: return "slide_south";
        case Terrain::CrackedFloor: return "cracked_floor";
        case Terrain::CrackedFloorHole: return "cracked_floor_hole";
        case Terrain::WarpPanel: return "warp_panel";
        case Terrain::Pit: return "pit";
        case Terrain::Vent: return "vent";
        case Terrain::LedgeEast: return "ledge_east";
        case Terrain::LedgeWest: return "ledge_west";
        case Terrain::LedgeNorth: return "ledge_north";
        case Terrain::LedgeSouth: return "ledge_south";
        case Terrain::LedgeNorthEast: return "ledge_north_east";
        case Terrain::LedgeNorthWest: return "ledge_north_west";
        case Terrain::LedgeSouthEast: return "ledge_south_east";
        case Terrain::LedgeSouthWest: return "ledge_south_west";
        case Terrain::ArrowWarp: return "arrow_warp";
        case Terrain::GymDoor: return "gym_door";
        case Terrain::SealedDoor: return "sealed_door";
        case Terrain::MuddySlope: return "muddy_slope";
        case Terrain::BumpySlope: return "bumpy_slope";
        case Terrain::Rail: return "rail";
        case Terrain::DeepWater: return "deep_water";
        case Terrain::Waterfall: return "waterfall";
        case Terrain::Current: return "current";
        case Terrain::TrashCan: return "trash_can";
        case Terrain::Sand: return "sand";
        case Terrain::Ash: return "ash";
        case Terrain::HotSprings: return "hot_springs";
        default: return "plain";
    }
}

const char* terrain_speech(Terrain t) {
    switch (t) {
        // Ice does the moving for you; saying so before you step is the whole
        // difference between a puzzle and a mystery.
        case Terrain::Ice: return "Ice. You will slide until something stops you.";
        case Terrain::ThinIce: return "Thin ice. It may break under you.";
        case Terrain::CrackedIce: return "Cracked ice.";
        case Terrain::SlideEast: return "A slippery slope. It will slide you east.";
        case Terrain::SlideWest: return "A slippery slope. It will slide you west.";
        case Terrain::SlideNorth: return "A slippery slope. It will slide you north.";
        case Terrain::SlideSouth: return "A slippery slope. It will slide you south.";
        case Terrain::CrackedFloor:
            return "Cracked floor. It will break if you step on it.";
        case Terrain::CrackedFloorHole: return "A hole in the floor.";
        case Terrain::WarpPanel: return "A warp panel. Step on it.";
        case Terrain::Pit:
            return "A pit. Step on it and the floor drops you to the basement.";
        case Terrain::Vent:
            return "A steam vent. Step on it and it throws you back up.";
        // The direction is the direction you jump, which is also the side you
        // have to stand on. Saying "Blocked" here is what made Lavaridge's only
        // door to the basement box invisible.
        case Terrain::LedgeEast: return "A ledge. Jump east to cross it.";
        case Terrain::LedgeWest: return "A ledge. Jump west to cross it.";
        case Terrain::LedgeNorth: return "A ledge. Jump north to cross it.";
        case Terrain::LedgeSouth: return "A ledge. Jump south to cross it.";
        case Terrain::LedgeNorthEast: return "A ledge. Jump north-east to cross it.";
        case Terrain::LedgeNorthWest: return "A ledge. Jump north-west to cross it.";
        case Terrain::LedgeSouthEast: return "A ledge. Jump south-east to cross it.";
        case Terrain::LedgeSouthWest: return "A ledge. Jump south-west to cross it.";
        case Terrain::ArrowWarp: return "A warp arrow. Step on it.";
        case Terrain::GymDoor: return "A gym door.";
        case Terrain::SealedDoor: return "A door that is shut.";
        case Terrain::MuddySlope: return "A muddy slope. You need the Mach Bike.";
        case Terrain::BumpySlope: return "A bumpy slope. You need the Mach Bike.";
        case Terrain::Rail: return "A rail. The Mach Bike rides it.";
        case Terrain::DeepWater: return "Deep water. You need Surf.";
        case Terrain::Waterfall: return "A waterfall. You need Waterfall.";
        case Terrain::Current: return "A strong current. It will carry you.";
        case Terrain::TrashCan: return "A rubbish bin.";
        case Terrain::Sand: return "Soft sand. You will walk slowly.";
        case Terrain::Ash: return "Deep ash. You will walk slowly.";
        case Terrain::HotSprings: return "Hot spring water.";
        default: return "";
    }
}

bool read_puzzle(const Mem& m, PuzzleState* out) {
    if (!out) return false;
    PuzzleState& p = *out;
    p = PuzzleState{};
    const Player pl = read_player(m);
    if (!pl.ok) return false;
    p.ok = true;
    p.mapGroup = pl.mapGroup;
    p.mapNum = pl.mapNum;
    p.x = pl.x;
    p.y = pl.y;
    p.underfoot = terrain_of_behavior(behavior_at(m, pl.x, pl.y));
    int fx = 0, fy = 0;
    facing_step(pl.facing, &fx, &fy);
    p.facing = terrain_of_behavior(behavior_at(m, pl.x + fx, pl.y + fy));

    Trigger triggers[kCoordEventMax];
    const int count = read_triggers(m, triggers, kCoordEventMax);
    p.coordEventCount = count;
    int best = 1 << 30;
    for (int i = 0; i < count; ++i) {
        // The engine fires a coord event when its elevation equals the player's
        // or is ELEVATION_TRANSITION (3), which means "any elevation" — the
        // value every floor-plate switch in a gym uses. Comparing only against
        // the player's elevation hid exactly the triggers a puzzle needs.
        if (triggers[i].elevation != pl.elevation && triggers[i].elevation != 3) continue;
        const int dx = triggers[i].x - pl.x;
        const int dy = triggers[i].y - pl.y;
        const int d = std::abs(dx) + std::abs(dy);
        if (d < best) {
            best = d;
            p.triggerDist = d;
            p.triggerDx = dx;
            p.triggerDy = dy;
        }
    }
    p.onTrigger = best == 0;

    const Grid grid = grid_of(m);
    p.gridWidth = grid.width;
    p.gridHeight = grid.height;
    p.gridBlocks = grid.ok ? grid.blocks : 0;
    if (grid.ok && p.triggerDist > 0) {
        // A raised switch is solid and a pressed one is flat, so passability is
        // exactly the state a sighted player sees on the pillar.
        p.triggerRaised = !passable_block(static_cast<std::uint16_t>(
            block_at(m, grid, pl.x + p.triggerDx, pl.y + p.triggerDy)));
    }
    if (grid.ok) {
        p.blockN = block_at(m, grid, pl.x, pl.y - 1);
        p.blockE = block_at(m, grid, pl.x + 1, pl.y);
        p.blockS = block_at(m, grid, pl.x, pl.y + 1);
        p.blockW = block_at(m, grid, pl.x - 1, pl.y);
        // MAPGRID_UNDEFINED (0x03FF) is what the grid returns past the map edge,
        // and its collision bits are zero, so a naive passability test calls the
        // wall of the world "open" while the game refuses the step. The read key
        // has to agree with the refusal it sits next to.
        auto open_way = [](unsigned b) {
            return b != 0x03FFu && passable_block(static_cast<std::uint16_t>(b));
        };
        p.openN = open_way(p.blockN);
        p.openE = open_way(p.blockE);
        p.openS = open_way(p.blockS);
        p.openW = open_way(p.blockW);
        const int nx[4] = {pl.x, pl.x + 1, pl.x, pl.x - 1};
        const int ny[4] = {pl.y - 1, pl.y, pl.y + 1, pl.y};
        for (int i = 0; i < 4; ++i) {
            if (is_ledge(terrain_of_behavior(behavior_at(m, nx[i], ny[i]))))
                p.ledgeMask |= 1 << i;
        }
    }
    p.lastMoveTiles = g_t.last_move_tiles;
    p.openedBlocks = g_t.last_opened;
    p.closedBlocks = g_t.last_closed;
    p.changedBlocks = g_t.last_changed;
    p.totalChanges = g_t.total_changes;
    p.puzzleMap = g_t.puzzle_map;
    return true;
}

std::string puzzle_json(const PuzzleState& p) {
    char head[768];
    std::snprintf(head, sizeof(head),
                  "{\"ok\":%s,\"map\":[%d,%d],\"x\":%d,\"y\":%d,"
                  "\"underfoot\":\"%s\",\"facing\":\"%s\",\"triggers\":%d,"
                  "\"trigger_dist\":%d,\"trigger_dx\":%d,\"trigger_dy\":%d,"
                  "\"changed\":%d,\"opened\":%d,\"closed\":%d,\"changes\":%d,"
                  "\"last_move\":%d,\"puzzle_map\":%s,"
                  "\"open\":{\"n\":%s,\"e\":%s,\"s\":%s,\"w\":%s},"
                  "\"grid\":[%d,%d,%lu],\"blocks\":[%lu,%lu,%lu,%lu]}",
                  p.ok ? "true" : "false", p.mapGroup, p.mapNum, p.x, p.y,
                  terrain_name(p.underfoot), terrain_name(p.facing),
                  p.coordEventCount, p.triggerDist, p.triggerDx, p.triggerDy,
                  p.changedBlocks, p.openedBlocks, p.closedBlocks, p.totalChanges,
                  p.lastMoveTiles, p.puzzleMap ? "true" : "false",
                  p.openN ? "true" : "false", p.openE ? "true" : "false",
                  p.openS ? "true" : "false", p.openW ? "true" : "false",
                  p.gridWidth, p.gridHeight, static_cast<unsigned long>(p.gridBlocks),
                  static_cast<unsigned long>(p.blockN), static_cast<unsigned long>(p.blockE),
                  static_cast<unsigned long>(p.blockS), static_cast<unsigned long>(p.blockW));
    return head;
}

void puzzle_reset() { g_t = Tracker{}; }

void puzzle_frame(const emerald::touch::SceneState& scene, const Mem& m,
                  std::uint16_t host_keys) {
    ++g_t.frame;

    if (scene.kind != emerald::touch::SceneKind::Overworld || scene.menu.live ||
        scene.list.live) {
        g_t.have_pos = false;   // whatever we do next is a fresh start
        return;
    }
    if (m.u8(addr::sFieldMessageBoxMode) != 0) {
        g_t.have_pos = false;   // reading: the player is not walking
        return;
    }

    const Player p = read_player(m);
    if (!p.ok) return;

    // ── New map ──────────────────────────────────────────────────────────
    if (!g_t.have_map || p.mapGroup != g_t.mapGroup || p.mapNum != g_t.mapNum) {
        g_t.have_map = true;
        g_t.mapGroup = p.mapGroup;
        g_t.mapNum = p.mapNum;
        g_t.have_pos = false;
        reset_map_state();
        // Indoors, a coord-event tile is a floor mechanism (a gym plate, a
        // Trick House tile, a pit); outdoors it is a story trigger, and naming
        // those would be chatter. That is the game's own map type, never a map
        // id, so every indoor puzzle gets plate guidance from the first step
        // instead of only after a switch has already been found.
        Trigger probe[kCoordEventMax];
        g_t.puzzle_map = m.u8(addr::gMapHeader + 0x17) == 8 &&   // MAP_TYPE_INDOOR
                         read_triggers(m, probe, kCoordEventMax) > 0;
    }

    // ── Terrain underfoot and in front ───────────────────────────────────
    // Only special ground is named. Normal floor, grass and cave rock are what
    // the player is already walking on and saying so on every step would make
    // the voice useless.
    const Terrain underfoot = terrain_of_behavior(behavior_at(m, p.x, p.y));
    if (underfoot != Terrain::Plain &&
        (static_cast<int>(underfoot) != g_t.announced_underfoot ||
         p.x != g_t.announced_underfoot_x || p.y != g_t.announced_underfoot_y)) {
        g_t.announced_underfoot = static_cast<int>(underfoot);
        g_t.announced_underfoot_x = p.x;
        g_t.announced_underfoot_y = p.y;
        if (const char* line = terrain_speech(underfoot); line && *line)
            speak_now(line, false);
    }
    int fx = 0, fy = 0;
    facing_step(p.facing, &fx, &fy);
    const Terrain facing = terrain_of_behavior(behavior_at(m, p.x + fx, p.y + fy));
    const bool facing_changed = facing != Terrain::Plain &&
        (static_cast<int>(facing) != g_t.announced_facing ||
         p.x + fx != g_t.announced_facing_x || p.y + fy != g_t.announced_facing_y);
    if (facing_changed) {
        g_t.announced_facing = static_cast<int>(facing);
        g_t.announced_facing_x = p.x + fx;
        g_t.announced_facing_y = p.y + fy;
        if (const char* line = terrain_speech(facing); line && *line)
            speak_now(line, false);
    }

    // ── Movement: did the player ask for it? ─────────────────────────────
    // A pad direction the host is holding, or a tap the layer queued, is a
    // player move. Anything else that changes the tile is the game moving the
    // player: an ice slide, a warp panel, a fall, a scripted push.
    // Two sources press directions: the host's own pad (active low) and the
    // synthesised pad the mod's action command drives (active high). A walk the
    // harness asks for arrives through the second one, so a refused step would
    // go unseen while only the host keys were consulted.
    const std::uint16_t pressed_directions = static_cast<std::uint16_t>(
        ((~host_keys) & 0x00F0u) |
        (emerald::touch::core().synth.last_pressed() & 0x00F0u));
    const bool direction_held = pressed_directions != 0;
    const bool input_idle = emerald::touch::core().synth.idle();
    const int dx = p.x - g_t.last_x;
    const int dy = p.y - g_t.last_y;
    const bool moved = g_t.have_pos && (dx != 0 || dy != 0);

    // ── Refused step ─────────────────────────────────────────────────────
    // Press a direction against a wall, a closed energy beam or a fence and
    // nothing at all happens: no sound, no hint, no change on screen a player
    // without sight can use. That makes a switchable maze impossible to probe
    // by ear, so a direction held for several frames against an impassable
    // tile is spoken once per tile, direction and blocking block. The block
    // value is part of the key because a beam that flips is a different
    // metatile, so a plate press that changes what blocks a step is heard
    // again rather than staying silent.
    int want_x = 0, want_y = 0;
    if (pressed_directions & 0x0010u) want_x = 1;         // KEY_RIGHT
    else if (pressed_directions & 0x0020u) want_x = -1;   // KEY_LEFT
    else if (pressed_directions & 0x0040u) want_y = -1;   // KEY_UP
    else if (pressed_directions & 0x0080u) want_y = 1;    // KEY_DOWN
    if ((want_x || want_y) && g_t.have_pos) {
        if (!g_t.press_active) {         // a new press starts
            g_t.press_active = true;
            g_t.press_x = want_x;
            g_t.press_y = want_y;
            g_t.press_moved = false;
        }
        if (moved) g_t.press_moved = true;
    } else if (g_t.press_active) {       // the press ended: did it move us?
        g_t.press_active = false;
        if (!g_t.press_moved) {
            const Grid g = grid_of(m);
            if (g.ok) {
                const std::uint16_t block = block_at(m, g, p.x + g_t.press_x, p.y + g_t.press_y);
                const bool changed_block = block != g_t.block_value || p.x != g_t.block_x ||
                                           p.y != g_t.block_y ||
                                           g_t.press_x != g_t.block_dx ||
                                           g_t.press_y != g_t.block_dy;
                // A ledge is not a wall: it is the door you jump. Naming it
                // twice (once as terrain, once as "Blocked") would bury the
                // one useful word in a contradiction.
                const Terrain into = terrain_of_behavior(
                    behavior_at(m, p.x + g_t.press_x, p.y + g_t.press_y));
                if (!passable_block(block) && changed_block && !is_ledge(into)) {
                    g_t.block_value = block;
                    g_t.block_x = p.x;
                    g_t.block_y = p.y;
                    g_t.block_dx = g_t.press_x;
                    g_t.block_dy = g_t.press_y;
                    const std::string line =
                        "Blocked " + std::string(compass(g_t.press_x, g_t.press_y)) + ".";
                    speak_now(line.c_str(), false);
                }
            }
        }
    }

    if (moved && !direction_held && input_idle) {
        g_t.forced_tiles += std::abs(dx) + std::abs(dy);
        g_t.forced_dx += dx;
        g_t.forced_dy += dy;
        g_t.forced_idle = 0;
    } else if (!moved) {
        ++g_t.forced_idle;
        if (g_t.forced_tiles >= 2 && g_t.forced_idle >= 4) {
            const std::string where = compass(g_t.forced_dx, g_t.forced_dy);
            const std::string line = "You were moved " + std::to_string(g_t.forced_tiles) +
                                     " tiles " + where + ".";
            g_t.last_move_tiles = g_t.forced_tiles;
            g_t.forced_tiles = 0;
            g_t.forced_dx = g_t.forced_dy = 0;
            speak_now(line.c_str(), false);
        }
    } else {
        // A player-driven step: the previous forced move (if any) is over.
        g_t.forced_tiles = 0;
        g_t.forced_dx = g_t.forced_dy = 0;
        g_t.forced_idle = 0;
    }
    g_t.last_x = p.x;
    g_t.last_y = p.y;
    g_t.have_pos = true;
    g_t.still = moved ? 0 : g_t.still + 1;

    // ── Room geometry ────────────────────────────────────────────────────
    // Keep a baseline of the window and diff against it. A map script
    // rewriting the room (a switch, a turnstile, a statue, a door opening)
    // shows up as a diff, and the direction of the change is what a sighted
    // player sees happening.
    //
    // The baseline is indexed by world tile, not by offset from the player.
    // That matters twice over. A one-tile step shifts every offset, so an
    // offset diff would report the whole window as changed on every step. And
    // a pressure plate's script rewrites the beams on the very frame the
    // player lands on it, so a baseline taken after arrival already contains
    // the new room: the plates in Mauville Gym fired all through the run and
    // yet nothing was ever spoken. Comparing world tiles on arrival catches
    // that frame, and the baseline is then retaken for the tile we now stand on.
    auto diff_room = [&]() {
        const Grid g = grid_of(m);
        if (!g.ok || !g_t.have_snapshot) return;
        if (g_t.snapshot.size() != static_cast<std::size_t>((2 * kScanRadius + 1) *
                                                          (2 * kScanRadius + 1)))
            return;
        int changed = 0, opened = 0, closed = 0;
        long sum_dx = 0, sum_dy = 0;
        std::size_t i = 0;
        for (int sy = -kScanRadius; sy <= kScanRadius; ++sy) {
            for (int sx = -kScanRadius; sx <= kScanRadius; ++sx, ++i) {
                const int wx = g_t.snap_x + sx, wy = g_t.snap_y + sy;
                const std::uint16_t now = block_at(m, g, wx, wy);
                if (now == g_t.snapshot[i]) continue;
                const bool was_open = passable_block(g_t.snapshot[i]);
                const bool is_open = passable_block(now);
                if (was_open == is_open && (now & 0x03FF) == (g_t.snapshot[i] & 0x03FF))
                    continue;   // elevation-only change: not a path
                ++changed;
                // The tile underfoot is where the press happened: a plate
                // rewrites its own metatile when it fires. Count that as the
                // press, never as a path, or a plate that is solid until
                // pressed would supply the one "opening" that turns every
                // ordinary press into a swap.
                if (wx != p.x || wy != p.y) {
                    if (!was_open && is_open) ++opened;
                    if (was_open && !is_open) ++closed;
                }
                sum_dx += wx - p.x;
                sum_dy += wy - p.y;
                g_t.snapshot[i] = now;
            }
        }
        g_t.last_changed = changed;
        g_t.last_opened = opened;
        g_t.last_closed = closed;
        if (changed == 0) return;
        const std::string where = compass(
            std::abs(sum_dx) < 2 ? 0 : (sum_dx > 0 ? 1 : -1),
            std::abs(sum_dy) < 2 ? 0 : (sum_dy > 0 ? 1 : -1));
        ++g_t.total_changes;
        // Say which way, not just that something happened: a switch that
        // raises beams without changing passability is still a change the
        // player has to connect to the plate they stepped on.
        if (opened > 0 && closed == 0) {
            speak_now(("A path opened " + where + ".").c_str(), false);
        } else if (closed > 0 && opened == 0) {
            speak_now(("A path closed " + where + ".").c_str(), false);
        } else if (opened > 0 && closed > 0) {
            // Paths that were open closed while others opened: the room
            // swapped one arrangement for another. "The room changed" hid
            // that, so a player who stepped off a plate to find their route
            // barred had no way to tell it was the press that did it - which
            // is exactly what Mauville Gym's beam switches do on every press.
            speak_now(("Paths swapped " + where + ".").c_str(), false);
        } else {
            speak_now(("The room changed " + where + ".").c_str(), false);
        }
        // From now on this map has proven to have switchable geometry, so
        // naming the trigger tiles you can step on is guidance the player
        // asked for by being here — not chatter.
        g_t.puzzle_map = true;
    };

    const bool tile_changed =
        !g_t.have_snapshot || p.x != g_t.snap_x || p.y != g_t.snap_y;
    if (tile_changed) {
        diff_room();            // did the step itself rewrite the room?
        snapshot_window(m, p);  // new baseline, taken after the script ran
    } else if (g_t.still >= 1) {
        diff_room();            // a script that wrote a frame or two later
    }

    // ── Trigger tiles, once the map has shown it has a puzzle ────────────
    if (g_t.puzzle_map && g_t.still >= kSettleFrames) {
        Trigger triggers[kCoordEventMax];
        const int count = read_triggers(m, triggers, kCoordEventMax);
        int best = 1 << 30, bx = 0, by = 0;
        for (int i = 0; i < count; ++i) {
            if (triggers[i].elevation != p.elevation && triggers[i].elevation != 3)
                continue;
            const int ddx = triggers[i].x - p.x;
            const int ddy = triggers[i].y - p.y;
            const int d = std::abs(ddx) + std::abs(ddy);
            if (d == 0) { best = 0; bx = ddx; by = ddy; break; }   // standing on it
            if (d < best) { best = d; bx = ddx; by = ddy; }
        }
        if (best > 0 && best <= 2 &&
            (g_t.trigger_notice_x != p.x + bx || g_t.trigger_notice_y != p.y + by)) {
            g_t.trigger_notice_x = p.x + bx;
            g_t.trigger_notice_y = p.y + by;
            const std::string steps =
                best == 1 ? "one step " : "two steps ";
            speak_now(("Step plate " + std::string(steps) + compass(bx, by) + ".").c_str(),
                      false);
        }
        if (best == 0) {
            // Standing on one: it fires by itself, so the room's answer is the
            // news. But a plate already pressed does nothing at all, and
            // silence on a plate tile is indistinguishable from silence on
            // plain floor - the player then presses it again believing the
            // first press was missed. Say once per tile that a plate is here.
            if (g_t.underfoot_notice_x != p.x || g_t.underfoot_notice_y != p.y) {
                g_t.underfoot_notice_x = p.x;
                g_t.underfoot_notice_y = p.y;
                speak_now("Plate underfoot.", false);
            }
            // Forgetting the notice lets the next approach speak.
            g_t.trigger_notice_x = g_t.trigger_notice_y = -999;
        }
        // Keep the reading for the read key, whether or not it was announced.
        g_t.trigger_dist = best == (1 << 30) ? -1 : best;
        g_t.trigger_dx = best > 0 ? bx : 0;
        g_t.trigger_dy = best > 0 ? by : 0;
        g_t.trigger_on = best == 0;
        if (best >= 0 && best < (1 << 30)) {
            const Grid g = grid_of(m);
            g_t.trigger_raised = !passable_block(block_at(m, g, p.x + bx, p.y + by));
        }
    }

    // ── Ledges ───────────────────────────────────────────────────────────
    // A ledge is the one blocked tile that is a door, and the jump happens in
    // a single press, so there is no frame where turning towards it can speak:
    // walking straight into one produced no cue at all on the first re-walk.
    // It is announced by distance and compass point like the pits, before the
    // step, and the sentence carries the way you jump - a ledge only jumps one
    // way, and standing on the landing side makes it a wall again.
    //
    // No settle gate here, unlike the pits: a pit is stepped onto and you stay
    // standing, but a ledge is crossed *by* the press, so waiting for the player
    // to stand still means the cue arrives after the jump - or never at all on a
    // continuous walk. Two tiles is the whole approach.
    {
        int best = 1 << 30, bx = 0, by = 0, jump_x = 0, jump_y = 0;
        for (int dy = -2; dy <= 2; ++dy) {
            for (int dx = -2; dx <= 2; ++dx) {
                const int d = std::abs(dx) + std::abs(dy);
                if (d < 1 || d > 2) continue;
                const Terrain t =
                    terrain_of_behavior(behavior_at(m, p.x + dx, p.y + dy));
                if (!is_ledge(t)) continue;
                int jx = 0, jy = 0;
                ledge_jump(t, &jx, &jy);
                if (d < best) {
                    best = d;
                    bx = dx;
                    by = dy;
                    jump_x = jx;
                    jump_y = jy;
                }
            }
        }
        if (best < (1 << 30)) {
            // The jump vector is the way the player travels, so it points from
            // the standing side to the landing side: same direction as the
            // ledge seen from here. Opposite means a wall until you walk round.
            const bool crossable = (bx * jump_x + by * jump_y) > 0;
            // The approach cue is the one that has to beat the press, so it is
            // not gated. The far-side cue can wait for the player to stand:
            // otherwise the jump animation's own frames - where the player is
            // momentarily over the ledge tile - announce a cut-off route that
            // is not there.
            const bool ready = crossable || g_t.still >= kSettleFrames;
            const bool fresh = g_t.ledge_x != p.x + bx || g_t.ledge_y != p.y + by;
            if (ready && fresh) {
                // A map whose only affordance is ledges (Flannery's room) also
                // has no coord events, so the read key needs telling here too.
                g_t.puzzle_map = true;
                g_t.ledge_x = p.x + bx;
                g_t.ledge_y = p.y + by;
                const std::string line =
                    std::string("Ledge ") + (best == 1 ? "one step " : "two steps ") +
                    compass(bx, by) + ". " +
                    (crossable ? std::string("Jump ") + compass(jump_x, jump_y) +
                                     " to cross it."
                               : std::string("It only jumps ") + compass(jump_x, jump_y) +
                                     ". You are on the far side.");
                speak_now(line.c_str(), false);
            }
        }
    }

    // ── Pits and vents ───────────────────────────────────────────────────
    // Lavaridge Gym is two floors built out of nothing but these tiles: one
    // drops you into the basement, one throws you back up. Learning that by
    // landing in it is not playable, so they are named the way the plates are
    // - by distance and compass point - before the step is taken.
    if (g_t.still >= kSettleFrames) {
        int best = 1 << 30, bx = 0, by = 0, kind = 0;   // 1 = pit, 2 = vent
        for (int dy = -2; dy <= 2; ++dy) {
            for (int dx = -2; dx <= 2; ++dx) {
                const int d = std::abs(dx) + std::abs(dy);
                if (d > 2) continue;
                const Terrain t =
                    terrain_of_behavior(behavior_at(m, p.x + dx, p.y + dy));
                const int k = t == Terrain::Pit ? 1 : (t == Terrain::Vent ? 2 : 0);
                if (k == 0) continue;
                if (d < best) { best = d; bx = dx; by = dy; kind = k; }
            }
        }
        if (kind > 0) {
            // These maps are puzzles with no coord events and no room diff, so
            // the read key needs telling; finding one is proof enough.
            g_t.puzzle_map = true;
            if (best == 0) {
                if (g_t.underfoot_notice_x != p.x || g_t.underfoot_notice_y != p.y) {
                    g_t.underfoot_notice_x = p.x;
                    g_t.underfoot_notice_y = p.y;
                    speak_now(kind == 1 ? "Pit underfoot." : "Vent underfoot.", false);
                }
            } else if (g_t.hazard_x != p.x + bx || g_t.hazard_y != p.y + by) {
                g_t.hazard_x = p.x + bx;
                g_t.hazard_y = p.y + by;
                speak_now((std::string(kind == 1 ? "Pit " : "Vent ") +
                           (best == 1 ? "one step " : "two steps ") +
                           compass(bx, by) + ".").c_str(), false);
            }
        }
    }
}

// ── Read-key sentence ────────────────────────────────────────────────────
namespace {

const char* count_word(int n) {
    switch (n) {
        case 1: return "one step";
        case 2: return "two steps";
        case 3: return "three steps";
        case 4: return "four steps";
        case 5: return "five steps";
        case 6: return "six steps";
        case 7: return "seven steps";
        case 8: return "eight steps";
        case 9: return "nine steps";
        default: return nullptr;
    }
}

// "north", "north and east", "north, east and south"
void append_directions(std::string* out, const bool open[4]) {
    static const char* const names[4] = {"north", "east", "south", "west"};
    int listed = 0, total = 0;
    for (int i = 0; i < 4; ++i) total += open[i] ? 1 : 0;
    if (total == 0) return;
    for (int i = 0; i < 4; ++i) {
        if (!open[i]) continue;
        if (listed > 0) *out += (listed == total - 1) ? " and " : ", ";
        *out += names[i];
        ++listed;
    }
}

}  // namespace

std::string puzzle_context_speech(const PuzzleState& p) {
    if (!p.ok || !p.puzzleMap) return std::string();
    std::string out = "Puzzle.";
    if (p.onTrigger) {
        out += " Plate underfoot.";
    } else if (p.triggerDist > 0 && p.triggerDist <= 9) {
        const char* words = count_word(p.triggerDist);
        if (words) {
            out += " Plate ";
            out += words;
            out += ' ';
            out += compass(p.triggerDx, p.triggerDy);
            out += p.triggerRaised ? ", raised." : ".";
        }
    }
    // Ways out of the tile underfoot. Blocked is the fact a wall and a beam
    // share, so this reads the same in every gym.
    bool open[4] = {p.openN, p.openE, p.openS, p.openW};
    bool ledge[4];
    for (int i = 0; i < 4; ++i) ledge[i] = ((p.ledgeMask >> i) & 1) != 0;
    // A ledge is blocked to walk into but is not a wall: it is reported on its
    // own line so "Blocked south." never stands where the only door is.
    bool blocked[4] = {!p.openN && !ledge[0], !p.openE && !ledge[1],
                       !p.openS && !ledge[2], !p.openW && !ledge[3]};
    int open_count = 0;
    for (int i = 0; i < 4; ++i) open_count += open[i] ? 1 : 0;
    if (open_count == 0) {
        out += " Boxed in.";
    } else if (open_count < 4) {
        out += " Open ";
        append_directions(&out, open);
        out += '.';
        // Only name the blocked ways when there are few enough to be useful.
        int blocked_count = 4 - open_count;
        if (blocked_count <= 2) {
            bool walls[4];
            int wall_count = 0;
            for (int i = 0; i < 4; ++i) {
                walls[i] = blocked[i];
                wall_count += walls[i] ? 1 : 0;
            }
            if (wall_count > 0) {
                out += " Blocked ";
                append_directions(&out, walls);
                out += '.';
            }
        }
    }
    int ledge_count = 0;
    for (int i = 0; i < 4; ++i) ledge_count += ledge[i] ? 1 : 0;
    if (ledge_count > 0) {
        out += " Ledge ";
        append_directions(&out, ledge);
        out += '.';
    }
    return out;
}

}  // namespace emerald::accessibility

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
// Reading the backup grid (rather than the ROM layout) is what makes a switch
// press visible: map scripts change the room with `setmetatile`, which writes
// that grid.

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
};

Grid grid_of(const Mem& m) {
    Grid g;
    g.width = static_cast<int>(m.u32(kBackupMapLayout));
    g.height = static_cast<int>(m.u32(kBackupMapLayout + 4));
    g.blocks = m.u32(kBackupMapLayout + 8);
    g.ok = g.width > 0 && g.width <= 512 && g.height > 0 && g.height <= 512 &&
           g.blocks >= 0x02000000u && g.blocks < 0x02040000u;
    return g;
}

std::uint16_t block_at(const Mem& m, const Grid& g, int x, int y) {
    if (!g.ok || x < 0 || y < 0 || x >= g.width || y >= g.height) return 0x03FF;
    return m.u16(g.blocks + static_cast<std::uint32_t>((y * g.width + x) * 2));
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
        case kMbMossdeepGymWarp:
        case kMbLavaridge1FWarp:
        case kMbLavaridgeB1FWarp:
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

    int last_opened = 0, last_closed = 0, last_changed = 0;
    int total_changes = 0;   // room changes seen on this map (diagnostics)
    int last_move_tiles = 0;
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
    g_t.last_opened = g_t.last_closed = g_t.last_changed = 0;
    g_t.last_move_tiles = 0;
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
    p.lastMoveTiles = g_t.last_move_tiles;
    p.openedBlocks = g_t.last_opened;
    p.closedBlocks = g_t.last_closed;
    p.changedBlocks = g_t.last_changed;
    p.totalChanges = g_t.total_changes;
    p.puzzleMap = g_t.puzzle_map;
    return true;
}

std::string puzzle_json(const PuzzleState& p) {
    char head[256];
    std::snprintf(head, sizeof(head),
                  "{\"ok\":%s,\"map\":[%d,%d],\"x\":%d,\"y\":%d,"
                  "\"underfoot\":\"%s\",\"facing\":\"%s\",\"triggers\":%d,"
                  "\"trigger_dist\":%d,\"trigger_dx\":%d,\"trigger_dy\":%d,"
                  "\"changed\":%d,\"opened\":%d,\"closed\":%d,\"changes\":%d,"
                  "\"last_move\":%d,\"puzzle_map\":%s}",
                  p.ok ? "true" : "false", p.mapGroup, p.mapNum, p.x, p.y,
                  terrain_name(p.underfoot), terrain_name(p.facing),
                  p.coordEventCount, p.triggerDist, p.triggerDx, p.triggerDy,
                  p.changedBlocks, p.openedBlocks, p.closedBlocks, p.totalChanges,
                  p.lastMoveTiles, p.puzzleMap ? "true" : "false");
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
    const bool direction_held = ((~host_keys) & 0x00F0u) != 0;
    const bool input_idle = emerald::touch::core().synth.idle();
    const int dx = p.x - g_t.last_x;
    const int dy = p.y - g_t.last_y;
    const bool moved = g_t.have_pos && (dx != 0 || dy != 0);
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
    // Snapshot the window once the player stands still, then re-read it every
    // settled frame. A map script rewriting the room (a switch, a turnstile, a
    // statue, a door opening) shows up as a diff, and the direction of the
    // change is what a sighted player sees happening.
    if (!g_t.have_snapshot || p.x != g_t.snap_x || p.y != g_t.snap_y) {
        // Snapshot the instant the tile changes. A trigger's map script runs on
        // the landing frame, so a snapshot taken after a settle delay already
        // contains the new room — the diff then always reported zero and a
        // switch could never be heard.
        snapshot_window(m, p);
        g_t.last_opened = g_t.last_closed = g_t.last_changed = 0;
    } else if (g_t.still >= 1) {
        const Grid g = grid_of(m);
        if (g.ok && g_t.snapshot.size() ==
                       static_cast<std::size_t>((2 * kScanRadius + 1) *
                                                (2 * kScanRadius + 1))) {
            int changed = 0, opened = 0, closed = 0;
            long sum_dx = 0, sum_dy = 0;
            std::size_t i = 0;
            for (int sy = -kScanRadius; sy <= kScanRadius; ++sy) {
                for (int sx = -kScanRadius; sx <= kScanRadius; ++sx, ++i) {
                    const std::uint16_t now = block_at(m, g, p.x + sx, p.y + sy);
                    if (now == g_t.snapshot[i]) continue;
                    const bool was_open = passable_block(g_t.snapshot[i]);
                    const bool is_open = passable_block(now);
                    if (was_open == is_open && (now & 0x03FF) == (g_t.snapshot[i] & 0x03FF))
                        continue;   // elevation-only change: not a path
                    ++changed;
                    if (!was_open && is_open) ++opened;
                    if (was_open && !is_open) ++closed;
                    sum_dx += sx;
                    sum_dy += sy;
                    g_t.snapshot[i] = now;
                }
            }
            g_t.last_changed = changed;
            g_t.last_opened = opened;
            g_t.last_closed = closed;
            if (changed > 0) {
                const std::string where = compass(
                    std::abs(sum_dx) < 2 ? 0 : (sum_dx > 0 ? 1 : -1),
                    std::abs(sum_dy) < 2 ? 0 : (sum_dy > 0 ? 1 : -1));
                ++g_t.total_changes;
                // Say which way, not just that something happened: a switch
                // that raises beams without changing passability is still a
                // change the player has to connect to the plate they stepped on.
                if (opened > 0 && closed == 0) {
                    speak_now(("A path opened " + where + ".").c_str(), false);
                } else if (closed > 0 && opened == 0) {
                    speak_now(("A path closed " + where + ".").c_str(), false);
                } else {
                    speak_now(("The room changed " + where + ".").c_str(), false);
                }
                // From now on this map has proven to have switchable geometry,
                // so naming the trigger tiles you can step on is guidance the
                // player asked for by being here — not chatter.
                g_t.puzzle_map = true;
            }
        }
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
            // Standing on one: it fires by itself, so nothing to say until the
            // room answers. Forgetting the notice lets the next approach speak.
            g_t.trigger_notice_x = g_t.trigger_notice_y = -999;
        }
    }
}

}  // namespace emerald::accessibility

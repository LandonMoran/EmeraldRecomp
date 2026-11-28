// emerald_nav.cpp — where the exits are, and what the player is walking up to.
//
// Facts come from the pinned pokemerald revision (see emerald_guest.h):
//   gMapHeader            MapHeader   @0x02037318
//     +0x04               const struct MapEvents *events        (ROM pointer)
// struct MapEvents      objectEventCount u8 @0, warpCount u8 @1,
//                         objectEvents * @4, warps * @8,
//                         coordEventCount u8 @2, bgEventCount u8 @3,
//                         bgEvents * @0x10
//   struct WarpEvent      s16 x, s16 y, u8 elevation, u8 warpId, u8 mapNum,
//                         u8 mapGroup                        (8 bytes)
//   struct BgEvent        u16 x @0, u16 y @2, u8 elevation @4, u8 kind @5,
//                         const u8 *script @8                 (12 bytes)
//                         BG_EVENT_PLAYER_FACING_* (constants/event_bg.h):
//                         0 any, 1 north, 2 south, 3 east, 4 west,
//                         7 hidden item, 8 secret base
//   The engine's own GetBackgroundEventAtPosition walks that 12-byte table,
//   matching x, y and (record elevation == 0 or == the player's); its caller
//   GetInteractedBackgroundEventScript then gates on kind, so a sign is only
//   readable from the side it was authored for. Both are mirrored here.
//   struct ObjectEvent    active:1 @0, invisible:1 @1.5, isPlayer:1 @2,
//                         graphicsId @0x05, trainerType @0x07,
//                         mapNum @0x09, mapGroup @0x0A,
//                         currentElevation:4 @0x0B, coords @0x10
// Object graphics id 59 (OBJ_EVENT_GFX_ITEM_BALL) is an item ball on the field.

#include "emerald_nav.h"

#include <cstdio>
#include <cstdlib>
#include <string>

#include "emerald_a11y.h"      // speak_now (used indirectly through cues)
#include "emerald_cues.h"
#include "emerald_map_names.h"
#include "touch/emerald_scene.h"   // SceneKind / SceneState

namespace emerald::accessibility {
namespace {

namespace addr = emerald::guest::addr;
using emerald::guest::Mem;

constexpr std::uint32_t kMapEventsPtr = 0x04;
constexpr std::uint32_t kMapEventsWarpCount = 0x01;
constexpr std::uint32_t kMapEventsBgCount = 0x03;
constexpr std::uint32_t kMapEventsWarps = 0x08;
constexpr std::uint32_t kMapEventsBgEvents = 0x10;
constexpr std::uint32_t kWarpEventSize = 8;

// MapHeader: mapLayout @0x00, events @0x04, mapScripts @0x08,
//            connections @0x0C (global.fieldmap.h). +0x08 is a *script*
//            pointer, and reading it as the table silently produced no roads.
//   struct MapConnections { s32 count; const MapConnection *connections; }
//   struct MapConnection  { u8 direction; s32 offset; u8 mapGroup; u8 mapNum; }
//   - direction at +0, mapGroup at +8, mapNum at +9, 12 bytes with padding.
// Direction codes are the engine's: 1 north, 2 south, 3 west, 4 east.
constexpr std::uint32_t kMapLayoutPtr = 0x00;
constexpr std::uint32_t kMapConnectionsPtr = 0x0C;
constexpr std::uint32_t kMapConnectionSize = 12;
constexpr int kConnNorth = 1, kConnSouth = 2, kConnWest = 3, kConnEast = 4;
constexpr int kConnNoticeTiles = 3;

// Background events: signs, the wall clock, the TV, shelves. They have no
// sprite, so nothing in the object list can say where they are.
constexpr std::uint32_t kBgEventSize = 12;
constexpr std::uint32_t kBgEventX = 0x00;
constexpr std::uint32_t kBgEventY = 0x02;
constexpr std::uint32_t kBgEventElevation = 0x04;
constexpr std::uint32_t kBgEventKind = 0x05;
constexpr std::uint32_t kBgEventScript = 0x08;
constexpr int kBgEventCountMax = 32;     // generous: real maps carry 0..12

// BG_EVENT_PLAYER_FACING_* — which way the player must face to read one.
constexpr int kBgFacingAny = 0;
constexpr int kBgFacingNorth = 1;
constexpr int kBgFacingSouth = 2;
constexpr int kBgFacingEast = 3;
constexpr int kBgFacingWest = 4;

constexpr std::uint32_t kEventSize = 0x24;
constexpr std::uint32_t kEventCoords = 0x10;
constexpr std::uint32_t kEventGraphics = 0x05;
constexpr std::uint32_t kEventTrainerType = 0x07;
constexpr std::uint32_t kEventMapNum = 0x09;
constexpr std::uint32_t kEventMapGroup = 0x0A;
constexpr std::uint32_t kEventElevation = 0x0B;
constexpr int kEventCount = 16;

constexpr int kItemBallGraphics = 59;   // OBJ_EVENT_GFX_ITEM_BALL
// Strength boulders and Rock Smash rocks are object events, so without naming
// them the field says only "Object here" — which is the difference between a
// puzzle and a wall for a blind player.
constexpr int kBreakableRockGraphics = 86;   // OBJ_EVENT_GFX_BREAKABLE_ROCK
constexpr int kPushableBoulderGraphics = 87; // OBJ_EVENT_GFX_PUSHABLE_BOULDER
// The moving box in the opening truck is scenery, not a person: the game's own
// description when you press A on it is "The box is printed with a POKéMON
// logo...", so calling it a person sent the player looking for a face.
constexpr int kMovingBoxGraphics = 113;  // OBJ_EVENT_GFX_MOVING_BOX
// Object-event coords carry the field's MAP_OFFSET; warp events use map tiles.
constexpr int kMapOffset = 7;

// Announcement policy.
constexpr int kWarpNoticeTiles = 2;     // start mentioning an exit this close
// Nothing here repeats on a timer: a thing is described when it becomes what
// the player is next to or looking at, and silence means nothing changed.

struct Target {
    bool set = false;
    int mapGroup = -1, mapNum = -1;
    int x = 0, y = 0;
};

struct Announcer {
    int mapGroup = -1, mapNum = -1;
    bool have_map = false;
    int warp_index = -1;
    int warp_frame = -100000;
    int npc_frame = -100000;
    int npc_dx = 999, npc_dy = 999, npc_kind = -1;   // who was last announced
    int look_x = -999, look_y = -999, look_kind = -1;  // what was looked at
    int conn_dir = -1;                                 // road edge already named
    int conn_frame = -100000;
    int frame = 0;
};
Announcer g_ann;
Target g_target;

std::string join(const char* a, const std::string& b, const char* c) {
    return std::string(a) + b + c;
}

// Background-event kind to the facing it demands (0 = read from any side,
// -1 = not something the player reads: hidden items, secret bases).
// Facing codes are the object's own: 1 south, 2 north, 3 west, 4 east.
int bg_event_required_facing(int kind) {
    switch (kind) {
        case kBgFacingAny: return 0;
        case kBgFacingNorth: return 2;
        case kBgFacingSouth: return 1;
        case kBgFacingEast: return 4;
        case kBgFacingWest: return 3;
        default: return -1;
    }
}

const char* facing_word(int facing) {
    switch (facing) {
        case 1: return "south";
        case 2: return "north";
        case 3: return "west";
        case 4: return "east";
        default: return "nearby";
    }
}

}  // namespace

void facing_step(int facing, int* dx, int* dy) {
    int sx = 0, sy = 0;
    switch (facing) {
        case 1: sy = 1; break;    // south
        case 2: sy = -1; break;   // north
        case 3: sx = -1; break;   // west
        case 4: sx = 1; break;    // east
        default: break;
    }
    if (dx) *dx = sx;
    if (dy) *dy = sy;
}

const char* compass(int dx, int dy) {
    if (dx == 0 && dy == 0) return "here";
    if (dx == 0) return dy > 0 ? "south" : "north";
    if (dy == 0) return dx > 0 ? "east" : "west";
    if (dx > 0) return dy > 0 ? "south-east" : "north-east";
    return dy > 0 ? "south-west" : "north-west";
}

bool read_nav(const Mem& m, NavState* out) {
    if (!out) return false;
    NavState& n = *out;
    n = NavState{};

    const std::uint32_t sb1 = m.u32(addr::gSaveBlock1Ptr);
    if (sb1 < 0x02000000u || sb1 >= 0x02040000u) return false;
    n.mapGroup = m.u8(sb1 + 4);
    n.mapNum = m.u8(sb1 + 5);

    const int id = m.u8(addr::gPlayerAvatar + 5);
    if (id >= kEventCount) return false;
    const std::uint32_t o = addr::gObjectEvents + id * kEventSize;
    n.x = m.s16(o + kEventCoords);
    n.y = m.s16(o + kEventCoords + 2);
    n.facing = m.u8(o + 0x18) & 0x0F;
    n.elevation = m.u8(o + kEventElevation) & 0x0F;
    n.ok = true;

    const std::uint32_t layout = m.u32(addr::gMapHeader + kMapLayoutPtr);

    // Warp events for this map (ROM tables pointed at by the RAM map header).
    // Routes have no warp entries at all, so a missing table must not skip the
    // facing probe below: what you are looking at matters on every map.
    const std::uint32_t events = m.u32(addr::gMapHeader + kMapEventsPtr);
    const bool have_events = events >= 0x08000000u;
    const int warp_count = have_events ? m.u8(events + kMapEventsWarpCount) : 0;
    const std::uint32_t warps = have_events ? m.u32(events + kMapEventsWarps) : 0;

    n.warpCount = 0;
    for (int i = 0; warps >= 0x08000000u && i < warp_count && n.warpCount < 8; ++i) {
        const std::uint32_t w = warps + static_cast<std::uint32_t>(i) * kWarpEventSize;
        WarpInfo info;
        info.x = m.s16(w + 0);
        info.y = m.s16(w + 2);
        info.elevation = m.u8(w + 4);
        info.warpId = m.u8(w + 5);
        info.mapNum = m.u8(w + 6);
        info.mapGroup = m.u8(w + 7);
        // Destination 127/127 is the game's "no warp here" filler entry (the
        // truck and several interior maps carry them); it is not an exit.
        if (info.mapGroup == 127 || info.mapNum == 127) continue;
        // A warp whose elevation differs from the tile the player stands on is
        // a floor change (stairs, ledge, cave mouth); same elevation is a door.
        info.stair = info.elevation != 0 && info.elevation != n.elevation;
        info.goesUp = info.elevation > n.elevation;
        n.warps[n.warpCount++] = info;
    }

    // Connecting maps: the road out of town is a map connection, not a warp.
    {
        const int width = layout ? static_cast<int>(m.u32(layout + 0x00)) : 0;
        const int height = layout ? static_cast<int>(m.u32(layout + 0x04)) : 0;
        const std::uint32_t table = m.u32(addr::gMapHeader + kMapConnectionsPtr);
        int count = 0;
        std::uint32_t entries = 0;
        if (table >= 0x08000000u) {
            count = static_cast<int>(m.u32(table));
            entries = m.u32(table + 4);
            if (count < 0 || count > 8 || entries < 0x08000000u) count = 0;
        }
        for (int i = 0; i < count; ++i) {
            const std::uint32_t c = entries + static_cast<std::uint32_t>(i) * kMapConnectionSize;
            NavState::ConnEdge e;
            e.direction = m.u8(c);
            e.mapGroup = m.u8(c + 8);
            e.mapNum = m.u8(c + 9);
            const int px = n.x - kMapOffset, py = n.y - kMapOffset;
            switch (e.direction) {
                case kConnNorth: e.dist = (height > 0) ? py : -1; break;
                case kConnSouth: e.dist = (height > 0) ? height - 1 - py : -1; break;
                case kConnWest:  e.dist = (width > 0) ? px : -1; break;
                case kConnEast:  e.dist = (width > 0) ? width - 1 - px : -1; break;
                default: e.dist = -1; break;   // dive/emerge: not a walkable edge
            }
            if (e.mapGroup == 127 || e.mapNum == 127) continue;
            n.conns[n.connCount++] = e;
        }
        // Say out loud what the header actually contained, once per map, when
        // asked: a silent zero here looks exactly like a map with no roads.
        static int dbg_group = -1, dbg_num = -1;
        if (std::getenv("EMERALD_NAV_DEBUG") && (dbg_group != n.mapGroup || dbg_num != n.mapNum)) {
            dbg_group = n.mapGroup;
            dbg_num = n.mapNum;
            std::fprintf(stderr,
                         "[emerald:a11y] conns: map (%d,%d) table=0x%08X count=%d "
                         "width=%d height=%d kept=%d\n",
                         n.mapGroup, n.mapNum, table, count, width, height, n.connCount);
            for (int i = 0; i < n.connCount; ++i)
                std::fprintf(stderr, "[emerald:a11y]   conn dir=%d -> map (%d,%d) dist=%d\n",
                             n.conns[i].direction, n.conns[i].mapGroup, n.conns[i].mapNum,
                             n.conns[i].dist);
        }
    }

    // Object-event coordinates are stored with the field's MAP_OFFSET (7) added
    // (InitObjectEventStateFromTemplate does `template->x + MAP_OFFSET`), while
    // warp events in the ROM table are plain map tiles. Compare in map space or
    // every warp looks seven tiles away and no door is ever in front of you.
    const int map_x = n.x - kMapOffset;
    const int map_y = n.y - kMapOffset;

    int best = -1, best_dist = 1 << 30;
    for (int i = 0; i < n.warpCount; ++i) {
        const int dx = n.warps[i].x - map_x;
        const int dy = n.warps[i].y - map_y;
        const int d = std::abs(dx) + std::abs(dy);
        if (d < best_dist) {
            best_dist = d;
            best = i;
        }
    }
    if (best >= 0) {
        n.nearestWarp = best;
        n.warpDx = n.warps[best].x - map_x;
        n.warpDy = n.warps[best].y - map_y;
        n.warpDist = best_dist;
    }

    // Closest person / item / interactive object on or beside the player.
    int npc_best = 1 << 30;
    for (int i = 0; i < kEventCount; ++i) {
        const std::uint32_t e = addr::gObjectEvents + i * kEventSize;
        const std::uint8_t flags0 = m.u8(e + 0);
        const std::uint8_t flags1 = m.u8(e + 1);
        const std::uint8_t flags2 = m.u8(e + 2);
        if ((flags0 & 0x01) == 0) continue;          // active
        if ((flags1 & 0x60) != 0) continue;          // invisible (0x20) / off-screen (0x40)
        if ((flags2 & 0x01) != 0) continue;          // isPlayer
        if (m.u8(e + kEventMapNum) != n.mapNum) continue;
        if (m.u8(e + kEventMapGroup) != n.mapGroup) continue;
        const int dx = m.s16(e + kEventCoords) - n.x;
        const int dy = m.s16(e + kEventCoords + 2) - n.y;
        const int d = std::abs(dx) + std::abs(dy);
        if (d > 1 || d >= npc_best) continue;        // adjacent only
        npc_best = d;
        n.npcDist = d;
        n.npcDx = dx;
        n.npcDy = dy;
        n.npcGraphics = m.u8(e + kEventGraphics);
        n.npcIsItem = n.npcGraphics == kItemBallGraphics;
        n.npcIsTrainer = m.u8(e + kEventTrainerType) != 0;
    }

    // What the player is looking at: one tile ahead, in the facing direction.
    int ldx = 0, ldy = 0;
    facing_step(n.facing, &ldx, &ldy);
    n.lookX = n.x + ldx;
    n.lookY = n.y + ldy;
    for (int i = 0; i < n.warpCount; ++i) {
        const WarpInfo& w = n.warps[i];
        if (w.x != n.lookX - kMapOffset || w.y != n.lookY - kMapOffset) continue;
        n.lookKind = w.stair ? (w.goesUp ? LookStairsUp : LookStairsDown) : LookDoor;
        break;
    }
    if (n.lookKind == LookNone) {
        for (int i = 0; i < kEventCount; ++i) {
            const std::uint32_t e = addr::gObjectEvents + i * kEventSize;
            const std::uint8_t flags0 = m.u8(e + 0);
            const std::uint8_t flags1 = m.u8(e + 1);
            const std::uint8_t flags2 = m.u8(e + 2);
            if ((flags0 & 0x01) == 0) continue;      // active
            if ((flags1 & 0x30) != 0) continue;      // invisible / off-screen
            if ((flags2 & 0x01) != 0) continue;      // isPlayer
            if (m.u8(e + kEventMapNum) != n.mapNum) continue;
            if (m.u8(e + kEventMapGroup) != n.mapGroup) continue;
            if (m.s16(e + kEventCoords) != n.lookX) continue;
            if (m.s16(e + kEventCoords + 2) != n.lookY) continue;
            n.lookGraphics = m.u8(e + kEventGraphics);
            const bool item = n.lookGraphics == kItemBallGraphics;
            const bool trainer = m.u8(e + kEventTrainerType) != 0;
            n.lookIsTrainer = trainer;
            n.lookKind = item ? LookItem : (trainer ? LookPerson : LookObject);
            break;
        }
    }

    // Background events: the things with no sprite that the game still lets you
    // read by pressing A — signs, the wall clock, the TV. Same rule the engine
    // uses (GetBackgroundEventAtPosition): the faced tile, the player's
    // elevation (or the record's own "any elevation" 0), and the authored
    // facing from the record's kind.
    if (n.lookKind == LookNone && have_events) {
        const int bg_count = m.u8(events + kMapEventsBgCount);
        const std::uint32_t bg_events = m.u32(events + kMapEventsBgEvents);
        for (int i = 0; bg_events >= 0x08000000u && i < bg_count &&
                        i < kBgEventCountMax; ++i) {
            const std::uint32_t b = bg_events + static_cast<std::uint32_t>(i) * kBgEventSize;
            if (m.u16(b + kBgEventX) != n.lookX - kMapOffset) continue;
            if (m.u16(b + kBgEventY) != n.lookY - kMapOffset) continue;
            const int elevation = m.u8(b + kBgEventElevation);
            if (elevation != 0 && elevation != n.elevation) continue;
            const int required = bg_event_required_facing(m.u8(b + kBgEventKind));
            if (required < 0) continue;
            if (required != 0 && required != n.facing) continue;
            if (m.u32(b + kBgEventScript) < 0x08000000u) continue;  // no script: inert
            n.lookKind = LookReadable;
            break;
        }
    }
    return n.ok;
}

std::string nav_json(const NavState& n) {
    std::string out = "{\"ok\":";
    out += n.ok ? "true" : "false";
    out += ",\"map\":[" + std::to_string(n.mapGroup) + "," + std::to_string(n.mapNum) + "]";
    out += ",\"x\":" + std::to_string(n.x) + ",\"y\":" + std::to_string(n.y);
    out += ",\"facing\":\"" + std::string(facing_word(n.facing)) + "\"";
    out += ",\"warp_count\":" + std::to_string(n.warpCount);
    out += ",\"warps\":[";
    for (int i = 0; i < n.warpCount; ++i) {
        if (i) out += ',';
        const WarpInfo& w = n.warps[i];
        out += "{\"x\":" + std::to_string(w.x) + ",\"y\":" + std::to_string(w.y) +
               ",\"elev\":" + std::to_string(w.elevation) + ",\"kind\":\"" +
               (w.stair ? (w.goesUp ? "stairs_up" : "stairs_down") : "door") +
               "\",\"dest\":[" + std::to_string(w.mapGroup) + "," +
               std::to_string(w.mapNum) + "]}";
    }
    out += "]";
    out += ",\"nearest_warp\":";
    if (n.nearestWarp < 0) {
        out += "null";
    } else {
        const WarpInfo& w = n.warps[n.nearestWarp];
        out += "{\"index\":" + std::to_string(n.nearestWarp);
        out += ",\"x\":" + std::to_string(w.x) + ",\"y\":" + std::to_string(w.y);
        out += ",\"kind\":\"";
        out += w.stair ? (w.goesUp ? "stairs_up" : "stairs_down") : "door";
        out += "\",\"direction\":\"" + std::string(compass(n.warpDx, n.warpDy)) + "\"";
        out += ",\"dist\":" + std::to_string(n.warpDist);
        out += ",\"dest\":[" + std::to_string(w.mapGroup) + "," +
               std::to_string(w.mapNum) + "]}";
    }
    out += ",\"look\":{\"kind\":\"";
    switch (n.lookKind) {
        case LookDoor: out += "door"; break;
        case LookStairsUp: out += "stairs_up"; break;
        case LookStairsDown: out += "stairs_down"; break;
        case LookPerson: out += "person"; break;
        case LookItem: out += "item"; break;
        case LookObject: out += "object"; break;
        case LookReadable: out += "readable"; break;
        default: out += "nothing"; break;
    }
    out += "\",\"x\":" + std::to_string(n.lookX) + ",\"y\":" + std::to_string(n.lookY);
    out += ",\"dir\":\"" + std::string(facing_word(n.facing)) + "\"}";
    if (n.npcDist > 0) {
        out += ",\"adjacent\":{\"kind\":\"";
        out += n.npcIsItem ? "item" : (n.npcIsTrainer ? "trainer" : "person");
        out += "\",\"direction\":\"" + std::string(compass(n.npcDx, n.npcDy)) + "\"";
        out += ",\"graphics\":" + std::to_string(n.npcGraphics) + "}";
    }
    out += "}";
    return out;
}

void nav_reset() {
    g_ann = Announcer{};
    g_ann.look_kind = -1;
    g_target = Target{};
}

void nav_set_target(int mapGroup, int mapNum, int x, int y) {
    g_target = Target{};
    g_target.set = true;
    g_target.mapGroup = mapGroup;
    g_target.mapNum = mapNum;
    g_target.x = x;
    g_target.y = y;
}

void nav_clear_target() { g_target = Target{}; }

void nav_frame(const emerald::touch::SceneState& scene, const Mem& m) {
    ++g_ann.frame;
    if (scene.kind != emerald::touch::SceneKind::Overworld) {
        // Leaving the field forgets wording so the next entry restates it.
        g_ann.warp_index = -1;
        return;
    }
    if (scene.menu.live) return;   // a menu is up: the player is not walking
    // A message box means the player is reading (listening to) dialogue. Saying
    // "Object here" over the top of a conversation is the quickest way to make
    // the game unlistenable, so the room stays quiet until the box closes.
    if (m.u8(addr::sFieldMessageBoxMode) != 0) return;

    NavState n;
    if (!read_nav(m, &n) || !n.ok) return;

    // ── New area ─────────────────────────────────────────────────────────
    if (!g_ann.have_map || n.mapGroup != g_ann.mapGroup || n.mapNum != g_ann.mapNum) {
        const bool first = !g_ann.have_map;
        g_ann.have_map = true;
        g_ann.mapGroup = n.mapGroup;
        g_ann.mapNum = n.mapNum;
        g_ann.warp_index = -1;
        if (!first) {
            // "New area." alone tells a player that something changed and not
            // what: walking into a house, a Centre and a gym all sounded the
            // same. The name comes from the compiled table, because the guest
            // keeps none.
            const char* name = map_name_spoken(n.mapGroup, n.mapNum);
            char line[96];
            if (name)
                std::snprintf(line, sizeof(line), "New area. %s.", name);
            else
                std::snprintf(line, sizeof(line), "New area.");
            play_cue(Cue::MapTransition, line);
        }
    }

    // ── Which way leads onward ───────────────────────────────────────────
    // A town's exits are map connections, not warps, so "which road goes
    // where" was the one travel question the mod could not answer. Name the
    // road and its compass side while the player is standing at that edge.
    {
        int pick = -1, best = kConnNoticeTiles + 1;
        for (int i = 0; i < n.connCount; ++i) {
            const int d = n.conns[i].dist;
            if (d >= 0 && d <= kConnNoticeTiles && d < best) {
                best = d;
                pick = i;
            }
        }
        if (pick >= 0) {
            const int dir = n.conns[pick].direction;
            if (g_ann.conn_dir != dir || g_ann.frame - g_ann.conn_frame > 900) {
                const char* word = dir == kConnNorth ? "north"
                                 : dir == kConnSouth ? "south"
                                 : dir == kConnWest ? "west" : "east";
                const char* name = map_name_spoken(n.conns[pick].mapGroup,
                                                   n.conns[pick].mapNum);
                char line[96];
                if (name)
                    std::snprintf(line, sizeof(line), "%s %s.", name, word);
                else
                    std::snprintf(line, sizeof(line), "An opening %s.", word);
                if (play_cue(Cue::MapTransition, line)) {
                    g_ann.conn_dir = dir;      // only when it was really said
                    g_ann.conn_frame = g_ann.frame;
                }
            }
        } else {
            g_ann.conn_dir = -1;    // walked away from the edge: name it again
        }
    }

    // ── Navigation target ───────────────────────────────────────────────
    if (g_target.set && n.mapGroup == g_target.mapGroup &&
        n.mapNum == g_target.mapNum && n.x == g_target.x && n.y == g_target.y) {
        // Only clear the target once the arrival was actually spoken: a cue
        // dropped by a cooldown would otherwise be lost for good.
        if (play_cue(Cue::Target, "You have arrived.")) g_target.set = false;
    }

    // ── What the player is looking at ───────────────────────────────────
    // Only the tile in front: turn to a door and it says so, stand with your
    // back to it and it says nothing. The key includes the tile so walking
    // along a wall of doors does not repeat the same one.
    const bool look_changed = n.lookKind != g_ann.look_kind ||
                              n.lookX != g_ann.look_x || n.lookY != g_ann.look_y;
    if (look_changed) {
        g_ann.look_kind = n.lookKind;
        g_ann.look_x = n.lookX;
        g_ann.look_y = n.lookY;
        switch (n.lookKind) {
            case LookDoor: {
                // Name the destination, so a door is a decision and not a
                // guess: standing in a town's doorway, "where does this go?"
                // is the question a sighted player answers from the sign.
                const char* dest = nullptr;
                for (int i = 0; i < n.warpCount; ++i) {
                    if (n.warps[i].x == n.lookX - kMapOffset &&
                        n.warps[i].y == n.lookY - kMapOffset) {
                        dest = map_name_spoken(n.warps[i].mapGroup, n.warps[i].mapNum);
                        break;
                    }
                }
                std::string say = "Door here.";
                if (dest) say += std::string(" Leads to ") + dest + ".";
                say += " Press A to exit.";
                play_cue(Cue::Door, say.c_str());
                break;
            }
            case LookStairsUp:
                play_cue(Cue::StairsUp, "Stairs up here. Walk onto them.");
                break;
            case LookStairsDown:
                play_cue(Cue::StairsDown, "Stairs down here. Walk onto them.");
                break;
            case LookPerson:
                // A trainer gets its own sound: "someone here" and "someone
                // who will challenge you" are different news.
                if (n.lookIsTrainer) {
                    play_cue(Cue::Trainer, "Trainer here. Press A to talk.");
                } else {
                    play_cue(Cue::Npc, "Person here. Press A to talk.");
                }
                break;
            case LookItem:
                play_cue(Cue::Item, "Item here. Press A to pick it up.");
                break;
            case LookObject:
                if (n.lookGraphics == kPushableBoulderGraphics) {
                    play_cue(Cue::Object, "Boulder here. Face it and use Strength to push it.");
                } else if (n.lookGraphics == kBreakableRockGraphics) {
                    play_cue(Cue::Object, "Cracked rock here. Use Rock Smash on it.");
                } else {
                    play_cue(Cue::Object, "Object here. Press A.");
                }
                break;
            case LookReadable:
                // A sign, the wall clock, the TV: the game has text for it but
                // no sprite, so naming the kind would be a guess. What matters
                // is that there is something to read on this tile. Its own
                // sound keeps it apart from the things you interact with.
                play_cue(Cue::Sign, "Something to read here. Press A.");
                break;
            default:
                break;   // nothing in front: silence
        }
    }

    // The facing line already covers whatever is directly in front, so the
    // longer-range hints below skip that one and describe the rest.
    const bool look_is_warp = n.nearestWarp >= 0 && n.lookKind != LookNone &&
        n.warps[n.nearestWarp].x == n.lookX - kMapOffset &&
        n.warps[n.nearestWarp].y == n.lookY - kMapOffset;
    const bool look_is_npc = n.npcDist > 0 && n.lookKind != LookNone &&
        n.lookX == n.x + n.npcDx && n.lookY == n.y + n.npcDy;

    // ── Exits ────────────────────────────────────────────────────────────
    if (n.nearestWarp >= 0 && n.warpDist <= kWarpNoticeTiles && !look_is_warp) {
        const WarpInfo& w = n.warps[n.nearestWarp];
        // Announce a door when it becomes the nearest one; standing next to it
        // is not news and the player asked not to be nagged.
        const bool again = n.nearestWarp != g_ann.warp_index;
        if (again) {
            g_ann.warp_index = n.nearestWarp;
            g_ann.warp_frame = g_ann.frame;
            const std::string where = compass(n.warpDx, n.warpDy);
            const std::string steps = n.warpDist == 1
                ? std::string("one step ")
                : (n.warpDist == 2 ? std::string("two steps ") : std::string());
            if (w.stair) {
                const std::string say = join("Stairs ", steps + where + ". Walk onto them.", "");
                play_cue(w.goesUp ? Cue::StairsUp : Cue::StairsDown, say.c_str());
            } else {
                std::string say = join("Door ", steps + where + ".", "");
                const char* dest = map_name_spoken(w.mapGroup, w.mapNum);
                if (dest) say += std::string(" Leads to ") + dest + ".";
                say += " Press A to exit.";
                play_cue(Cue::Door, say.c_str());
            }
        }
    } else if (n.nearestWarp >= 0 && n.warpDist > kWarpNoticeTiles + 1) {
        g_ann.warp_index = -1;   // walked away: re-announce on the next approach
    }

    // ── People, items and interactive objects ────────────────────────────
    const int npc_kind = n.npcIsItem ? 2 : (n.npcIsTrainer ? 1 : 0);
    const bool npc_changed = n.npcDist > 0 &&
        (n.npcDx != g_ann.npc_dx || n.npcDy != g_ann.npc_dy || npc_kind != g_ann.npc_kind);
    if (look_is_npc) {
        g_ann.npc_dx = n.npcDx;      // the facing line has it; don't repeat it
        g_ann.npc_dy = n.npcDy;
        g_ann.npc_kind = npc_kind;
    }
    if (n.npcDist > 0 && !look_is_npc && npc_changed) {
        g_ann.npc_frame = g_ann.frame;
        g_ann.npc_dx = n.npcDx;
        g_ann.npc_dy = n.npcDy;
        g_ann.npc_kind = npc_kind;
        const std::string where = compass(n.npcDx, n.npcDy);
        if (n.npcIsItem) {
            const std::string say =
                join("Item ", where + ". Press A to pick it up.", "");
            play_cue(Cue::Item, say.c_str());
        } else if (n.npcIsTrainer) {
            const std::string say = join("Trainer ", where + ". Press A to talk.", "");
            play_cue(Cue::Trainer, say.c_str());
        } else if (n.npcGraphics == kMovingBoxGraphics) {
            const std::string say = join("Box ", where + ". Press A.", "");
            play_cue(Cue::Object, say.c_str());
        } else if (n.npcGraphics == kPushableBoulderGraphics) {
            const std::string say = join("Boulder ", where + ". Face it and use Strength to push it.", "");
            play_cue(Cue::Object, say.c_str());
        } else if (n.npcGraphics == kBreakableRockGraphics) {
            const std::string say = join("Cracked rock ", where + ". Use Rock Smash on it.", "");
            play_cue(Cue::Object, say.c_str());
        } else {
            const std::string say = join("Person ", where + ". Press A to talk.", "");
            play_cue(Cue::Npc, say.c_str());
        }
    }
}

}  // namespace emerald::accessibility

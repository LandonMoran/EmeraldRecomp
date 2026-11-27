// emerald_devtools.cpp — developer-only teleport and field diagnostics.
// See emerald_devtools.h for why the warp uses the warp record + CB2_LoadMap
// instead of writing the player's coordinates.
//
// Everything in this file is compiled only with -DEMERALD_DEVTOOLS=ON.

#include "emerald_devtools.h"

#if defined(EMERALD_DEVTOOLS)

#include <cstdio>
#include <cstring>
#include <string>

#include "accessibility/emerald_nav.h"
#include "accessibility/emerald_puzzle.h"
#include "mini_json.h"
#include "runtime_arm.h"          // bus_write_u8
#include "touch/emerald_guest.h"
#include "touch/emerald_touch.h"  // core().synth, core().frame

namespace emerald::dev {
namespace {

namespace addr = emerald::guest::addr;
namespace a11y = emerald::accessibility;
using emerald::guest::Mem;

// Field entry points (pokeemerald, pinned revision; Thumb bit set).
constexpr std::uint32_t kCb2LoadMap = 0x08085FCD;    // CB2_LoadMap
constexpr std::uint32_t kCb1Overworld = 0x08085E04;  // CB1_Overworld
constexpr std::uint32_t kCb2Overworld = 0x08085E5C;  // CB2_Overworld

// SaveBlock1 field offsets (include/global.h, struct SaveBlock1).
constexpr std::uint32_t kPos = 0x00;
constexpr std::uint32_t kLocation = 0x04;
constexpr std::uint32_t kContinueGameWarp = 0x0C;
constexpr std::uint32_t kFlags = 0x1270;
constexpr std::uint32_t kVars = 0x139C;
constexpr int kFlagCount = 0x400 * 8;      // FLAGS_COUNT
constexpr int kVarFirst = 0x4000;          // VAR_0x4000
constexpr int kVarCount = 256;             // VARS_COUNT

constexpr int kWarpIdNone = 0xFF;
constexpr int kLoadDeadlineFrames = 900;   // 15 s at 60 Hz
constexpr int kTurnSettleFrames = 10;

void put8(std::uint32_t address, std::uint8_t value) { bus_write_u8(address, value); }
void put16(std::uint32_t address, std::uint16_t value) {
    put8(address, static_cast<std::uint8_t>(value & 0xFF));
    put8(address + 1, static_cast<std::uint8_t>(value >> 8));
}
void put32(std::uint32_t address, std::uint32_t value) {
    for (int i = 0; i < 4; ++i)
        put8(address + static_cast<std::uint32_t>(i),
             static_cast<std::uint8_t>((value >> (8 * i)) & 0xFF));
}

std::uint32_t saveblock() {
    const Mem m = Mem::current();
    return m.u32(addr::gSaveBlock1Ptr);
}

bool valid_saveblock(std::uint32_t sb1) {
    return sb1 >= 0x02000000u && sb1 < 0x02040000u;
}

struct Location {
    int mapGroup = -1, mapNum = -1, warpId = -1, x = 0, y = 0;
};

Location read_location(const Mem& m, std::uint32_t sb1, std::uint32_t offset) {
    Location l;
    l.mapGroup = m.s8(sb1 + offset + 0);
    l.mapNum = m.s8(sb1 + offset + 1);
    l.warpId = m.u8(sb1 + offset + 2);
    l.x = m.s16(sb1 + offset + 4);
    l.y = m.s16(sb1 + offset + 6);
    return l;
}

// Facing codes are the engine's: 1 south, 2 north, 3 west, 4 east.
int facing_from_text(const std::string& text, int fallback) {
    if (text.empty()) return fallback;
    if (text == "south" || text == "down") return 1;
    if (text == "north" || text == "up") return 2;
    if (text == "west" || text == "left") return 3;
    if (text == "east" || text == "right") return 4;
    return fallback;
}

const char* facing_name(int facing) {
    switch (facing) {
        case 1: return "south";
        case 2: return "north";
        case 3: return "west";
        case 4: return "east";
        default: return "unknown";
    }
}

std::uint16_t facing_key(int facing) {
    switch (facing) {
        case 1: return gbarecomp::kGbaKeyDown;
        case 2: return gbarecomp::kGbaKeyUp;
        case 3: return gbarecomp::kGbaKeyLeft;
        default: return gbarecomp::kGbaKeyRight;
    }
}

// ── Warp job ─────────────────────────────────────────────────────────────

struct WarpJob {
    bool active = false;
    bool done = false;
    bool ok = false;
    int group = 0, num = 0, x = 0, y = 0, facing = 0;
    int stage = 0;          // 1 loading, 2 turning, 3 settling
    int timer = 0;
    std::uint64_t deadline = 0;
    std::string detail;
};
WarpJob g_warp;

void finish(bool ok, const std::string& detail) {
    g_warp.done = true;
    g_warp.ok = ok;
    g_warp.stage = 0;
    g_warp.detail = detail;
}

std::string location_json(const Location& l) {
    char buf[128];
    std::snprintf(buf, sizeof(buf), "{\"map\":[%d,%d],\"x\":%d,\"y\":%d,\"warp_id\":%d}",
                  l.mapGroup, l.mapNum, l.x, l.y, l.warpId);
    return buf;
}

// ── Reads used by the diagnostics ────────────────────────────────────────

std::string state_json() {
    const Mem m = Mem::current();
    const std::uint32_t sb1 = m.u32(addr::gSaveBlock1Ptr);
    std::string out = "{\"ok\":true";
    if (valid_saveblock(sb1)) {
        const Location location = read_location(m, sb1, kLocation);
        const Location cont = read_location(m, sb1, kContinueGameWarp);
        char buf[256];
        std::snprintf(buf, sizeof(buf),
                      ",\"saveblock\":%u,\"pos\":[%d,%d],\"location\":%s,"
                      "\"continue\":%s,\"callback1\":%u,\"callback2\":%u,"
                      "\"script_status\":%u,\"controls_locked\":%u,\"message_box\":%u",
                      sb1, m.s16(sb1 + kPos), m.s16(sb1 + kPos + 2),
                      location_json(location).c_str(), location_json(cont).c_str(),
                      m.u32(addr::gMain) & ~1u, m.u32(addr::gMain + 4) & ~1u,
                      m.u32(addr::sGlobalScriptContextStatus), m.u8(addr::sLockFieldControls),
                      m.u8(addr::sFieldMessageBoxMode));
        out += buf;

        const int id = m.u8(addr::gPlayerAvatar + 5);
        if (id < 16) {
            const std::uint32_t o = addr::gObjectEvents + static_cast<std::uint32_t>(id) * 0x24;
            char obj[192];
            std::snprintf(obj, sizeof(obj),
                          ",\"object\":{\"x\":%d,\"y\":%d,\"map\":[%u,%u],"
                          "\"facing\":\"%s\",\"elevation\":%u}",
                          m.s16(o + 0x10), m.s16(o + 0x12), m.u8(o + 0x0A), m.u8(o + 0x09),
                          facing_name(m.u8(o + 0x18) & 0x0F), m.u8(o + 0x0B) & 0x0F);
            out += obj;
        }
    } else {
        out += ",\"saveblock\":0";
    }

    a11y::PuzzleState puzzle;
    if (a11y::read_puzzle(m, &puzzle)) {
        out += ",\"puzzle\":";
        out += a11y::puzzle_json(puzzle);
    }
    a11y::NavState nav;
    if (a11y::read_nav(m, &nav)) {
        out += ",\"nav\":";
        out += a11y::nav_json(nav);
    }

    out += ",\"warp\":{\"active\":";
    out += g_warp.active && !g_warp.done ? "true" : "false";
    out += ",\"done\":";
    out += g_warp.done ? "true" : "false";
    out += ",\"ok\":";
    out += g_warp.ok ? "true" : "false";
    out += ",\"detail\":";
    gbarecomp::json::append_quoted(out, g_warp.detail);
    out += "}";
    out += "}";
    return out;
}

// ── Commands ─────────────────────────────────────────────────────────────

void command_warp(const gbarecomp::json::Value& req, std::string* out) {
    const Mem m = Mem::current();
    const std::uint32_t sb1 = m.u32(addr::gSaveBlock1Ptr);
    if (!valid_saveblock(sb1)) {
        *out = gbarecomp::json::error_reply("no save block: the game is not in the field yet");
        return;
    }
    const int group = static_cast<int>(req.integer("map_group", -1));
    const int num = static_cast<int>(req.integer("map_num", -1));
    const int x = static_cast<int>(req.integer("x", -1));
    const int y = static_cast<int>(req.integer("y", -1));
    if (group < 0 || group > 127 || num < 0 || num > 255) {
        *out = gbarecomp::json::error_reply("map_group (0-127) and map_num (0-255) required");
        return;
    }
    if (x < 0 || x > 255 || y < 0 || y > 255) {
        *out = gbarecomp::json::error_reply("x and y are map tiles, 0-255");
        return;
    }

    // Refuse only while the game is showing text: warping out from under a line
    // the player is reading would be a surprise. A waiting script context is
    // normal on the field (the opening truck sequence holds one for minutes),
    // and replacing the field callback is exactly what a warp does, so it is
    // allowed — the checkpoint taken before the warp is the safety net.
    if (m.u8(addr::sFieldMessageBoxMode) != 0) {
        *out = gbarecomp::json::error_reply("a message box is open; finish reading it first");
        return;
    }
    // A scripted walk owns the player through gPlayerAvatar.flags &
    // PLAYER_AVATAR_FLAG_FORCED_MOVE (0x20). Loading a map from under it carries
    // the flag onto the new map, where the field ignores every D-pad press — the
    // warp would appear to work and the game would be unplayable. Refuse instead
    // and let the caller finish the scene.
    if (m.u8(addr::gPlayerAvatar) & 0x20) {
        *out = gbarecomp::json::error_reply(
            "a scripted walk is in progress; wait for the field to hand control back");
        return;
    }

    const int warp_id = static_cast<int>(req.integer("warp_id", kWarpIdNone));
    const int facing = facing_from_text(req.str("facing"), 0);

    // The warp record, written where SetWarpDestination/ApplyCurrentWarp put it.
    put16(sb1 + kPos, static_cast<std::uint16_t>(x));
    put16(sb1 + kPos + 2, static_cast<std::uint16_t>(y));
    for (std::uint32_t base : {kLocation, kContinueGameWarp}) {
        put8(sb1 + base + 0, static_cast<std::uint8_t>(group));
        put8(sb1 + base + 1, static_cast<std::uint8_t>(num));
        put8(sb1 + base + 2, static_cast<std::uint8_t>(warp_id));
        put8(sb1 + base + 3, 0);
        put16(sb1 + base + 4, static_cast<std::uint16_t>(x));
        put16(sb1 + base + 6, static_cast<std::uint16_t>(y));
    }

    // Then the game's own map load. CB2_LoadMap clears the field callbacks,
    // resets the script context, unlocks field controls and chains
    // CB2_DoChangeMap -> CB2_LoadMap2 -> DoMapLoadLoop, which runs the map's
    // on-transition and on-load scripts before returning to CB1/CB2_Overworld.
    put32(addr::gMain, 0);
    put32(addr::gMain + 4, kCb2LoadMap);

    g_warp = WarpJob{};
    g_warp.active = true;
    g_warp.group = group;
    g_warp.num = num;
    g_warp.x = x;
    g_warp.y = y;
    g_warp.facing = facing;
    g_warp.stage = 1;
    g_warp.deadline = emerald::touch::core().frame + kLoadDeadlineFrames;
    g_warp.detail = "loading";

    char buf[192];
    std::snprintf(buf, sizeof(buf),
                  "{\"ok\":true,\"pending\":true,\"requested\":{\"map\":[%d,%d],"
                  "\"x\":%d,\"y\":%d,\"facing\":\"%s\"}}",
                  group, num, x, y, facing_name(facing));
    *out = buf;
}

void command_var(const gbarecomp::json::Value& req, std::string* out) {
    const std::uint32_t sb1 = saveblock();
    if (!valid_saveblock(sb1)) {
        *out = gbarecomp::json::error_reply("no save block");
        return;
    }
    const Mem m = Mem::current();
    const int id = static_cast<int>(req.integer("id", -1));
    if (id < kVarFirst || id >= kVarFirst + kVarCount) {
        *out = gbarecomp::json::error_reply("var id must be 0x4000-0x40FF");
        return;
    }
    const std::uint32_t at = sb1 + kVars + static_cast<std::uint32_t>(id - kVarFirst) * 2;
    if (req.integer("set", -1) >= 0) {
        put16(at, static_cast<std::uint16_t>(req.integer("set", 0)));
    }
    char buf[96];
    std::snprintf(buf, sizeof(buf), "{\"ok\":true,\"var\":%d,\"value\":%u}", id,
                  m.u16(at));
    *out = buf;
}

void command_flag(const gbarecomp::json::Value& req, std::string* out) {
    const std::uint32_t sb1 = saveblock();
    if (!valid_saveblock(sb1)) {
        *out = gbarecomp::json::error_reply("no save block");
        return;
    }
    const Mem m = Mem::current();
    const int id = static_cast<int>(req.integer("id", -1));
    if (id < 0 || id >= kFlagCount) {
        *out = gbarecomp::json::error_reply("flag id out of range");
        return;
    }
    const std::uint32_t at = sb1 + kFlags + static_cast<std::uint32_t>(id / 8);
    const std::uint8_t bit = static_cast<std::uint8_t>(1u << (id & 7));
    const int set = static_cast<int>(req.integer("set", -1));
    if (set >= 0) {
        const std::uint8_t now = m.u8(at);
        put8(at, static_cast<std::uint8_t>(set ? (now | bit) : (now & ~bit)));
    }
    char buf[96];
    std::snprintf(buf, sizeof(buf), "{\"ok\":true,\"flag\":%d,\"value\":%s}", id,
                  (m.u8(at) & bit) ? "true" : "false");
    *out = buf;
}

}  // namespace

bool enabled() { return true; }

int tcp_command(const char* request, void (*write)(void*, const char*, std::size_t),
                void* ctx) {
    if (!request || !std::strstr(request, "\"emerald_dev")) return 0;
    gbarecomp::json::Value req;
    if (!gbarecomp::json::parse(request, req) || !req.is_object()) return 0;
    const std::string cmd = req.str("cmd");
    std::string out;
    if (cmd == "emerald_dev_warp") {
        command_warp(req, &out);
    } else if (cmd == "emerald_dev_state") {
        out = state_json();
    } else if (cmd == "emerald_dev_var") {
        command_var(req, &out);
    } else if (cmd == "emerald_dev_flag") {
        command_flag(req, &out);
    } else if (cmd == "emerald_dev_reset") {
        g_warp = WarpJob{};
        out = "{\"ok\":true}";
    } else {
        out = gbarecomp::json::error_reply("unknown emerald_dev command");
    }
    write(ctx, out.data(), out.size());
    return 1;
}

void frame() {
    if (!g_warp.active || g_warp.done) return;
    const Mem m = Mem::current();
    const std::uint32_t sb1 = m.u32(addr::gSaveBlock1Ptr);
    if (!valid_saveblock(sb1)) return;
    const std::uint64_t now = emerald::touch::core().frame;
    const Location location = read_location(m, sb1, kLocation);
    const int px = m.s16(sb1 + kPos);
    const int py = m.s16(sb1 + kPos + 2);
    const std::uint32_t cb1 = m.u32(addr::gMain) & ~1u;
    const bool arrived = location.mapGroup == g_warp.group &&
                         location.mapNum == g_warp.num && px == g_warp.x &&
                         py == g_warp.y && cb1 == kCb1Overworld;

    switch (g_warp.stage) {
        case 1:
            if (arrived) {
                if (g_warp.facing) {
                    g_warp.stage = 2;
                } else {
                    char buf[160];
                    std::snprintf(buf, sizeof(buf),
                                  "at map [%d,%d] (%d,%d)", location.mapGroup,
                                  location.mapNum, px, py);
                    finish(true, buf);
                }
            } else if (now > g_warp.deadline) {
                char buf[192];
                std::snprintf(buf, sizeof(buf),
                              "map load did not finish: want [%d,%d] (%d,%d), at [%d,%d] (%d,%d)",
                              g_warp.group, g_warp.num, g_warp.x, g_warp.y,
                              location.mapGroup, location.mapNum, px, py);
                finish(false, buf);
            }
            break;
        case 2: {
            // Turn in place with the game's own input: a one-frame press turns
            // the player without taking a step. Writing the facing byte would
            // leave the sprite and the field state disagreeing.
            if (!emerald::touch::core().synth.idle()) break;
            emerald::touch::core().synth.tap(facing_key(g_warp.facing), 1, 2);
            g_warp.stage = 3;
            g_warp.timer = 0;
            break;
        }
        case 3: {
            if (++g_warp.timer < kTurnSettleFrames) break;
            const int id = m.u8(addr::gPlayerAvatar + 5);
            const int facing = id < 16
                ? (m.u8(addr::gObjectEvents + static_cast<std::uint32_t>(id) * 0x24 + 0x18) & 0x0F)
                : 0;
            char buf[192];
            std::snprintf(buf, sizeof(buf), "at map [%d,%d] (%d,%d) facing %s%s",
                          location.mapGroup, location.mapNum, px, py, facing_name(facing),
                          facing == g_warp.facing ? "" : " (turn not applied)");
            finish(true, buf);
            break;
        }
        default: break;
    }
}

void reset() { g_warp = WarpJob{}; }

}  // namespace emerald::dev

#endif  // EMERALD_DEVTOOLS

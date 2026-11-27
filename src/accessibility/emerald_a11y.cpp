// emerald_a11y.cpp — spoken UI for Pokémon Emerald. See emerald_a11y.h.
//
// Everything here reads guest state through emerald::guest::Mem (bounds-checked,
// read-only) and steers the game only with synthesized key presses, exactly
// like the touch policy. Speech content comes from three sources:
//
//   1. The text printer. AddTextPrinter (0x0800467C) receives a stack-built
//      TextPrinterTemplate whose first field is the string the game is about to
//      draw. Hooking its entry captures dialogue, battle messages, map-name
//      banners and menu labels as the game itself spells them, before the
//      typewriter animation advances. Field messages and battle messages do not
//      go through AddTextPrinterParameterized, so the template entry point is
//      the only hook that sees all of them.
//   2. ListMenu item name pointers (task data + 0x08), which give real item
//      names for the bag, shops and PC lists.
//   3. Battle state: action/move/target cursors, move names, types and PP.

#include "emerald_a11y.h"

#include "emerald_cues.h"    // audio cues + interaction outcomes
#include "emerald_hotkeys.h"  // pad commands, chord decoding
#include "emerald_nav.h"     // exits, stairs, adjacent people/items
#include "emerald_settings.h"  // pad-editable spoken settings

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <deque>
#include <functional>
#include <mutex>
#include <string>
#include <vector>

#include "touch/emerald_guest.h"
#include "mini_json.h"
#include "mod_function_hooks.h"
#include "mod_runtime.h"        // the same mod state the Mods menu edits
#include "runtime_arm.h"
#if __has_include("recomp_launcher.h")
#include "recomp_launcher.h"    // RecompLauncherCModProvider (feature_set_option)
#define EMERALD_HAS_MOD_PROVIDER 1
#else
#define EMERALD_HAS_MOD_PROVIDER 0
#endif
#include "touch/emerald_touch.h"
#include "emerald_state_slots.h"
#include "runtime_bus_bridge.h"   // g_runtime_state_epoch (bumped on restore)

#include <filesystem>
#include <system_error>

namespace emerald::accessibility {

namespace {

namespace k = gbarecomp;
namespace guest = emerald::guest;
using guest::Mem;
using emerald::touch::BattleControl;
using emerald::touch::Core;
using emerald::touch::ListState;
using emerald::touch::MenuState;
using emerald::touch::SceneKind;
using emerald::touch::SceneState;
using emerald::touch::scene_name;
namespace addr = emerald::guest::addr;
namespace off = emerald::guest::off;

constexpr int kMaxItems = 32;
// One printed page of Emerald text is up to ~600 characters (Birch's world
// speech is 431). Cutting at 400 stopped a sentence mid-word ("…I've been"),
// so the cap sits above a full page; Android's TTS takes 4000 per utterance.
constexpr int kMaxText = 1000;

const char* scene_speech_name(SceneKind kind);   // defined below

// ── Speech sink ──────────────────────────────────────────────────────────

SpeakFn g_speak_fn = nullptr;
void (*g_stop_fn)() = nullptr;
void (*g_rate_fn)(float) = nullptr;

bool g_enabled = false;
bool g_speak_text = true;
int g_verbosity = 1;   // 0 = menus/battle/screens, 1 = all printed text
float g_rate = 1.0f;

std::uint64_t g_frame = 0;
std::string g_last_spoken;
std::uint64_t g_last_said_frame = 0;
std::string g_message;          // latest spoken game text (for repeat/status)

// ── Diagnostic log (TCP) ─────────────────────────────────────────────────

struct LogEntry {
    std::uint64_t frame = 0;
    std::uint64_t seq = 0;      // monotonic: the ring trims, the numbering does not
    std::string text;
    int interrupt = 0;
};
std::mutex g_log_m;
std::deque<LogEntry> g_log;
std::uint64_t g_log_seq = 0;
constexpr std::size_t kLogSize = 64;

// ── Text captured from AddTextPrinter ────────────────────────────────────

struct PrintEvent {
    std::uint32_t window = 0xFF;
    std::uint32_t y = 0;
    std::uint64_t frame = 0;
    std::string text;                  // whole string, lines joined by '\n'
    std::vector<std::string> lines;    // one entry per printed line
};
std::vector<PrintEvent> g_prints;
// Diagnostics: proves whether the printer hook is being entered at all, which
// is the difference between "the game is silent" and "the hook is dead".
std::uint64_t g_prints_seen = 0;
std::string g_last_print;

// Labels drawn into the current menu window, in draw order. The game prints its
// own option strings (including the player's name in the Start menu), so this
// is the label list without guessing anything.
std::vector<std::string> g_labels;

// ── Watched state ────────────────────────────────────────────────────────

SceneKind g_kind = SceneKind::Unknown;
bool g_had_scene = false;
bool g_surface_changed = false;
std::uint32_t g_surface = 0;

bool g_menu_live = false;
std::uint8_t g_menu_window = 0xFF;
int g_menu_cursor = -9999;

bool g_list_live = false;
std::uint8_t g_list_task = 0xFF;
int g_list_index = -9999;

BattleControl g_control = BattleControl::None;
int g_battle_cursor = -9999;

// Name entry keyboard state (page, cursor, typed name).
bool g_naming_live = false;
int g_naming_page = -1;
int g_naming_row = -9999;
int g_naming_column = -9999;
bool g_naming_button = false;
std::string g_naming_typed;

bool g_pending_item = false;
int g_pending_deadline = 0;

// ── Navigation ("select this item") ─────────────────────────────────────

struct Nav {
    bool active = false;
    int target = 0;
    std::uint32_t surface = 0;
    int last = -9999;
    int stuck = 0;
} g_nav;

// ── Action queue (UI thread / TCP → emulation thread) ────────────────────

std::mutex g_action_m;
std::deque<std::pair<int, int>> g_actions;

// ── Text decoding ────────────────────────────────────────────────────────

void trim(std::string* s) {
    std::size_t begin = 0, end = s->size();
    while (begin < end && ((*s)[begin] == ' ' || (*s)[begin] == '\n')) ++begin;
    while (end > begin && ((*s)[end - 1] == ' ' || (*s)[end - 1] == '\n')) --end;
    if (begin == 0 && end == s->size()) return;
    *s = s->substr(begin, end - begin);
}

// Gen III charmap → UTF-8, read one byte at a time through the bounds-checked
// bus view. 0xFC/0xFD introduce control codes and string variables; those are
// skipped rather than spelled out.
std::string decode(const Mem& m, std::uint32_t address, std::size_t max_len,
                   bool keep_line_breaks = false) {
    std::string out;
    if (!address) return out;
    for (std::size_t i = 0; i < max_len; ++i) {
        const std::uint8_t c = m.u8(address + static_cast<std::uint32_t>(i));
        if (c == 0xFF) break;
        if (c == 0xFC || c == 0xFD) {
            ++i;
            continue;
        }
        // Line breaks and page breaks are layout, not words: a space keeps
        // "honey!It must be" from running together, and a page break reads as a
        // sentence end so the voice pauses where the game shows a new box.
        if (c == 0xFE || c == 0xFA || c == 0xF9) {
            out += (keep_line_breaks && c == 0xFE) ? '\n' : ' ';
            continue;
        }
        if (c == 0xFB) {
            // Page break: a sentence end, unless the sentence already ended.
            const char last = out.empty() ? ' ' : out.back();
            if (last == '.' || last == '!' || last == '?' || last == '"')
                out += ' ';
            else
                out += ". ";
            continue;
        }
        if (c == 0x00) {
            out += ' ';
        } else if (c >= 0xBB && c <= 0xD4) {
            out += static_cast<char>('A' + (c - 0xBB));
        } else if (c >= 0xD5 && c <= 0xEE) {
            out += static_cast<char>('a' + (c - 0xD5));
        } else if (c >= 0xA1 && c <= 0xAA) {
            out += static_cast<char>('0' + (c - 0xA1));
        } else {
            switch (c) {
                case 0xAB: out += '!'; break;
                case 0xAC: out += '?'; break;
                case 0xAD: out += '.'; break;
                case 0xAE: out += '-'; break;
                case 0xB0: out += "\xE2\x80\xA6"; break;        // …
                case 0xB1: out += "\xE2\x80\x9C"; break;        // “
                case 0xB2: out += "\xE2\x80\x9D"; break;        // ”
                case 0xB3: out += "\xE2\x80\x98"; break;        // ‘
                case 0xB4: out += "\xE2\x80\x99"; break;        // ’
                case 0xB5: out += "\xE2\x99\x82"; break;        // ♂
                case 0xB6: out += "\xE2\x99\x80"; break;        // ♀
                case 0xB8: out += ','; break;
                case 0xBA: out += '/'; break;
                case 0x1B: out += "\xC3\xA9"; break;            // é
                case 0x5C: out += '('; break;
                case 0x5D: out += ')'; break;
                case 0xF0: out += ':'; break;
                default: break;
            }
        }
    }
    trim(&out);
    return out;
}

// ── Speech ───────────────────────────────────────────────────────────────

void log_line(const std::string& text, int interrupt) {
    std::lock_guard<std::mutex> lk(g_log_m);
    g_log.push_back({g_frame, ++g_log_seq, text, interrupt});
    while (g_log.size() > kLogSize) g_log.pop_front();
}

void say(std::string text, bool interrupt) {
    std::string out;
    bool space = false;
    for (char ch : text) {
        if (ch == '\n' || ch == '\r' || ch == '\t') ch = ' ';
        if (ch == ' ') {
            if (!space && !out.empty()) out += ' ';
            space = true;
            continue;
        }
        space = false;
        out += ch;
    }
    trim(&out);
    if (out.empty()) return;
    if (out.size() > kMaxText) {
        out.resize(kMaxText);
        const std::size_t stop = out.find_last_of(".!?");
        if (stop != std::string::npos && stop > out.size() / 2)
            out.resize(stop + 1);      // end on a sentence, not inside a word
        else
            while (!out.empty() &&
                   (static_cast<unsigned char>(out.back()) & 0xC0) == 0x80)
                out.pop_back();
    }
    if (!interrupt && out == g_last_spoken && g_frame - g_last_said_frame < 90) return;
    g_last_spoken = out;
    g_last_said_frame = g_frame;
    log_line(out, interrupt ? 1 : 0);
    if (g_speak_fn) {
        g_speak_fn(out.c_str(), interrupt ? 1 : 0);
    } else {
        std::fprintf(stderr, "[emerald:a11y] speak%s: %s\n", interrupt ? "!" : "",
                     out.c_str());
    }
}

// ── Save states (spoken) ─────────────────────────────────────────────────
//
// The runtime owns save states: the menu rows and the F1..F9 / Shift+F1..F9
// hotkeys both end in one host event (HostWindow::Events::save_slot/
// load_slot), and a game cannot call its snapshot code. So the layer types the
// slot hotkey the host already understands and then reads the file the engine
// wrote (emerald_state_slots.h mirrors the engine's own slot path). The visual
// menu keeps working exactly as it did; this is a second, spoken way in.
//
// A host event queue exists only while the game window runs, which is every
// real session (pad, touch and the menu all arrive through it). Without one the
// layer says save states are unavailable rather than claiming a save happened.

SlotHotkeyFn g_slot_hotkey = nullptr;
LaunchPaths g_paths;          // where this run's slots live (--state-dir / ROM)
int g_state_slot = 1;         // the slot the spoken path uses, 1..9
bool g_state_menu = false;    // the spoken save/load sheet is open

// How long a save or load may take before the layer reports it as failed. The
// engine performs both synchronously at the next present boundary.
constexpr std::uint64_t kStateOpFrames = 120;
// Corner-tap zone: the top-left fifth of the game image. A tap there walks the
// player into the map's corner, which is why it is free to mean "save states".
constexpr float kStateCornerFraction = 0.2f;

struct StateOp {
    bool active = false;
    bool save = false;
    int slot = 0;
    std::uint64_t deadline = 0;
    unsigned long long epoch = 0;  // g_runtime_state_epoch at the request
    std::string path;              // the file this slot names (empty when unknown)
    std::string before;            // its stamp when the request was made
} g_state_op;

// "<mtime>:<size>", or empty when the file is not there. Only a change between
// two reads matters, so the absolute value is not interesting.
std::string slot_stamp(const std::string& path) {
    if (path.empty()) return std::string();
    std::error_code ec;
    const auto stamp = std::filesystem::last_write_time(path, ec);
    if (ec) return std::string();
    const auto size = std::filesystem::file_size(path, ec);
    if (ec) return std::string();
    return std::to_string(
               static_cast<long long>(stamp.time_since_epoch().count())) +
           ":" + std::to_string(static_cast<unsigned long long>(size));
}

void close_state_menu(const char* speech) {
    if (!g_state_menu) return;
    g_state_menu = false;
    if (speech && *speech) say(speech, true);
}

void open_state_menu() {
    g_state_menu = true;
    say(slot_sheet_speech(g_state_slot), true);
}

void begin_state_op(bool save, int slot) {
    slot = clamp_state_slot(slot);
    g_state_slot = slot;
    if (!g_slot_hotkey) {
        say(slot_unavailable_speech(), true);
        return;
    }
    const std::string path = state_slot_path(g_paths.state_dir, g_paths.rom, slot);
    if (!save && !path.empty() && slot_stamp(path).empty()) {
        // Nothing to restore: saying so beats a silent failed load.
        say(slot_missing(slot), true);
        return;
    }
    StateOp op;
    op.active = true;
    op.save = save;
    op.slot = slot;
    op.deadline = g_frame + kStateOpFrames;
    op.epoch = g_runtime_state_epoch;
    op.path = path;
    op.before = save ? slot_stamp(path) : std::string();
    g_state_op = op;
    say(save ? slot_save_request(slot) : slot_load_request(slot), true);
    g_slot_hotkey(slot, save ? 1 : 0);
}

// The confirmation is evidence, not an assumption: a save is done when the
// slot's file changed, a load when the runtime's state epoch moved (it is
// bumped on every restoration, which is why the emulator's own view policy
// watches it too).
void poll_state_op() {
    if (!g_state_op.active) return;
    const int slot = g_state_op.slot;
    if (g_state_op.save) {
        if (!g_state_op.path.empty()) {
            const std::string now = slot_stamp(g_state_op.path);
            if (!now.empty() && now != g_state_op.before) {
                g_state_op.active = false;
                say(slot_saved(slot), true);
                return;
            }
        }
    } else if (g_runtime_state_epoch != g_state_op.epoch) {
        g_state_op.active = false;
        say(slot_loaded(slot), true);
        return;
    }
    if (g_frame >= g_state_op.deadline) {
        const bool save = g_state_op.save;
        const bool known = !g_state_op.path.empty();
        g_state_op.active = false;
        if (known) say(save ? slot_save_failed(slot) : slot_load_failed(slot), true);
    }
}

// Save states are a field action: offering them mid-menu or mid-battle would
// put a state in the middle of a screen the player is reading.
bool state_menu_allowed(const SceneState& s) {
    return s.kind == SceneKind::Overworld && !s.menu.live && !s.list.live &&
           !s.battle.active;
}

bool corner_tap(const gbarecomp::TouchFrameInfo* frame) {
    if (!frame || !frame->gestures) return false;
    const float width =
        frame->view_width ? static_cast<float>(frame->view_width) : 240.0f;
    const float height =
        frame->view_height ? static_cast<float>(frame->view_height) : 160.0f;
    for (std::size_t i = 0; i < frame->gesture_count; ++i) {
        const gbarecomp::Gesture& g = frame->gestures[i];
        if (g.kind != gbarecomp::GestureKind::Tap || !g.start_in_view) continue;
        if (g.start_view_x <= width * kStateCornerFraction &&
            g.start_view_y <= height * kStateCornerFraction)
            return true;
    }
    return false;
}

// While the sheet is open it owns the frame's gestures: tap saves, swipe up
// loads, swipe left/right changes the slot, two-finger tap closes. The frame's
// synthesized keys are dropped so a tap that dismisses the sheet cannot also
// walk the player or confirm a game prompt.
void state_menu_gestures(const gbarecomp::TouchFrameInfo* frame) {
    if (!frame || !frame->gestures) return;
    for (std::size_t i = 0; i < frame->gesture_count; ++i) {
        const gbarecomp::Gesture& g = frame->gestures[i];
        switch (g.kind) {
            case gbarecomp::GestureKind::Tap:
                close_state_menu(nullptr);
                begin_state_op(true, g_state_slot);
                break;
            case gbarecomp::GestureKind::Swipe:
                if (g.swipe == gbarecomp::SwipeDirection::Up) {
                    close_state_menu(nullptr);
                    begin_state_op(false, g_state_slot);
                } else if (g.swipe == gbarecomp::SwipeDirection::Right) {
                    g_state_slot = next_state_slot(g_state_slot);
                    say(slot_sheet_after_slot_speech(g_state_slot), true);
                } else if (g.swipe == gbarecomp::SwipeDirection::Left) {
                    g_state_slot = prev_state_slot(g_state_slot);
                    say(slot_sheet_after_slot_speech(g_state_slot), true);
                } else {
                    close_state_menu("Closed.");
                }
                break;
            case gbarecomp::GestureKind::TwoFingerTap:
            case gbarecomp::GestureKind::Back:
            case gbarecomp::GestureKind::LongPress:
                close_state_menu("Closed.");
                break;
            default: break;
        }
    }
}

// ── Surfaces ─────────────────────────────────────────────────────────────

// Identity of "what the player is choosing on". A change means the captured
// label list belongs to a different menu and must be rebuilt.
std::uint32_t surface_key(const SceneState& s) {
    if (s.menu.live)
        return 0x10000000u | (static_cast<std::uint32_t>(s.menu.window) << 8) |
               (s.start_menu ? 1u : 0u);
    if (s.list.live)
        return 0x20000000u | (static_cast<std::uint32_t>(s.list.task) << 8) | s.list.window;
    if (s.battle.active && s.battle.control != BattleControl::None)
        return 0x30000000u | static_cast<std::uint32_t>(s.battle.control);
    return 0x40000000u | static_cast<std::uint32_t>(s.kind);
}

bool window_is_menu(const SceneState& s, std::uint32_t window) {
    return s.menu.live && window == s.menu.window;
}

bool window_is_list(const SceneState& s, std::uint32_t window) {
    return s.list.live && window == s.list.window;
}

// In a battle, while an input menu is up, every window except the message
// window (B_WIN_MSG = 0) holds menu labels. With no menu up, battle text is
// dialogue.
bool window_is_battle_labels(const SceneState& s, std::uint32_t window) {
    return s.battle.active && s.battle.control != BattleControl::None && window != 0;
}

// ── Labels ───────────────────────────────────────────────────────────────

const char* const kActionLabels[4] = {"Fight", "Bag", "Pok\xC3\xA9mon", "Run"};
const char* const kSafariLabels[4] = {"Ball", "Pok\xC3\xA9" " Block", "Go near", "Run"};

std::string move_name(const Mem& m, int move) {
    if (move <= 0 || move > 354) return {};
    return decode(m, addr::gMoveNames + static_cast<std::uint32_t>(move) * 13, 13);
}

std::string type_name(const Mem& m, int type) {
    if (type < 0 || type > 17) return {};
    return decode(m, addr::gTypeNames + static_cast<std::uint32_t>(type) * 7, 7);
}

// ListMenu item name: the task's ListMenu template starts at the task data
// (task + 8); items (const struct ListMenuItem *) is its first field and each
// entry is 8 bytes { const u8 *name; s32 id; }.
std::string list_item_name(const Mem& m, const ListState& l, int index) {
    if (index < 0 || index >= l.total) return {};
    const std::uint32_t task = addr::gTasks + static_cast<std::uint32_t>(l.task) * off::kTaskSize;
    const std::uint32_t items = m.u32(task + 0x08);
    if (!items || !m.ptr(items, 8)) return {};
    const std::uint32_t name = m.u32(items + static_cast<std::uint32_t>(index) * 8u);
    if (!name || !m.ptr(name, 1)) return {};
    return decode(m, name, 24);
}

std::string menu_label(const MenuState& menu, int index) {
    const int slot = index - menu.min;
    if (slot >= 0 && slot < static_cast<int>(g_labels.size())) return g_labels[slot];
    return {};
}

std::string action_label(BattleControl control, int index) {
    if (index < 0 || index > 3) return {};
    return (control == BattleControl::SafariAction ? kSafariLabels : kActionLabels)[index];
}

std::string move_speech(const Mem& m, const emerald::touch::BattleState& b, int slot) {
    const std::uint32_t mon = addr::gBattleMons + static_cast<std::uint32_t>(b.battler) * 0x58;
    const int move = m.u16(mon + 0x0C + 2 * slot);
    if (!move) return "Empty slot.";
    std::string out = move_name(m, move);
    if (out.empty()) out = "Move";
    const std::uint32_t mv = addr::gBattleMoves + static_cast<std::uint32_t>(move) * 12;
    const std::string type = type_name(m, m.u8(mv + 2));
    const int base_pp = m.u8(mv + 4);
    const int bonus = (m.u8(mon + 0x3B) >> (2 * slot)) & 3;
    const int max_pp = base_pp + base_pp * 20 * bonus / 100;
    char tail[64];
    std::snprintf(tail, sizeof(tail), ", %s, PP %d of %d.", type.empty() ? "unknown type"
                                                                        : type.c_str(),
                  m.u8(mon + 0x24 + slot), max_pp);
    return out + tail;
}

std::string target_speech(const Mem& m, int battler) {
    const std::uint32_t mon = addr::gBattleMons + static_cast<std::uint32_t>(battler) * 0x58;
    std::string name = decode(m, mon + 0x30, 11);
    if (name.empty()) name = "Pokémon";
    return name + ((m.u8(addr::gBattlerPositions + battler) & 1) ? ", foe" : ", ally");
}

// ── Name entry ───────────────────────────────────────────────────────────

// The naming screen is the one screen the touch policy cannot describe as a
// menu or a list: it is a three-page keyboard the game draws from its own ROM
// tables, and the cursor's row and column are the cursor sprite's data fields.
// Reading those is enough to say what the cursor is on, exactly as the screen
// shows it. Nothing is written: the player moves the cursor with the pad and
// presses A, as a sighted player does, and speech follows the cursor.
struct NamingKey {
    bool valid = false;
    bool button = false;   // cursor is in the button column
    int page = 0;          // KBPAGE_*: 0 symbols, 1 upper case, 2 lower case
    int keyboard = 1;      // KEYBOARD_*: 0 lower, 1 upper, 2 symbols
    int row = 0;
    int column = 0;
    int columns = 8;       // keys in this page's rows; the buttons sit past it
    std::string key;       // the character or button under the cursor
};

// Struct NamingScreenData offsets (pinned decomp revision).
constexpr std::uint32_t kNamingTextBuffer = 0x1800;   // u8[16], game charset
constexpr std::uint32_t kNamingCurrentPage = 0x1E22;  // u8
constexpr std::uint32_t kNamingCursorSprite = 0x1E23; // u8 sprite id
constexpr std::uint32_t kSpriteData = 0x2E;           // struct Sprite::data[0]
constexpr std::uint32_t kSpriteSize = 0x44;

bool naming_state(const Mem& m, NamingKey* out) {
    const std::uint32_t data = m.u32(addr::sNamingScreen);
    if (data < 0x02000000u || data >= 0x02040000u) return false;
    const std::uint8_t page = m.u8(data + kNamingCurrentPage);
    if (page > 2) return false;
    const std::uint8_t keyboard = m.u8(addr::sPageToKeyboardId + page);
    if (keyboard > 2) return false;
    const std::uint8_t sprite = m.u8(data + kNamingCursorSprite);
    if (sprite >= 64) return false;
    const std::uint32_t cursor = addr::gSprites +
        static_cast<std::uint32_t>(sprite) * kSpriteSize + kSpriteData;
    const int column = m.s16(cursor);
    const int row = m.s16(cursor + 2);
    const int columns = m.u8(addr::sPageColumnCounts + keyboard);
    if (column < 0 || column > columns || row < 0 || row > 3) return false;
    out->valid = true;
    out->page = page;
    out->keyboard = keyboard;
    out->columns = columns;
    out->column = column;
    out->row = row;
    out->button = column >= columns;
    if (out->button) {
        switch (row) {
            case 0: out->key = "Change page"; break;
            case 1: out->key = "Backspace"; break;
            default: out->key = "OK"; break;
        }
    } else {
        const std::uint32_t index = addr::sKeyboardChars +
            static_cast<std::uint32_t>((keyboard * 4 + row) * 8 + column);
        out->key = decode(m, index, 1);
    }
    return true;
}

std::string naming_page_name(int page) {
    switch (page) {
        case 1: return "Upper case letters";
        case 2: return "Lower case letters";
        default: return "Symbols";
    }
}

// A single character as speech: the letters and digits are read as themselves
// by the synthesizer, the rest by name.
std::string naming_char_speech(const std::string& key) {
    if (key.empty() || key == " ") return "blank";
    if (key == ".") return "period";
    if (key == ",") return "comma";
    if (key == "!") return "exclamation mark";
    if (key == "?") return "question mark";
    if (key == "-") return "hyphen";
    if (key == "/") return "slash";
    if (key == "\xE2\x80\xA6") return "ellipsis";
    if (key == "\xE2\x80\x9C" || key == "\xE2\x80\x9D") return "quote";
    if (key == "\xE2\x80\x98" || key == "\xE2\x80\x99") return "apostrophe";
    if (key == "\xE2\x99\x82") return "male sign";
    if (key == "\xE2\x99\x80") return "female sign";
    return key;
}

std::string naming_typed(const Mem& m) {
    const std::uint32_t data = m.u32(addr::sNamingScreen);
    if (data < 0x02000000u || data >= 0x02040000u) return std::string();
    return decode(m, data + kNamingTextBuffer, 16);
}

// Where the cursor is, in the words a player can act on.
std::string naming_speech(const NamingKey& key, const std::string& typed) {
    std::string out = naming_char_speech(key.key);
    if (!key.button) {
        out += ", row " + std::to_string(key.row + 1) + " of 4, column " +
               std::to_string(key.column + 1) + " of " + std::to_string(key.columns);
    }
    out += ".";
    if (!typed.empty()) out += " Name so far: " + typed + ".";
    return out;
}

int list_index(const ListState& l) { return l.scroll + l.selected; }

// Fill `out` with what the current selection is. Returns false when the label
// could not be resolved (so the caller can wait a frame for captured labels).
bool item_speech(const SceneState& s, const Mem& m, std::string* out) {
    if (s.menu.live) {
        const MenuState& menu = s.menu;
        const int count = menu.max - menu.min + 1;
        const int pos = menu.cursor - menu.min + 1;
        std::string label = menu_label(menu, menu.cursor);
        if (label.empty()) {
            *out = "Option " + std::to_string(pos) + " of " + std::to_string(count) + ".";
            return false;
        }
        *out = label;
        if (count > 2) *out += ", " + std::to_string(pos) + " of " + std::to_string(count);
        *out += ".";
        return true;
    }
    if (s.list.live) {
        const ListState& l = s.list;
        const int index = list_index(l);
        std::string label = list_item_name(m, l, index);
        if (label.empty()) {
            *out = "Item " + std::to_string(index + 1) + " of " + std::to_string(l.total) + ".";
            return false;
        }
        *out = label + ", " + std::to_string(index + 1) + " of " + std::to_string(l.total) + ".";
        return true;
    }
    if (s.battle.active) {
        const auto& b = s.battle;
        switch (b.control) {
            case BattleControl::Action:
            case BattleControl::SafariAction: {
                *out = action_label(b.control, b.action_cursor);
                if (out->empty()) *out = "Choice";
                *out += ", " + std::to_string(b.action_cursor + 1) + " of 4.";
                return true;
            }
            case BattleControl::Move: {
                *out = move_speech(m, b, b.move_cursor) + " " +
                       std::to_string(b.move_cursor + 1) + " of " +
                       std::to_string(std::max(1, static_cast<int>(b.moves)));
                return true;
            }
            case BattleControl::Target: {
                const int count = std::min<int>(4, m.u8(addr::gBattlersCount));
                *out = target_speech(m, b.target_cursor) + ". " +
                       std::to_string(b.target_cursor + 1) + " of " +
                       std::to_string(std::max(1, count)) + ".";
                return true;
            }
            case BattleControl::YesNo:
                *out = b.target_cursor == 0 ? "Yes." : "No.";
                return true;
            case BattleControl::MoveSwitch:
                *out = "Choose a move to forget.";
                return true;
            case BattleControl::Other:
            case BattleControl::None:
                break;
        }
    }
    return false;
}

// ── Status text (what read-status says) ──────────────────────────────────

std::string status_text(const SceneState& s, const Mem& m) {
    if (s.kind == SceneKind::Naming) {
        NamingKey key;
        if (naming_state(m, &key))
            return "Name entry. " + naming_page_name(key.page) + ". " +
                   naming_speech(key, naming_typed(m));
        return "Name entry.";
    }
    std::string what;
    if (s.menu.live || s.list.live || (s.battle.active && s.battle.control != BattleControl::None))
        item_speech(s, m, &what);

    switch (s.kind) {
        case SceneKind::Overworld:
            return what.empty() ? "Overworld." : "Overworld. " + what;
        case SceneKind::Battle:
            return what.empty() ? "Battle." : "Battle. " + what;
        case SceneKind::Bag:
            return what.empty() ? "Bag." : "Bag. " + what;
        case SceneKind::Party:
            return what.empty() ? "Party." : "Party. " + what;
        case SceneKind::TitleMenus:
            return what.empty() ? "Title and main menu." : "Main menu. " + what;
        case SceneKind::Boot:
            return "Starting Pokémon Emerald.";
        default: {
            const char* name = scene_speech_name(s.kind);
            if (!name || !name[0]) return what;
            return what.empty() ? std::string(name) + "." : std::string(name) + ". " + what;
        }
    }
}

// ── Scene/screen speech ──────────────────────────────────────────────────

const char* scene_speech_name(SceneKind kind) {
    switch (kind) {
        case SceneKind::Boot: return "Starting Pokémon Emerald";
        case SceneKind::TitleMenus: return "Title and main menu";
        case SceneKind::Overworld: return "Overworld";
        case SceneKind::Battle: return "Battle";
        case SceneKind::Bag: return "Bag";
        case SceneKind::Party: return "Party";
        case SceneKind::Summary: return "Summary";
        case SceneKind::Storage: return "PC storage";
        case SceneKind::Pokedex: return "Pokédex";
        case SceneKind::Naming: return "Name entry";
        case SceneKind::Shop: return "Shop";
        case SceneKind::Options: return "Options";
        case SceneKind::TrainerCard: return "Trainer card";
        case SceneKind::Pokenav: return "PokéNav";
        case SceneKind::EasyChat: return "Easy chat";
        case SceneKind::FlyMap: return "Fly map";
        case SceneKind::Contest: return "Contest";
        case SceneKind::Blender: return "Berry blender";
        case SceneKind::Slots: return "Slot machine";
        case SceneKind::Roulette: return "Roulette";
        case SceneKind::FactorySelect: return "Battle Factory";
        case SceneKind::PyramidBag: return "Pyramid bag";
        case SceneKind::FrontierPass: return "Frontier pass";
        case SceneKind::Mail: return "Mail";
        case SceneKind::Unknown:
        case SceneKind::Other: return "";
    }
    return "";
}

// A scene is announced when it becomes the screen the player is on, not every
// time the classifier flickers back to it: the title screen and the main menu
// share one kind, so an unnamed frame between them used to make the same line
// play twice. Only a *named* scene counts as having been left.
SceneKind g_announced_kind = SceneKind::Unknown;
bool g_announced_valid = false;
std::uint64_t g_kind_since = 0;   // frame the current scene kind first appeared

void announce_scene(SceneKind kind) {
    const char* name = scene_speech_name(kind);
    if (!name || !name[0]) return;
    if (g_announced_valid && g_announced_kind == kind) return;
    // Emerald runs the post-naming confirmation dialog and the intro movie under
    // the title-screen callback, so the classifier reports the title screen
    // while the professor is still talking. Announcing it there interrupted the
    // conversation with "Title and main menu."; the player has not gone back.
    if (kind == SceneKind::TitleMenus && g_announced_valid &&
        g_announced_kind == SceneKind::Naming)
        return;
    g_announced_kind = kind;
    g_announced_valid = true;
    say(std::string(name) + ".", true);
}

// ── Print capture ────────────────────────────────────────────────────────

// AddTextPrinter receives a whole string, often several lines at once: a Yes/No
// prompt arrives as "YES\nNO", the title menu as "NEW GAME\nOPTION". The lines
// are what the player reads as separate entries, so each one is its own label.
void add_label(const std::string& text) {
    if (text.empty()) return;
    if (g_labels.empty() || g_labels.back() != text) g_labels.push_back(text);
    if (g_labels.size() > static_cast<std::size_t>(kMaxItems))
        g_labels.erase(g_labels.begin());
}

void consume_prints(const SceneState& s, const Mem& m) {
    if (g_prints.empty()) return;
    // The naming screen draws its keyboard through the same printer. Those rows
    // are letters, not sentences, and the naming reader already says the key
    // under the cursor, so nothing printed while it is up is spoken as dialogue.
    if (s.kind == SceneKind::Naming || g_naming_live) { g_prints.clear(); return; }
    {
        NamingKey keyboard;
        if (naming_state(m, &keyboard)) { g_prints.clear(); return; }
    }
    std::string message;
    bool menu_run = false;   // the previous print was a short all-caps block
    std::vector<PrintEvent> later;
    for (const PrintEvent& p : g_prints) {
        if (p.text.empty()) continue;
        // A menu prints its labels on the frame it is built; the classifier sees
        // the live menu on the next frame. One frame of patience is what turns a
        // printed "YES\nNO" from dialogue into that menu's two labels.
        if (g_frame < p.frame + 2) { later.push_back(p); continue; }
        if (window_is_list(s, p.window)) continue;   // names come from ListMenu
        if (window_is_menu(s, p.window) || window_is_battle_labels(s, p.window)) {
            for (const std::string& line : p.lines) add_label(line);
            continue;
        }
        // Battle narration lives in the message window (B_WIN_MSG = 0). Other
        // battle windows hold healthbox and level readouts that repaint as
        // numbers animate, so they are never narrated as dialogue.
        if (s.battle.active && p.window != 0) continue;
        if (!g_speak_text || g_verbosity < 1) continue;
        // A block of short all-capital lines is a menu the game drew itself
        // (the title screen's "NEW GAME" / "OPTION"); read it as a list so the
        // voice does not run the entries together into one phrase. Anything
        // else is prose and keeps ordinary spaces.
        bool menu_block = !p.lines.empty();
        for (const std::string& line : p.lines) {
            if (line.size() > 24) menu_block = false;
            for (char c : line) {
                // Words only: a battle healthbox ("5 17/ 20 TORCHIC") or a
                // Pokédex readout has digits and punctuation and is prose.
                const bool word = (c >= 'A' && c <= 'Z') || c == ' ' || c == '.' ||
                                  c == '!' || c == '?';
                if (!word) menu_block = false;
            }
        }
        bool first_line = true;
        for (const std::string& line : p.lines) {
            if (line.empty()) continue;
            if (line.size() == 1 && !std::isalnum(static_cast<unsigned char>(line[0])))
                continue;   // stray cursor glyphs
            if (!message.empty())
                message += (menu_block && (!first_line || menu_run)) ? ", " : " ";
            message += line;
            first_line = false;
        }
        menu_run = menu_block;
    }
    g_prints.swap(later);
    if (message.empty()) return;
    if (message == g_message) return;
    g_message = message;
    say(message, false);
    // Printed text is how an interaction reports success.
    note_game_text();
}

// Dialogue fallback: the printer entry hook needs a code-generation entry
// guard (see variants/emerald/game.toml); when that guard is absent the hook can
// never run. The game's own message buffer and text printers are always readable,
// so the same sentences are picked up by polling them: while a message box is up
// the box's whole string is already in gStringVar4, before the typewriter draws
// it. Read-only, and it speaks each distinct string once.
void poll_message_text(const SceneState& s, const Mem& m) {
    if (!g_speak_text || g_verbosity < 1) return;
    // Once the printer entry hook has fired, it is the authority: it sees the
    // exact string the game is printing, on the frame it prints it. Polling
    // gStringVar4 as well would repeat the last box's text after every battle
    // message, because the buffer still holds it while another printer draws.
    if (g_prints_seen > 0) return;
    if (s.kind == SceneKind::Unknown || s.kind == SceneKind::Naming) return;

    bool visible = false;
    if (!s.battle.active && m.u8(addr::sFieldMessageBoxMode) != 0) visible = true;
    if (!visible) {
        for (std::uint32_t i = 0; i < 32; ++i) {
            const std::uint32_t p = addr::sTextPrinters +
                i * emerald::guest::off::kTextPrinterSize;
            if (m.u8(p + emerald::guest::off::kTextPrinterActive) == 0) continue;
            if (m.u8(p + emerald::guest::off::kTextPrinterWindow) != 0) continue;  // message window
            visible = true;
            break;
        }
    }
    if (!visible) return;

    // gStringVar4 is 1000 bytes, i.e. at most 500 UTF-16 units. The intro's
    // long page ran past a 400-unit read and was spoken cut off mid-sentence
    // ("...I've been"), so read the whole buffer.
    std::string text = decode(m, addr::gStringVar4, 500);
    while (!text.empty() && text.back() == ' ') text.pop_back();
    if (text.size() < 2) return;
    if (text == g_message) return;
    g_message = text;
    say(text, false);
    note_game_text();
}

// ── Talking to the game (accessibility actions) ──────────────────────────

int battle_cursor(const emerald::touch::BattleState& b) {
    switch (b.control) {
        case BattleControl::Action:
        case BattleControl::SafariAction: return b.action_cursor;
        case BattleControl::Move: return b.move_cursor;
        case BattleControl::Target:
        case BattleControl::YesNo: return b.target_cursor;
        default: return -9999;
    }
}

int surface_cursor(const SceneState& s) {
    if (s.menu.live) return s.menu.cursor;
    if (s.list.live) return list_index(s.list);
    if (s.battle.active) return battle_cursor(s.battle);
    return -9999;
}

int surface_count(const SceneState& s, const Mem& m) {
    if (s.menu.live) return s.menu.max - s.menu.min + 1;
    if (s.list.live) return s.list.total;
    if (s.battle.active) {
        if (s.battle.control == BattleControl::Move)
            return std::max(1, static_cast<int>(s.battle.moves));
        if (s.battle.control == BattleControl::YesNo) return 2;
        if (s.battle.control == BattleControl::Target)
            return std::min<int>(4, m.u8(addr::gBattlersCount));
    }
    return 0;
}

std::uint16_t step_key(const SceneState& s, int current, int target) {
    using namespace gbarecomp;
    if (s.menu.live) {
        const MenuState& menu = s.menu;
        if (menu.grid && menu.columns > 0) {
            if (current / menu.columns != target / menu.columns)
                return target / menu.columns < current / menu.columns ? kGbaKeyUp : kGbaKeyDown;
            return target % menu.columns < current % menu.columns ? kGbaKeyLeft : kGbaKeyRight;
        }
        return target < current ? kGbaKeyUp : kGbaKeyDown;
    }
    if (s.list.live) return target < current ? kGbaKeyUp : kGbaKeyDown;
    if (s.battle.active) {
        if (s.battle.control == BattleControl::Action ||
            s.battle.control == BattleControl::SafariAction ||
            s.battle.control == BattleControl::Move) {
            if ((current & 1) != (target & 1)) return (target & 1) ? kGbaKeyRight : kGbaKeyLeft;
            if ((current & 2) != (target & 2)) return (target & 2) ? kGbaKeyDown : kGbaKeyUp;
            return 0;
        }
        if (s.battle.control == BattleControl::Target) return kGbaKeyRight;
        return target < current ? kGbaKeyUp : kGbaKeyDown;
    }
    return 0;
}

void start_nav(const SceneState& s, const Mem& m, int target) {
    const int count = surface_count(s, m);
    if (count <= 0) return;
    g_nav.active = true;
    g_nav.target = std::max(0, std::min(count - 1, target));
    g_nav.surface = surface_key(s);
    g_nav.last = -9999;
    g_nav.stuck = 0;
}

void nav_frame(Core& c, const SceneState& s) {
    if (!g_nav.active) return;
    if (surface_key(s) != g_nav.surface) {
        g_nav.active = false;
        return;
    }
    const int current = surface_cursor(s);
    if (current < -1000) {
        g_nav.active = false;
        return;
    }
    if (current == g_nav.target) {
        if (c.synth.idle()) c.synth.tap(k::kGbaKeyA, 2, 2);
        g_nav.active = false;
        return;
    }
    g_nav.stuck = current == g_nav.last ? g_nav.stuck + 1 : 0;
    g_nav.last = current;
    if (g_nav.stuck > 6) {
        g_nav.active = false;
        return;
    }
    const std::uint16_t key = step_key(s, current, g_nav.target);
    if (!key) {
        g_nav.active = false;
        return;
    }
    if (c.synth.idle()) c.synth.tap(key, 1, 2);
}

// A pad direction means two different things depending on where you are.
// In a menu it nudges the cursor one place, which is a single-frame tap. In
// the field the game latches a walk from a *held* key and ignores a one-frame
// tap (it only turns you in place), so a pad direction there is a step
// request: hold long enough for one tile, then release. That is also what a
// blind player expects from a swipe -- one gesture, one tile.
constexpr int kStepPressFrames = 16;
// A step that begins by turning spends the turn before it can walk: holding
// only long enough for the walk left the player facing the right way and still
// standing on the same tile (the pad "did nothing" on every change of
// direction). Emerald's turn is ~8 frames, so a step that starts facing the
// wrong way needs the turn plus the walk.
constexpr int kStepTurnFrames = 24;
constexpr int kStepReleaseFrames = 8;

bool field_step_scene(const SceneState& s) {
    return s.kind == SceneKind::Overworld && !s.menu.live && !s.list.live;
}

// How long to hold a pad direction for exactly one tile in the field.
int step_press_for(const Mem& m, bool step, int base, int want_facing) {
    if (!step) return base;
    const int id = m.u8(addr::gPlayerAvatar + 5);
    if (id >= 16) return base;
    const int facing = m.u8(addr::gObjectEvents + id * 0x24 + 0x18) & 0x0F;
    return facing == want_facing ? base : kStepTurnFrames;
}

void consume_actions(Core& c, const SceneState& s, const Mem& m) {
    std::deque<std::pair<int, int>> queued;
    {
        std::lock_guard<std::mutex> lk(g_action_m);
        queued.swap(g_actions);
    }
    const bool step = field_step_scene(s);
    const int dir_press = step ? kStepPressFrames : 1;
    const int dir_release = step ? kStepReleaseFrames : 2;
    for (const auto& [raw, arg] : queued) {
        note_action(raw);   // A/B start an interaction; text (or silence) resolves it
        const Action action = static_cast<Action>(raw);
        switch (action) {
            case Action::Up:
                c.synth.tap(k::kGbaKeyUp, step_press_for(m, step, dir_press, 2), dir_release);
                break;
            case Action::Down:
                c.synth.tap(k::kGbaKeyDown, step_press_for(m, step, dir_press, 1), dir_release);
                break;
            case Action::Left:
                c.synth.tap(k::kGbaKeyLeft, step_press_for(m, step, dir_press, 3), dir_release);
                break;
            case Action::Right:
                c.synth.tap(k::kGbaKeyRight, step_press_for(m, step, dir_press, 4), dir_release);
                break;
            case Action::Confirm: c.synth.tap(k::kGbaKeyA, 2, 2); break;
            case Action::Cancel: c.synth.tap(k::kGbaKeyB, 2, 2); break;
            case Action::Start: c.synth.tap(k::kGbaKeyStart, 2, 2); break;
            case Action::SelectItem: start_nav(s, m, arg); break;
            case Action::NextItem: c.synth.tap(k::kGbaKeyDown, 1, 2); break;
            case Action::PrevItem: c.synth.tap(k::kGbaKeyUp, 1, 2); break;
            case Action::ReadStatus: {
                // Scene + selection, plus the text the game last printed when
                // there is no surface to read (dialogue, cutscene lines): the
                // message is the useful thing to hear again at a prompt.
                std::string text = status_text(s, m);
                if (surface_count(s, m) <= 0 && !g_message.empty()) {
                    if (!text.empty()) text += ' ';
                    text += g_message;
                }
                g_pending_item = false;
                say(text, true);
                break;
            }
            case Action::Repeat:
                if (!g_last_spoken.empty()) say(g_last_spoken, true);
                break;
            case Action::SaveState:
                begin_state_op(true, arg > 0 ? arg : g_state_slot);
                break;
            case Action::LoadState:
                begin_state_op(false, arg > 0 ? arg : g_state_slot);
                break;
            case Action::NextStateSlot:
                g_state_slot = next_state_slot(g_state_slot);
                say(slot_sheet_after_slot_speech(g_state_slot), true);
                break;
            case Action::StateMenu:
                if (g_state_menu)
                    close_state_menu("Closed.");
                else
                    open_state_menu();
                break;
            case Action::StopSpeech:
                g_nav.active = false;
                if (g_stop_fn) g_stop_fn();
                break;
        }
    }
    nav_frame(c, s);
}

// ── Frame ────────────────────────────────────────────────────────────────

void watch(const SceneState& s, const Mem& m) {
    // Surface change: the captured labels belong to the previous menu.
    const std::uint32_t surface = surface_key(s);
    g_surface_changed = surface != g_surface;
    if (g_surface_changed) {
        g_surface = surface;
        g_labels.clear();
        g_pending_item = false;
    }

    // The screen name leads, then the text it printed this frame. A scene is
    // announced once it has *held* for a moment: the classifier briefly reports
    // the title screen between the naming screen and the intro's confirmation
    // dialog, which used to announce "Title and main menu" in the middle of a
    // conversation. Real screens last far longer than this window.
    constexpr std::uint64_t kSceneStableFrames = 24;
    if (!g_had_scene || s.kind != g_kind) {
        g_had_scene = true;
        g_kind = s.kind;
        g_kind_since = g_frame;
    }
    if (g_frame - g_kind_since >= kSceneStableFrames) announce_scene(s.kind);

    consume_prints(s, m);
    poll_message_text(s, m);

    // A battle starting is announced by the game itself — the encounter
    // effect and the battle music — so the layer adds nothing there, exactly as
    // it adds nothing when Emerald plays its own menu and cursor sounds.

    // Menus (Start menu, script multichoice, Yes/No, context menus).
    if (s.menu.live) {
        const bool opened = !g_menu_live || s.menu.window != g_menu_window || g_surface_changed;
        if (opened) {
            g_menu_live = true;
            g_menu_window = s.menu.window;
            std::string text;
            if (!item_speech(s, m, &text)) {
                g_pending_item = true;
                g_pending_deadline = static_cast<int>(g_frame) + 8;
            } else {
                say(text, false);
            }
        } else if (s.menu.cursor != g_menu_cursor) {
            std::string text;
            item_speech(s, m, &text);
            say(text, false);
        }
        g_menu_cursor = s.menu.cursor;
    } else {
        g_menu_live = false;
        g_menu_window = 0xFF;
        g_menu_cursor = -9999;
    }

    // List menus (bag, shops, PC lists).
    if (s.list.live) {
        const int index = list_index(s.list);
        const bool opened = !g_list_live || s.list.task != g_list_task || g_surface_changed;
        if (opened) {
            g_list_live = true;
            g_list_task = s.list.task;
            std::string text;
            item_speech(s, m, &text);
            say(text, false);
        } else if (index != g_list_index) {
            std::string text;
            item_speech(s, m, &text);
            say(text, false);
        }
        g_list_index = index;
    } else {
        g_list_live = false;
        g_list_task = 0xFF;
        g_list_index = -9999;
    }

    // Battle input menus.
    if (s.battle.active && s.battle.control != BattleControl::None) {
        const int cursor = battle_cursor(s.battle);
        const bool opened = s.battle.control != g_control || g_surface_changed;
        if (opened) {
            g_control = s.battle.control;
            std::string text;
            item_speech(s, m, &text);
            say(text, false);
        } else if (cursor != g_battle_cursor) {
            std::string text;
            item_speech(s, m, &text);
            say(text, false);
        }
        g_battle_cursor = cursor;
    } else {
        g_control = BattleControl::None;
        g_battle_cursor = -9999;
    }

    // Name entry: its keyboard is not an sMenu or ListMenu, so it is read from
    // the screen's own tables and cursor. The player steers it with the pad as
    // a sighted player does; every move says where the cursor landed.
    if (s.kind == SceneKind::Naming) {
        NamingKey key;
        if (naming_state(m, &key)) {
            const std::string typed = naming_typed(m);
            const bool first = !g_naming_live || g_surface_changed;
            if (first) {
                // The screen's own keys, said once: Select swaps the page, B
                // deletes, Start finishes. They are still the game's keys; the
                // reader only names them.
                say(naming_page_name(key.page) + ". " + naming_speech(key, typed) +
                        " Select changes the page, B deletes, Start finishes.", false);
            } else if (key.page != g_naming_page) {
                say(naming_page_name(key.page) + ". " + naming_speech(key, typed), false);
            } else if (key.row != g_naming_row || key.column != g_naming_column ||
                       key.button != g_naming_button) {
                say(naming_char_speech(key.key), false);
            } else if (typed != g_naming_typed) {
                say(typed.empty() ? "Name cleared." : "Name: " + typed, false);
            }
            g_naming_live = true;
            g_naming_page = key.page;
            g_naming_row = key.row;
            g_naming_column = key.column;
            g_naming_button = key.button;
            g_naming_typed = typed;
        } else {
            g_naming_live = false;
        }
    } else {
        g_naming_live = false;
        g_naming_page = -1;
        g_naming_row = -9999;
        g_naming_column = -9999;
        g_naming_button = false;
        g_naming_typed.clear();
    }

    // A menu opened before its labels were captured: retry briefly.
    if (g_pending_item) {
        std::string text;
        if (item_speech(s, m, &text)) {
            g_pending_item = false;
            say(text, false);
        } else if (static_cast<int>(g_frame) >= g_pending_deadline) {
            g_pending_item = false;
            say(text, false);
        }
    }

}

// ── Spoken settings (read from the mod's own options) ────────────────────

// The three options the launcher and the Mods menu edit. The layer keeps its
// own copy so a change is audible in the running session, and
// activate_from_options() reads the persisted values at start-up, so every
// place that edits them edits one setting rather than several.
//
// There is no pad path on purpose: settings are changed on the launcher (before
// play) or in the game's own Mods menu, never by a button combination pressed
// during play, so the pad cannot change how the game talks by accident.
SpokenSettings g_settings;

void apply_settings() {
    set_speak_game_text(g_settings.read_game_text);
    set_verbosity(g_settings.detail_everything ? 1 : 0);
    set_rate(rate_multiplier(g_settings.rate));
}

// ── Controller hotkeys ───────────────────────────────────────────────────

// Host key state only, once per guest frame: a hotkey fires once per press, so
// holding a shoulder button does not repeat speech. The state is the pad's own
// keyinput, before synthesis, so touch gestures and the touch policy never
// trigger it. emerald_hotkeys.h owns the decoding, including the staggered
// presses of a real pad (Select then L stops, Select alone repeats). Settings
// are not on the pad: nothing pressed during play changes how the game talks.
HotkeyTracker g_hotkeys;

// Android attaches the Java bridge before the SDL view exists, and a failed
// attach used to leave the whole run silent (say() can only log). Retry a few
// times, at most every two seconds, until a speech sink is installed.
#if defined(__ANDROID__)
std::uint64_t g_last_sink_attempt = 0;
unsigned g_sink_attempts = 0;
#endif

void retry_speech_sink_if_needed() {
#if defined(__ANDROID__)
    if (g_speak_fn || g_sink_attempts >= 8) return;
    if (g_last_sink_attempt && g_frame - g_last_sink_attempt < 120) return;
    g_last_sink_attempt = g_frame;
    ++g_sink_attempts;
    install_platform_bridge();
#endif
}

void poll_hotkeys(std::uint16_t host, bool naming) {
    switch (g_hotkeys.poll(host, naming)) {
        case Hotkey::Read: push_action(Action::ReadStatus); break;
        case Hotkey::Repeat: push_action(Action::Repeat); break;
        case Hotkey::Stop: push_action(Action::StopSpeech); break;
        case Hotkey::None: break;
    }
}

}  // namespace

// ── Public interface ─────────────────────────────────────────────────────

const char* action_name(Action action) {
    switch (action) {
        case Action::Up: return "up";
        case Action::Down: return "down";
        case Action::Left: return "left";
        case Action::Right: return "right";
        case Action::Confirm: return "confirm";
        case Action::Cancel: return "cancel";
        case Action::Start: return "start";
        case Action::ReadStatus: return "read_status";
        case Action::Repeat: return "repeat";
        case Action::StopSpeech: return "stop";
        case Action::SelectItem: return "select";
        case Action::NextItem: return "next";
        case Action::PrevItem: return "prev";
        case Action::SaveState: return "save_state";
        case Action::LoadState: return "load_state";
        case Action::NextStateSlot: return "next_state_slot";
        case Action::StateMenu: return "state_menu";
    }
    return "unknown";
}

std::uint16_t input_frame(const gbarecomp::TouchFrameInfo* frame) {
    if (!frame) return emerald::touch::input_frame(frame);
    const std::uint16_t keys = emerald::touch::input_frame(frame);
    g_frame = frame->frame_count;
    if (!g_enabled) {
        g_hotkeys.reset(frame->host_keyinput);
        g_prints.clear();
        return keys;
    }
    Core& c = emerald::touch::core();
    const SceneState& s = c.scene;
    const Mem m = Mem::current();
    // The spoken save-state sheet is opened by a tap in the top-left corner and
    // owns the gestures while it is up. Its frame produces no synthesized keys:
    // opening, saving and closing must never also play the game.
    bool swallow_keys = false;
    if (g_state_menu) {
        state_menu_gestures(frame);
        swallow_keys = true;
    } else if (state_menu_allowed(s) && corner_tap(frame)) {
        open_state_menu();
        swallow_keys = true;
    }
    // Pad commands, serviced this frame. The naming screen is the one scene
    // that reads Select, so its repeat modifier is R.
    retry_speech_sink_if_needed();
    poll_hotkeys(frame->host_keyinput, s.kind == SceneKind::Naming);
    consume_actions(c, s, m);
    watch(s, m);
    poll_state_op();
    // Audio cues age their interaction expectations, then the navigation layer
    // reports exits, floor changes and whatever the player just walked up to.
    cues_frame();
    nav_frame(s, m);
    return swallow_keys ? 0 : keys;
}

void install_sink(SpeakFn speak, void (*stop)(), void (*rate)(float)) {
    g_speak_fn = speak;
    g_stop_fn = stop;
    g_rate_fn = rate;
    if (g_rate_fn) g_rate_fn(g_rate);
}

void speak_now(const char* text, bool interrupt) {
    if (text) say(text, interrupt);
}

const char* controller_hotkeys_help() {
    // Three commands, no chord to remember for settings: those are changed on
    // the launcher (Android) or in the Mods menu, never by the pad.
#if defined(__ANDROID__)
    return "Press L to read the screen, Select to repeat, "
           "and Select then L to stop speech. Tap the top-left corner of the "
           "screen to save or load a state. To change the spoken settings, "
           "quit the game and set them on the launcher screen.";
#else
    return "Press L to read the screen, Select to repeat, "
           "and Select then L to stop speech. The spoken settings are in the "
           "Mods menu.";
#endif
}

void adopt_options(const char* game_text, const char* detail, const char* rate) {
    g_settings.read_game_text = game_text_on(game_text);
    g_settings.detail_everything = detail_everything(detail);
    g_settings.rate = rate_index(rate);
    apply_settings();
}

void push_action(Action action, int arg) {
    std::lock_guard<std::mutex> lk(g_action_m);
    if (g_actions.size() >= 16) g_actions.pop_front();
    g_actions.emplace_back(static_cast<int>(action), arg);
}

void enable(bool on) {
    if (g_enabled == on) return;
    g_enabled = on;
    g_prints.clear();
    g_labels.clear();
    g_pending_item = false;
    g_state_menu = false;
    g_state_op = StateOp{};
    g_nav.active = false;
    cues_reset();
    nav_reset();
    g_had_scene = false;
    g_kind = SceneKind::Unknown;
    g_menu_live = false;
    g_menu_cursor = -9999;
    g_list_live = false;
    g_list_index = -9999;
    g_control = BattleControl::None;
    g_battle_cursor = -9999;
    g_surface = 0;
    g_message.clear();
    std::fprintf(stderr, "[emerald:a11y] spoken UI %s\n", on ? "enabled" : "disabled");
}

bool enabled() { return g_enabled; }

void set_speak_game_text(bool on) { g_speak_text = on; }

void set_verbosity(int level) { g_verbosity = level > 0 ? 1 : 0; }

void set_rate(float rate) {
    g_rate = std::max(0.5f, std::min(2.0f, rate));
    if (g_rate_fn) g_rate_fn(g_rate);
}

void install_slot_hotkey(SlotHotkeyFn fn) { g_slot_hotkey = fn; }

void set_launch_arguments(const std::vector<std::string>& args) {
    g_paths = launch_paths_from_args(args);
}

int state_slot() { return g_state_slot; }

void set_state_slot(int slot) { g_state_slot = clamp_state_slot(slot); }

void reset() {
    // Mod activation disables every entry hook before reset callbacks run, so
    // the text-printer probe is registered and re-enabled from here (the touch
    // policy's scene probes use the same pattern). Speech stays off until the
    // feature's activation pass runs.
    register_text_probe();
    enable(false);
    g_labels.clear();
    g_prints.clear();
    g_nav = Nav{};
}

// ── Text printer hook ────────────────────────────────────────────────────

namespace {
int text_printer_probe(std::uint32_t address, int thumb, ArmCpuState* cpu);

void register_probe_once() {
    static bool registered = false;
    if (registered) return;
    registered = true;
    gba_mod_register_function_entry_plugin("emerald.a11y.text_printer", 0x0800467C, 1,
                                          text_printer_probe);
}
}  // namespace

void register_text_probe() {
    register_probe_once();
    gba_mod_set_function_hook_enabled("emerald.a11y.text_printer", 1);
}

namespace {

// AddTextPrinter(struct TextPrinterTemplate *template, u8 speed, callback):
// template->currentChar is the string, template->windowId at +4, y at +7.
int text_printer_probe(std::uint32_t address, int thumb, ArmCpuState* cpu) {
    (void)address;
    (void)thumb;
    if (!g_enabled || !cpu) return 0;
    const std::uint32_t template_addr = cpu->R[0] & ~1u;
    const Mem m = Mem::current();
    if (!m.ok() || !m.ptr(template_addr, 8)) return 0;
    const std::uint32_t text_addr = m.u32(template_addr);
    if (!text_addr || !m.ptr(text_addr, 1)) return 0;
    PrintEvent event;
    event.window = m.u8(template_addr + 4);
    event.y = m.u8(template_addr + 7);
    event.frame = g_frame;
    // A printed page can be long: the intro's world-building page runs to about
    // 560 characters, and cutting shorter truncated it mid-sentence ("…battle
    // others lik", then "…I've been"). The game's message buffers are 1000
    // bytes, so read the whole thing.
    event.text = decode(m, text_addr, 1000, true);
    if (event.text.empty()) return 0;
    // One label per printed line: menus and prompts print their entries as
    // lines of a single string.
    std::size_t start = 0;
    while (start <= event.text.size()) {
        std::size_t end = event.text.find('\n', start);
        if (end == std::string::npos) end = event.text.size();
        std::string line = event.text.substr(start, end - start);
        trim(&line);
        if (!line.empty()) event.lines.push_back(line);
        if (end == event.text.size()) break;
        start = end + 1;
    }
    if (event.lines.empty()) return 0;
    ++g_prints_seen;
    g_last_print = event.text;
    if (g_prints.size() >= 48) g_prints.erase(g_prints.begin());
    g_prints.push_back(std::move(event));
    return 0;   // observe only: the guest body always runs
}

}  // namespace

// ── TCP ──────────────────────────────────────────────────────────────────

namespace {

void tcp_status(std::string* out) {
    Core& c = emerald::touch::core();
    const SceneState& s = c.scene;
    const Mem m = Mem::current();
    char head[256];
    std::snprintf(head, sizeof(head),
                  "{\"ok\":true,\"prints\":%llu,\"enabled\":%s,\"frame\":%llu,\"scene\":\"%s\","
                  "\"menu\":%s,\"list\":%s,\"battle\":%s,\"speak_text\":%s,"
                  "\"verbosity\":%d,\"state_slot\":%d,\"state_menu\":%s,\"message\":",
                  static_cast<unsigned long long>(g_prints_seen),
                  g_enabled ? "true" : "false",
                  static_cast<unsigned long long>(g_frame), scene_name(s.kind),
                  s.menu.live ? "true" : "false", s.list.live ? "true" : "false",
                  s.battle.active ? "true" : "false", g_speak_text ? "true" : "false",
                  g_verbosity, g_state_slot, g_state_menu ? "true" : "false");
    *out = head;
    gbarecomp::json::append_quoted(*out, g_message);
    *out += ",\"last_print\":";
    gbarecomp::json::append_quoted(*out, g_last_print);
    *out += ",\"status\":";
    gbarecomp::json::append_quoted(*out, status_text(s, m));
    *out += ",\"items\":[";
    bool first = true;
    if (s.menu.live) {
        for (int i = s.menu.min; i <= s.menu.max && i - s.menu.min < kMaxItems; ++i) {
            std::string label = menu_label(s.menu, i);
            if (label.empty()) label = "Option " + std::to_string(i - s.menu.min + 1);
            if (!first) *out += ",";
            first = false;
            gbarecomp::json::append_quoted(*out, label);
        }
    } else if (s.list.live) {
        for (int i = 0; i < s.list.total && i < kMaxItems; ++i) {
            std::string label = list_item_name(m, s.list, i);
            if (!first) *out += ",";
            first = false;
            gbarecomp::json::append_quoted(*out, label);
        }
    }
    *out += "],\"selected\":";
    *out += std::to_string(surface_cursor(s));
    *out += "}";
}

void tcp_action(const std::string& name, int arg) {
    for (int i = 1; i <= static_cast<int>(Action::StateMenu); ++i) {
        const Action action = static_cast<Action>(i);
        if (name == action_name(action)) {
            push_action(action, arg);
            return;
        }
    }
}

}  // namespace

int tcp_command(const char* request, void (*write)(void*, const char*, std::size_t),
                void* ctx) {
    if (emerald::touch::tcp_command(request, write, ctx)) return 1;
    if (!request || !std::strstr(request, "\"emerald_a11y")) return 0;
    gbarecomp::json::Value req;
    if (!gbarecomp::json::parse(request, req) || !req.is_object()) return 0;
    const std::string cmd = req.str("cmd");
    std::string out;
    auto emit = [&] { write(ctx, out.data(), out.size()); };

    if (cmd == "emerald_a11y_status") {
        tcp_status(&out);
        emit();
        return 1;
    }
    if (cmd == "emerald_a11y_log") {
        out = "{\"ok\":true,\"utterances\":[";
        bool first = true;
        std::lock_guard<std::mutex> lk(g_log_m);
        for (const LogEntry& e : g_log) {
            if (!first) out += ",";
            first = false;
            out += "{\"frame\":" + std::to_string(e.frame) + ",\"seq\":" +
                   std::to_string(e.seq) + ",\"interrupt\":" +
                   std::to_string(e.interrupt) + ",\"text\":";
            gbarecomp::json::append_quoted(out, e.text);
            out += "}";
        }
        out += "]}";
        emit();
        return 1;
    }
    if (cmd == "emerald_a11y_action") {
        tcp_action(req.str("action"), static_cast<int>(req.integer("index", 0)));
        out = "{\"ok\":true}";
        emit();
        return 1;
    }
    if (cmd == "emerald_a11y_speak") {
        speak_now(req.str("text").c_str(), true);
        out = "{\"ok\":true}";
        emit();
        return 1;
    }
    if (cmd == "emerald_a11y_nav") {
        NavState n;
        read_nav(Mem::current(), &n);
        out = nav_json(n);
        emit();
        return 1;
    }
    if (cmd == "emerald_a11y_target") {
        // Navigation target: "tell me when I get there". Without arguments it
        // clears the target; with x/y (and the current map by default) it arms
        // one, which the bot uses to step a route and confirm each waypoint.
        if (req.integer("clear", 0) != 0) {
            nav_clear_target();
            out = "{\"ok\":true,\"clear\":true}";
            emit();
            return 1;
        }
        NavState here;
        read_nav(Mem::current(), &here);
        const int x = static_cast<int>(req.integer("x", here.x));
        const int y = static_cast<int>(req.integer("y", here.y));
        const int group = static_cast<int>(req.integer("map_group", here.mapGroup));
        const int num = static_cast<int>(req.integer("map_num", here.mapNum));
        nav_set_target(group, num, x, y);
        out = "{\"ok\":true,\"target\":[" + std::to_string(x) + "," +
              std::to_string(y) + "]}";
        emit();
        return 1;
    }
    if (cmd == "emerald_a11y_cues") {
        out = "{\"ok\":true,\"spoken\":";
        out += spoken_alongside() ? "true" : "false";
        out += ",\"table\":[";
        for (int i = 0; i < cue_table_size(); ++i) {
            if (i) out += ',';
            gbarecomp::json::append_quoted(out, cue_table_row(i));
        }
        out += "]}";
        emit();
        return 1;
    }
    if (cmd == "emerald_a11y_cue") {
        // Test/tuning hook: play one named cue, optionally toggling the spoken
        // announcements that ride alongside the sounds.
        const int spoken = static_cast<int>(req.integer("spoken", -1));
        if (spoken >= 0) set_spoken_alongside(spoken != 0);
        const std::string name = req.str("name");
        bool played = false;
        for (int i = 0; i < cue_table_size(); ++i) {
            const Cue cue = static_cast<Cue>(i);
            if (name != cue_name(cue)) continue;
            play_cue(cue, req.str("say").c_str());
            played = true;
            break;
        }
        out = played ? "{\"ok\":true}" : gbarecomp::json::error_reply("unknown cue");
        emit();
        return 1;
    }
    out = gbarecomp::json::error_reply("unknown emerald_a11y command");
    emit();
    return 1;
}

}  // namespace emerald::accessibility

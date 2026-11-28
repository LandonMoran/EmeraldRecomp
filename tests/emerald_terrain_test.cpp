// tests/emerald_terrain_test.cpp — the behaviour-byte to terrain mapping.
//
// This is the table that decides whether a tile is a wall, a door, or a lift,
// and for ledges it also decides which way you jump. A ledge that is mapped one
// entry off still looks like a ledge and still has a plausible sentence, so
// nothing in play announces the mistake: the player just finds that the door
// they were told to jump is not there. These cases pin every direction, both
// halves of it (the terrain class and the jump vector), and the words that go
// with them.
#include "accessibility/emerald_terrain.h"

#include <cstdio>
#include <cstring>
#include <string>

using emerald::accessibility::Terrain;
using emerald::accessibility::is_ledge;
using emerald::accessibility::ledge_jump;
using emerald::accessibility::terrain_name;
using emerald::accessibility::terrain_of_behavior;
using emerald::accessibility::terrain_speech;

namespace {

int failures = 0;

// MB_JUMP_* from include/constants/metatile_behaviors.h, in the header's order.
struct Ledge {
    int behavior;
    Terrain terrain;
    const char* name;
    int jx, jy;              // the step a jump takes you, in map tiles
    const char* direction;   // the word the sentence must carry
};

const Ledge kLedges[] = {
    {0x38, Terrain::LedgeEast, "ledge_east", 1, 0, "east"},
    {0x39, Terrain::LedgeWest, "ledge_west", -1, 0, "west"},
    {0x3A, Terrain::LedgeNorth, "ledge_north", 0, -1, "north"},
    {0x3B, Terrain::LedgeSouth, "ledge_south", 0, 1, "south"},
    {0x3C, Terrain::LedgeNorthEast, "ledge_north_east", 1, -1, "north-east"},
    {0x3D, Terrain::LedgeNorthWest, "ledge_north_west", -1, -1, "north-west"},
    {0x3E, Terrain::LedgeSouthEast, "ledge_south_east", 1, 1, "south-east"},
    {0x3F, Terrain::LedgeSouthWest, "ledge_south_west", -1, 1, "south-west"},
};

void expect(bool ok, const char* what, const char* detail) {
    if (ok) return;
    std::printf("FAIL: %s (%s)\n", what, detail);
    ++failures;
}

void expect_terrain(int behavior, Terrain want, const char* detail) {
    const Terrain got = terrain_of_behavior(behavior);
    if (got != want) {
        std::printf("FAIL: behaviour 0x%02X -> %s, wanted %s\n", behavior,
                    terrain_name(got), terrain_name(want));
        ++failures;
    }
}

}  // namespace

int main() {
    for (const Ledge& l : kLedges) {
        const char* detail = l.name;
        expect_terrain(l.behavior, l.terrain, detail);

        expect(is_ledge(l.terrain), "is_ledge", detail);
        expect(is_ledge(terrain_of_behavior(l.behavior)),
               "is_ledge(terrain_of_behavior)", detail);

        int jx = 99, jy = 99;
        ledge_jump(l.terrain, &jx, &jy);
        if (jx != l.jx || jy != l.jy) {
            std::printf("FAIL: ledge_jump(%s) = (%d,%d), wanted (%d,%d)\n", l.name, jx,
                        jy, l.jx, l.jy);
            ++failures;
        }

        expect(std::strcmp(terrain_name(l.terrain), l.name) == 0, "terrain_name",
               detail);

        // The sentence has to name the way you jump, and only that way: a
        // copy-pasted "south" in the north case reads as a working cue.
        const char* speech = terrain_speech(l.terrain);
        expect(speech != nullptr && speech[0] != '\0', "terrain_speech empty", detail);
        if (speech) {
            // The whole sentence, not a substring: cardinals live inside the
            // diagonal words ("north" in "north-east"), so a contains() check
            // cannot tell a copied phrase from the right one.
            const std::string want =
                std::string("A ledge. Jump ") + l.direction + " to cross it.";
            if (want != speech) {
                std::printf("FAIL: terrain_speech(%s) = \"%s\", wanted \"%s\"\n",
                            l.name, speech, want.c_str());
                ++failures;
            }
        }
    }

    // The two Lavaridge tiles keep their own classes; ledges must not have
    // swallowed them, and they must not claim to be jumpable.
    expect_terrain(0x68, Terrain::Pit, "MB_LAVARIDGE_GYM_1F_WARP");
    expect_terrain(0x29, Terrain::Vent, "MB_LAVARIDGE_GYM_B1F_WARP");
    expect(std::strcmp(terrain_name(Terrain::Pit), "pit") == 0, "pit name", "");
    expect(std::strcmp(terrain_name(Terrain::Vent), "vent") == 0, "vent name", "");
    expect(!is_ledge(Terrain::Pit), "pit is not a ledge", "");
    expect(!is_ledge(Terrain::Vent), "vent is not a ledge", "");
    expect(!is_ledge(Terrain::Plain), "plain is not a ledge", "");

    int jx = 99, jy = 99;
    ledge_jump(Terrain::Pit, &jx, &jy);
    expect(jx == 0 && jy == 0, "pit has no jump vector", "");

    // Ordinary ground stays ordinary: every unremarkable behaviour the layer
    // might meet must not become a ledge.
    expect_terrain(0x00, Terrain::Plain, "MB_NORMAL");
    expect_terrain(0x40, Terrain::Plain, "MB_UNUSED_40");

    if (failures == 0) {
        std::printf("emerald_terrain_test: all checks passed\n");
        return 0;
    }
    std::printf("emerald_terrain_test: %d failure(s)\n", failures);
    return 1;
}

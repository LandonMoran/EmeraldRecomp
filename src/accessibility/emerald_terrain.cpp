// emerald_terrain.cpp — behaviour byte -> terrain class, jump vector, sentence.
//
// The behaviour numbers are the game's own constants
// (include/constants/metatile_behaviors.h). tests/emerald_terrain_test.cpp pins
// every ledge direction: a mapping that is off by one turns a jump into a wall
// that says the wrong way, and that is invisible unless it is asserted.

#include "accessibility/emerald_terrain.h"

namespace emerald::accessibility {

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

bool is_ledge(Terrain t) {
    return t == Terrain::LedgeEast || t == Terrain::LedgeWest ||
           t == Terrain::LedgeNorth || t == Terrain::LedgeSouth ||
           t == Terrain::LedgeNorthEast || t == Terrain::LedgeNorthWest ||
           t == Terrain::LedgeSouthEast || t == Terrain::LedgeSouthWest;
}
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

}  // namespace emerald::accessibility

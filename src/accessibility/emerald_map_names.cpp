#include "emerald_map_names.h"

namespace emerald::accessibility {

namespace {
#include "emerald_map_names.inc"

constexpr int kCount = static_cast<int>(sizeof(kMapNames) / sizeof(kMapNames[0]));

const MapNameEntry* find(int group, int num) {
    if (group < 0 || group > 255 || num < 0 || num > 255) return nullptr;
    const int key = (group << 8) | num;
    int lo = 0, hi = kCount - 1;
    while (lo <= hi) {
        const int mid = (lo + hi) / 2;
        const int at = (kMapNames[mid].group << 8) | kMapNames[mid].num;
        if (at == key) return &kMapNames[mid];
        if (at < key) lo = mid + 1;
        else hi = mid - 1;
    }
    return nullptr;
}
}  // namespace

const char* map_name_spoken(int group, int num) {
    const MapNameEntry* e = find(group, num);
    return e ? e->spoken : nullptr;
}

const char* map_name_symbol(int group, int num) {
    const MapNameEntry* e = find(group, num);
    return e ? e->symbol : nullptr;
}

}  // namespace emerald::accessibility

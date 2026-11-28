// tests/a11y_hp_readout_test.cpp — the health-box readout filter.
//
// A heal animates the HP bar, and the health box repaints "23/", "/24", ... "28/"
// through the text printer on the way. Those used to be spoken as their own
// sentences - six fragments for one potion. These cases pin which printed blocks
// count as readout noise, and that ordinary text (money, "12/28 HP", item names)
// is still speech.
#include "accessibility/emerald_text_filter.h"

#include <cstdio>
#include <string>

using emerald::accessibility::is_hp_readout;

namespace {

int failures = 0;

void expect(const char* text, bool want) {
    const bool got = is_hp_readout(text);
    if (got == want) return;
    std::printf("FAIL: is_hp_readout(\"%s\") = %s, wanted %s\n", text,
                got ? "true" : "false", want ? "true" : "false");
    ++failures;
}

}  // namespace

int main() {
    // The fragments a potion used to speak, one per step of the bar.
    expect("23/", true);
    expect("/24", true);
    expect("25/", true);
    expect("28/", true);
    expect("12/28", true);

    // Not readouts: money has no slash, and anything with letters is text.
    expect("2300", false);
    expect("12/28 HP", false);
    expect("HP 12/28", false);
    expect("POKé BALL", false);
    expect("HP was restored by 16 points.", false);
    expect("", false);

    if (failures == 0) std::printf("a11y_hp_readout_test: ok\n");
    return failures == 0 ? 0 : 1;
}

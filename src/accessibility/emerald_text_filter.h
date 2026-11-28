// emerald_text_filter.h — which printed blocks are readouts, not speech.
//
// Kept dependency-free so the rules can be pinned by a plain unit test: a health
// box repaints its numbers through the text printer while the bar animates, and
// those repaints are not something to say out loud.

#pragma once

#include <string>

namespace emerald::accessibility {

// True when `text` is nothing but digits, slashes and spaces - the shape of a
// health box caught part way through its animation ("23/", "/24", "28/"). Money
// is digits with no slash and is not one of these.
bool is_hp_readout(const std::string& text);

}  // namespace emerald::accessibility

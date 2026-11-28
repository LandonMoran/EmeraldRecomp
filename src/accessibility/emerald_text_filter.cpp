// emerald_text_filter.cpp — see emerald_text_filter.h.
#include "accessibility/emerald_text_filter.h"

namespace emerald::accessibility {

bool is_hp_readout(const std::string& text) {
    if (text.find('/') == std::string::npos) return false;
    return text.find_first_not_of("0123456789/ ") == std::string::npos;
}

}  // namespace emerald::accessibility

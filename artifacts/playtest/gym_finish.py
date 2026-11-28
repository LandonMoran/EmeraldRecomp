"""Finish the four-plate run: survive the trainer at (7,10), step onto (8,9).

The route script left the player at (7,9) with VAR_MAUVILLE_GYM_STATE == 3 after
a trainer's sight line started a battle. This presses A until the field comes
back, then takes the one remaining step and reports what the mod said.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402

REPORT = os.path.join(HERE, "reports", "mauville-fourth-plate.txt")


def tile(p):
    o = p.obj()
    return (o["x"] - 7, o["y"] - 7)


def main():
    p = Pad(transcript=REPORT)
    lines = []
    for i in range(260):
        st = p.status()
        if st.get("scene") != "battle":
            break
        p.confirm(40)
        p.flush_speech("battle%d" % i)
    lines.append("scene now %s at %s" % (p.status().get("scene"), tile(p)))

    for i in range(4):
        moved, o = p.step("right")
        p.flush_speech("last%d" % i)
        st = p.status()
        msg = st.get("message") or st.get("status") or ""
        lines.append("right -> %s %s %s" % (tile(p), "moved" if moved else "BLOCKED", msg))
        if tile(p) == (8, 9):
            lines.append("ON SWITCH 4: %s" % msg)
            break
        if st.get("scene") == "battle":
            for i in range(260):
                if p.status().get("scene") != "battle":
                    break
                p.confirm(40)
                p.flush_speech("b2-%d" % i)

    out = "\n".join(lines)
    open(os.path.join(HERE, "reports", "mauville-fourth-plate.log"), "w").write(out + "\n")
    print(out)


if __name__ == "__main__":
    main()

"""Challenge Flannery from (13,10) and record what the mod says about the win.

The walk left the player one tile south of Flannery. This faces her, presses A
through the challenge, fights, and then keeps pressing A through the prize text
until the field is free again. Everything the mod speaks is in the transcript.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402

REPORT = os.path.join(HERE, "reports", "lavaridge-flannery.txt")
BATTLE_PRESS_LIMIT = 900


class Shim:
    def __init__(self, p):
        self.p = p

    def ask(self, **kw):
        return self.p.ask(**kw)


def free(p):
    st = p.ask(cmd="emerald_dev_state")
    return (p.status().get("scene") == "overworld" and not st.get("message_box")
            and not st.get("controls_locked"))


def main():
    p = Pad(transcript=REPORT)
    log = []
    if "--save" in sys.argv:
        Checkpoints(conn=Shim(p)).save("lavaridge-at-flannery",
                                       note="1F (13,10), one tile south of Flannery")
        log.append("checkpoint lavaridge-at-flannery saved")
    o = p.obj()
    log.append("at (%d,%d) scene %s" % (o["x"] - 7, o["y"] - 7, p.status().get("scene")))

    # Face her and start the challenge.
    p.action("up", 20)
    p.flush_speech("face")
    for i in range(4):
        p.confirm(40)
        p.flush_speech("talk%d" % i)
        if p.status().get("scene") == "battle" or p.ask(cmd="emerald_dev_state").get("controls_locked"):
            break

    for rnd in range(12):
        if free(p):
            break
        fight_if_needed(p, "flannery%d" % rnd, log)
        p.flush_speech("flannery%d" % rnd)
        for i in range(6):
            if free(p):
                break
            p.confirm(40)
            p.flush_speech("after%d-%d" % (rnd, i))

    # Clear any remaining prize text.
    for i in range(30):
        if free(p):
            break
        p.confirm(40)
    p.flush_speech("prize")
    log.append("final scene %s, controls_locked %s"
               % (p.status().get("scene"),
                  p.ask(cmd="emerald_dev_state").get("controls_locked")))

    words = [t for _, t in p.words()]
    for line in words:
        if any(k in line.upper() for k in ("BADGE", "TM", "OVERHEAT", "FLANNERY", "HEAT")):
            log.append("SAID: " + line)
    open(REPORT, "w").write("\n".join(log) + "\n")
    print("\n".join(log[-14:]))


if __name__ == "__main__":
    main()

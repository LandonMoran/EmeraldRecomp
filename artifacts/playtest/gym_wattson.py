"""After the four-plate run: reach Wattson on the path the sim says exists.

From (8,9) the even layout's pocket only leaves south past (8,12); the fifth
press happens on switch 3 at (3,9), which is legal because the state var has
moved on to 4, and it flips the maze to the odd layout where row 7 - the beam
wall under Wattson - is open.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from checkpoints import Checkpoints  # noqa: E402
from pad import Pad  # noqa: E402

REPORTS = os.path.join(HERE, "reports")
# gym_sim.py route_to((8,9), k=4, state=4) -> (5,3), with NPC tiles blocked:
# BEN stands on (5,10), which is what refused the old route.
ROUTE = [("down", 3), ("left", 3), ("up", 1), ("left", 1), ("up", 2),
         ("left", 1), ("right", 1), ("up", 6), ("right", 1)]


class Shim:
    def __init__(self, pad):
        self.p = pad

    def ask(self, **kw):
        return self.p.ask(**kw)


def tile(p):
    o = p.obj()
    return (o["x"] - 7, o["y"] - 7)


def drain(p, tag, log, limit=400):
    n = 0
    while n < limit:
        st = p.ask(cmd="emerald_dev_state")
        scene = p.status().get("scene")
        if (scene == "overworld" and not st.get("message_box")
                and not st.get("controls_locked")):
            break
        p.confirm(40)
        p.flush_speech("%s-a%d" % (tag, n))
        n += 1
    log.append("[%s] A x%d -> %s at %s" % (tag, n, p.status().get("scene"), tile(p)))
    return n


def main():
    p = Pad(transcript=os.path.join(REPORTS, "mauville-wattson.txt"))
    cps = Checkpoints(conn=Shim(p))
    log = []
    cps.load("mauville-four-plates")
    drain(p, "settle", log)
    log.append("resumed at %s" % (tile(p),))

    tag = 0
    for d, n in ROUTE:
        for _ in range(n):
            tag += 1
            moved, o = p.step(d)
            p.flush_speech("r%02d" % tag)
            st = p.status()
            log.append("r%02d %-5s -> %s %s %s"
                       % (tag, d, tile(p), "moved" if moved else "BLOCKED",
                          st.get("message") or st.get("status") or ""))
            drain(p, "r%02d" % tag, log, 80)

    log.append("at %s; talking to Wattson" % (tile(p),))
    p.step("up")            # turn to face him
    p.flush_speech("face")
    p.confirm(40)
    p.flush_speech("talk")
    drain(p, "wattson", log)
    log.append("after talk: %s map %s" % (tile(p), tuple(p.map())))

    cps.save("mauville-wattson-cleared", note="four plates then the walk to Wattson")
    u = p.ask(cmd="emerald_a11y_log").get("utterances") or []
    with open(os.path.join(REPORTS, "mauville-wattson-utterances.txt"), "w") as fh:
        fh.write("Wattson walk - mod utterances\n\n")
        for e in u:
            fh.write("f%-7d %s\n" % (e["frame"], e["text"]))
    out = "\n".join(log)
    open(os.path.join(REPORTS, "mauville-wattson.log"), "w").write(out + "\n")
    print(out)


if __name__ == "__main__":
    main()

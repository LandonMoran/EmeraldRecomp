"""Stand in front of a gym leader, talk, fight for real, and prove the badge.

Why this exists
---------------
The mechanical part of a gym (levels, ledges, panels, ice) is modelled in
``gym_graph.py`` and spoken by the mod. Getting the *leader* in front of the
player still needs the tester's hands, and the audit allows exactly that: a dev
warp may put the tester at a tile. What it may not do is decide anything the
player would decide, so the warp is used only to reach the door, and the fight,
the badge and the party are read from the game afterwards.

Evidence written per gym:

* the spoken lines during the fight and the prize (transcript),
* the badge flag straight out of the save block (``emerald_dev_flag``),
* the party's levels after the fight,
* a checkpoint of the moment.

    python3 artifacts/playtest/leader_fight.py --gym fortree \
        --map 12,1 --tile 15,3 --face north --leader WINONA \
        --badge-id 0x86C --badge FEATHER
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402
from gym_walker import here  # noqa: E402

REPORTS = os.path.join(HERE, "reports")
DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}


class Log:
    def __init__(self, fh):
        self.fh = fh

    def append(self, text):
        print(text, flush=True)
        self.fh.write(text + "\n")
        self.fh.flush()


def party_levels(p):
    """Level/max HP of each party slot, straight from gPlayerParty."""
    import struct
    from party import G_PARTY, G_PARTY_COUNT, MON_SIZE, OFF_LEVEL, OFF_MAX_HP, read_ewram
    n = read_ewram(p, G_PARTY_COUNT, 1)[0]
    out = []
    for i in range(min(n, 6)):
        raw = read_ewram(p, G_PARTY + i * MON_SIZE, MON_SIZE)
        out.append((raw[OFF_LEVEL], struct.unpack("<H", raw[OFF_MAX_HP:OFF_MAX_HP + 2])[0]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gym", required=True)
    ap.add_argument("--map", required=True, help="group,num")
    ap.add_argument("--tile", required=True, help="x,y to stand on")
    ap.add_argument("--face", default="north")
    ap.add_argument("--leader", required=True)
    ap.add_argument("--badge-id", required=True, help="flag id, decimal or 0x..")
    ap.add_argument("--badge", required=True, help="badge name, for the report")
    ap.add_argument("--checkpoint", default="petalburg-cleared")
    ap.add_argument("--save", default="")
    args = ap.parse_args()

    group, num = (int(v) for v in args.map.split(","))
    tx, ty = (int(v) for v in args.tile.split(","))
    badge_id = int(args.badge_id, 0)
    os.makedirs(REPORTS, exist_ok=True)
    transcript = os.path.join(REPORTS, f"{args.gym}-leader.txt")
    p = Pad(transcript=transcript)
    log = Log(open(transcript + ".log", "w"))

    class S:
        def __init__(self, pad):
            self.pad = pad

        def ask(self, **kw):
            return self.pad.ask(**kw)

    Checkpoints(conn=S(p)).load(args.checkpoint)
    p.frames(40)
    before = p.ask(cmd="emerald_dev_flag", id=badge_id)
    log.append("badge flag %s before: %s" % (hex(badge_id), before.get("value")))

    p.force_map(group, num, tx, ty)
    p.frames(140)
    log.append("warped to %s on %s (the audit's tester hands)" % (here(p), args.map))

    dx, dy = DIRS[args.face]
    # face the leader, then talk
    p.walk(args.face, 1)
    p.frames(50)
    log.append("facing %s, leader at %s" % (args.face, (tx + dx, ty + dy)))
    p.confirm(45)
    p.flush_speech("talk")

    for rnd in range(40):
        st = p.status()
        scene = st.get("scene")
        if scene == "battle":
            fight_if_needed(p, "fight%d" % rnd, log)
            p.flush_speech("fight%d" % rnd)
            continue
        if p.ask(cmd="emerald_dev_state").get("controls_locked") or \
                p.ask(cmd="emerald_dev_state").get("message_box"):
            p.confirm(45)
            p.flush_speech("text%d" % rnd)
            continue
        break

    # let the prize text finish (badge, TM, Pokénav)
    for i in range(40):
        p.confirm(45)
        p.flush_speech("prize%d" % i)
    p.frames(60)

    after = p.ask(cmd="emerald_dev_flag", id=badge_id)
    levels = party_levels(p)
    log.append("badge flag %s after: %s" % (hex(badge_id), after.get("value")))
    log.append("party after: %s" % (levels,))
    log.append("position after: %s" % (here(p),))
    log.append("scene after: %s" % p.status().get("scene"))

    if args.save:
        Checkpoints(conn=S(p)).save(args.save, note="%s beaten" % args.gym)
        log.append("checkpoint saved: %s" % args.save)

    lines = [u["text"] for u in p.ask(cmd="emerald_a11y_log").get("utterances", [])]
    key = [t for t in lines if args.badge.upper() in t.upper() or "TM" in t or "defeated" in t]
    log.append("key lines: %s" % key[-8:])
    log.fh.close()


if __name__ == "__main__":
    main()

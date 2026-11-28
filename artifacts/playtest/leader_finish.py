"""Finish a leader fight that is already in progress, then collect the prize.

`leader_fight.py` sets the fight up; when the battle text runs long the press
cap can land mid-battle (Winona's Altaria alone is worth a hundred presses).
This continues from wherever the game is: battle, prize text, or field, and
writes the same evidence - badge flag, party, key spoken lines.
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
from leader_fight import Log, party_levels  # noqa: E402

REPORTS = os.path.join(HERE, "reports")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gym", required=True)
    ap.add_argument("--badge-id", required=True)
    ap.add_argument("--badge", required=True)
    ap.add_argument("--save", default="")
    ap.add_argument("--map", default="")
    ap.add_argument("--tile", default="")
    args = ap.parse_args()

    badge_id = int(args.badge_id, 0)
    transcript = os.path.join(REPORTS, f"{args.gym}-leader.txt")
    p = Pad(transcript=transcript)
    log = Log(open(transcript + ".log", "a"))

    log.append("--- continue from %s (scene %s)" % (here(p), p.status().get("scene")))
    last_text, quiet = None, 0
    for rnd in range(120):
        st = p.status()
        if st.get("scene") == "battle":
            fight_if_needed(p, "cont%d" % rnd, log)
            p.flush_speech("cont%d" % rnd)
            last_text, quiet = None, 0
            continue
        state = p.ask(cmd="emerald_dev_state")
        text = (st.get("message") or "")[-60:]
        if state.get("controls_locked") or state.get("message_box") or text != last_text:
            last_text = text
            quiet = 0
            p.confirm(45)
            p.flush_speech("text%d" % rnd)
            continue
        quiet += 1
        p.confirm(45)
        p.flush_speech("quiet%d" % rnd)
        if quiet >= 8:
            break

    for i in range(40):
        p.confirm(45)
        p.flush_speech("prize%d" % i)
    p.frames(60)

    after = p.ask(cmd="emerald_dev_flag", id=badge_id)
    log.append("badge flag %s: %s" % (hex(badge_id), after.get("value")))
    log.append("party after: %s" % (party_levels(p),))
    log.append("position after: %s, scene %s" % (here(p), p.status().get("scene")))

    if args.save:
        class S:
            def __init__(self, pad):
                self.pad = pad

            def ask(self, **kw):
                return self.pad.ask(**kw)

        Checkpoints(conn=S(p)).save(args.save, note="%s beaten" % args.gym)
        log.append("checkpoint saved: %s" % args.save)

    lines = [u["text"] for u in p.ask(cmd="emerald_a11y_log").get("utterances", [])]
    key = [t for t in lines if args.badge.upper() in t.upper() or "TM" in t]
    log.append("key lines: %s" % key[-8:])
    log.fh.close()


if __name__ == "__main__":
    main()

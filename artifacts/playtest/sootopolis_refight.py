"""Fight Juan again from the healed party, and capture the prize lines.

The first Sootopolis run's transcript lost its speech body, so the audit's
Sootopolis row quoted lines that no committed file held. This is the re-capture:
the save is already past the gym, so the three flags that gate the fight
(FLAG_BADGE08_GET, FLAG_DEFEATED_SOOTOPOLIS_GYM and TRAINER_JUAN_1's own flag)
are cleared first, and the party is healed at Sootopolis's Pokémon Centre before
the fight - the first attempt wedged on a move list where every move had 0 PP.

Disclosed shortcuts, both already allowed in this project: the flags restored
above, and the developer warp that puts the tester at (8,3) facing him. The
battle, the prize text and the flags afterwards are the game's own output.

    python3 artifacts/playtest/sootopolis_refight.py
"""

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
TRANSCRIPT = os.path.join(REPORTS, "sootopolis-leader.txt")

BADGE = 0x86E            # FLAG_BADGE08_GET (RAIN BADGE)
GYM_DEFEAT = 1271        # FLAG_DEFEATED_SOOTOPOLIS_GYM
JUAN_1 = 0x500 + 272     # FLAG_TRAINER_FLAG_START + TRAINER_JUAN_1


class S:
    def __init__(self, pad):
        self.pad = pad

    def ask(self, **kw):
        return self.pad.ask(**kw)


def speak(p, tag, wait=90):
    """Press A with a long settle, then record whatever became speech."""
    p.confirm(wait)
    p.frames(50)
    p.flush_speech(tag)


def main():
    p = Pad(transcript=TRANSCRIPT)
    log = Log(open(TRANSCRIPT + ".log", "a"))

    log.append("--- re-fight on the healed party ---")
    p.force_map(15, 0, 8, 3)
    p.frames(160)
    log.append("at %s (map 15,0) scene %s" % (here(p), p.status().get("scene")))

    for name, fid in (("FLAG_BADGE08_GET", BADGE),
                      ("FLAG_DEFEATED_SOOTOPOLIS_GYM", GYM_DEFEAT),
                      ("TRAINER_JUAN_1", JUAN_1)):
        log.append("cleared %s (%d) -> %s"
                   % (name, fid, p.ask(cmd="emerald_dev_flag", id=fid, set=0).get("value")))
    log.append("badge flag %s before the fight: %s"
               % (hex(BADGE), p.ask(cmd="emerald_dev_flag", id=BADGE).get("value")))

    p.walk("north", 1)
    p.frames(60)
    log.append("facing north at %s, leader at (8,2)" % (here(p),))

    for i in range(24):
        speak(p, "talk%d" % i)
        if p.status().get("scene") == "battle":
            log.append("battle started after %d presses" % (i + 1))
            break

    for rnd in range(60):
        st = p.status()
        if st.get("scene") == "battle":
            fight_if_needed(p, "fight%d" % rnd, log)
            p.flush_speech("fight%d" % rnd)
            continue
        if p.ask(cmd="emerald_dev_state").get("controls_locked"):
            speak(p, "text%d" % rnd)
            continue
        break

    for i in range(50):
        speak(p, "prize%d" % i)
    p.frames(60)

    log.append("badge flag %s after: %s"
               % (hex(BADGE), p.ask(cmd="emerald_dev_flag", id=BADGE).get("value")))
    log.append("FLAG_DEFEATED_SOOTOPOLIS_GYM after: %s"
               % (p.ask(cmd="emerald_dev_flag", id=GYM_DEFEAT).get("value"),))
    log.append("party after: %s" % (party_levels(p),))
    log.append("position after: %s, scene %s" % (here(p), p.status().get("scene")))

    if p.ask(cmd="emerald_dev_flag", id=BADGE).get("value"):
        Checkpoints(conn=S(p)).save("sootopolis-recapture", note="Juan beaten, re-captured fight")
        log.append("checkpoint saved: sootopolis-recapture")

    lines = [u["text"] for u in p.ask(cmd="emerald_a11y_log").get("utterances", [])]
    key = [t for t in lines if "BADGE" in t.upper() or "TM" in t or "defeated" in t]
    log.append("key lines: %s" % key[-12:])
    log.fh.close()
    print("done", flush=True)


if __name__ == "__main__":
    main()

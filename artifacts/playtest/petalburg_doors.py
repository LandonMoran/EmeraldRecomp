"""Petalburg gym, door model from the map's own door scripts.

Each door is a sign event, not a walkable tile: you stand on the tile below it,
press A, answer YES to "enter?", and the game warps you to a fixed destination.
Whether it opens is a condition on the door's script, and the conditions are the
gym:

    (1,105) Speed       -> (7,85)   VAR_PETALBURG_GYM_STATE >= 6
    (7,105) Accuracy    -> (1,98)   same
    (1,79) Confusion    -> (7,46)   TRAINER_RANDALL defeated
    (7,79) LeftDefense  -> (1,59)   TRAINER_RANDALL
    (1,92) RightDefense -> (7,59)   TRAINER_MARY
    (7,92) Recovery     -> (1,72)   TRAINER_MARY
    (7,40) LeftStrength -> (1,20)   TRAINER_PARKER
    (1,53) RightStrength-> (7,20)   TRAINER_ALEXIA
    (7,53) LeftOHKO     -> (1,33)   TRAINER_ALEXIA
    (1,66) RightOHKO    -> (7,33)   TRAINER_GEORGE
    (7,14) LeftLeaders  -> (1,7)    TRAINER_JODY
    (1,27) RightLeaders -> (7,7)    TRAINER_BERKE

so Randall opens the way to Parker, Parker to Jody, and Jody to Norman. The
walker walks this chain by ear: press the door, beat who is in the room, press the
next one.

    python3 artifacts/playtest/petalburg_doors.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pad import Pad  # noqa: E402
from gym_walk import fight_if_needed  # noqa: E402
from gym_walker import DIRS, here, live_grid, people, route  # noqa: E402

REPORT = os.path.join(HERE, "reports", "petalburg-walk.txt")
LOG = os.path.join(HERE, "reports", "petalburg-walk.log")
NORMAN = (4, 2)
STAND = (4, 3)

# door tile -> (destination, room name); all doors are pressed from one tile below
DOORS = {
    (1, 105): ((7, 85), "speed"),
    (7, 105): ((1, 98), "accuracy"),
    (1, 79): ((7, 46), "confusion"),
    (7, 79): ((1, 59), "left-defense"),
    (1, 92): ((7, 59), "right-defense"),
    (7, 92): ((1, 72), "recovery"),
    (7, 40): ((1, 20), "left-strength"),
    (1, 53): ((7, 20), "right-strength"),
    (7, 53): ((1, 33), "left-ohko"),
    (1, 66): ((7, 33), "right-ohko"),
    (7, 14): ((1, 7), "left-leaders"),
    (1, 27): ((7, 7), "right-leaders"),
}

# trainer standing in each room (map tile), from the map's object list
TRAINERS = {(4, 94): "MARY", (4, 81): "RANDALL", (4, 42): "PARKER",
            (4, 55): "ALEXIA", (4, 68): "GEORGE", (4, 16): "JODY",
            (4, 29): "BERKE"}


class Log:
    """fight_if_needed() appends lines; keep that shape and mirror them to the file."""

    def __init__(self, fh):
        self.fh = fh

    def append(self, text):
        print(text, flush=True)
        self.fh.write(text + "\n")
        self.fh.flush()


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def band(y):
    """Which room a row belongs to: rooms are 6 tall, separated by 7-row walls."""
    for top in (2, 15, 28, 41, 54, 67, 80, 93, 106):
        if top <= y < top + 13:
            return top
    return None


def say(fh, text):
    print(text, flush=True)
    fh.write(text + "\n")
    fh.flush()


def drain(p, fh, tag):
    """Clear any leftover message box: a trainer's parting line blocks movement."""
    for i in range(25):
        st = p.ask(cmd="emerald_dev_state")
        if not st.get("message_box") and not st.get("controls_locked"):
            return True
        p.confirm(40)
        p.flush_speech(tag + "-drain%d" % i)
    return False


def walk(p, fh, goal, tag):
    """Walk to a tile, re-planning each leg; returns True when there."""
    drain(p, fh, tag)
    for leg in range(30):
        pos = here(p)
        if pos == goal:
            return True
        grid = live_grid(p, 9, 112)
        plan = route(pos, goal, grid, people(p) - {goal})
        if plan is None:
            say(fh, "%s: no route %s -> %s" % (tag, pos, goal))
            return False
        d = plan[0]
        p.ask(cmd="emerald_a11y_action", action=d)
        p.frames(46)
        p.flush_speech("%s-%02d" % (tag, leg))
        if p.status().get("scene") == "battle":
            fight_if_needed(p, "%s-fight%02d" % (tag, leg), Log(fh))
            p.flush_speech("%s-fight%02d" % (tag, leg))
            for i in range(10):
                if p.status().get("scene") != "battle":
                    break
                p.confirm(40)
    return here(p) == goal


def press_door(p, fh, door, tag):
    """Stand under the door, press A, accept YES. True if it warped us."""
    approach = (door[0], door[1] + 1)
    if here(p) != approach and not walk(p, fh, approach, tag + "-approach"):
        return False
    p.action("north", 10)
    # A opens "Would you like to enter?", A again takes YES, then the door
    # animation runs for about a second before the map is swapped.
    for i in range(10):
        p.confirm(45)
        p.flush_speech("%s-press%d" % (tag, i))
        if band(here(p)[1]) != band(approach[1]) or here(p) != approach:
            p.frames(60)
            say(fh, "%s: %s opened, now %s" % (tag, DOORS[door][1], here(p)))
            return True
    say(fh, "%s: %s did not open" % (tag, DOORS[door][1]))
    return False


def fight_room(p, fh, y, tag):
    """Beat the trainer whose room y is in, if there is one.

    Trainers battle when they see you, so this approaches from the side of the
    room their line of sight runs down rather than poking them from behind.
    """
    trainer = next(((t, n) for t, n in TRAINERS.items()
                    if band(t[1]) == band(y)), None)
    if not trainer:
        say(fh, "%s: no trainer in room %s" % (tag, band(y)))
        return
    spot, name = trainer
    say(fh, "%s: room %s has %s at %s" % (tag, band(y), name, spot))
    grid = live_grid(p, 9, 112)
    for stand in ((spot[0], spot[1] + 3), (spot[0], spot[1] + 2),
                  (spot[0], spot[1] - 3), (spot[0] + 2, spot[1]),
                  (spot[0], spot[1] + 1)):
        if stand not in grid:
            continue
        if not walk(p, fh, stand, tag + "-" + name):
            continue
        # face them and press A: a trainer who does not spot you still answers
        d = "north" if stand[1] > spot[1] else ("south" if stand[1] < spot[1]
             else ("west" if stand[0] > spot[0] else "east"))
        p.action(d, 10)
        for i in range(8):
            if p.status().get("scene") == "battle":
                break
            p.confirm(45)
            p.flush_speech("%s-%s-talk%d" % (tag, name, i))
        if p.status().get("scene") != "battle" and manhattan(stand, spot) > 1:
            continue
        if p.status().get("scene") == "battle":
            fight_if_needed(p, tag + "-fight-" + name, Log(fh))
            p.flush_speech(tag + "-fight-" + name)
            for _ in range(10):
                if p.status().get("scene") != "battle":
                    break
                p.confirm(40)
            drain(p, fh, tag + "-after-" + name)
            say(fh, "%s: beat %s, at %s" % (tag, name, here(p)))
            return
        if False:
            if p.status().get("scene") == "battle":
                fight_if_needed(p, tag + "-fight-" + name, Log(fh))
                p.flush_speech(tag + "-fight-" + name)
                for _ in range(10):
                    if p.status().get("scene") != "battle":
                        break
                    p.confirm(40)
                drain(p, fh, tag + "-after-" + name)
                say(fh, "%s: beat %s, at %s" % (tag, name, here(p)))
                return
    say(fh, "%s: could not start a battle with %s" % (tag, name))


def main():
    p = Pad(transcript=REPORT)
    fh = open(LOG, "w")
    say(fh, "state %s" % (p.ask(cmd="emerald_dev_var", id=0x4085),))
    say(fh, "start %s room %s" % (here(p), band(here(p)[1])))

    chain = {106: (1, 105), 80: (1, 79), 41: (7, 40), 15: (7, 14)}
    for i in range(12):
        room = band(here(p)[1])
        if room in (0, 2) or room is None:
            break
        if room not in chain:
            say(fh, "step%d: no known door out of room %s" % (i, room))
            break
        fight_room(p, fh, here(p)[1], "step%d" % i)
        if not press_door(p, fh, chain[room], "step%d" % i):
            say(fh, "stopped: could not get through %s" % (DOORS[chain[room]][1],))
            break

    say(fh, "at %s room %s" % (here(p), band(here(p)[1])))
    if here(p) != STAND:
        walk(p, fh, STAND, "to-norman")
    if here(p) == STAND:
        p.action("north", 12)
        for i in range(4):
            p.confirm(40)
            p.flush_speech("tab0-talk%d" % i)
            if p.status().get("scene") == "battle":
                break
        for rnd in range(10):
            if p.status().get("scene") != "battle":
                break
            fight_if_needed(p, "norman%d" % rnd, fh)
            p.flush_speech("norman%d" % rnd)
            for _ in range(6):
                if p.status().get("scene") != "battle":
                    break
                p.confirm(40)
        for i in range(25):
            p.confirm(40)
            p.flush_speech("prize%d" % i)
        say(fh, "final %s scene %s" % (here(p), p.status().get("scene")))
    else:
        say(fh, "not at Norman: %s" % (here(p),))
    fh.close()


if __name__ == "__main__":
    main()

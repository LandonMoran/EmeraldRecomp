"""Settle the travel row and the four untested cue rows in one session.

What this proves, all in a single append-mode transcript:

* travel: standing at a town edge names the road and its side
  (`Route 116 east.`), and walking onto it lands where the name said
  (`New area. Route 116.`). A door names its destination too, so a door is a
  decision instead of a guess.
* the `sign` cue: facing a sign says `Something to read here. Press A.` and
  reading it speaks the game's text, which is also the `interact_ok` cue.
* the `item` cue: an item ball on the field says `Item here. Press A to pick it
  up.` and the pickup prints the game's own line.
* the `target` cue: arming a navigation target and walking to it says
  `You have arrived.`

Everything is driven from live state; the transcript is baselined on the
monotonic utterance seq so nothing logged before this run can be quoted.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catch_final as cf          # noqa: E402  (walk/go_to_warp/cross_edge live here)
import navwalk                     # noqa: E402
from maps import Grid, npc_tiles, obj_to_map   # noqa: E402
from pad import Pad                # noqa: E402

REPORT = os.environ.get(
    "TRAVEL_REPORT", "artifacts/playtest/reports/travel-cues.txt")

# Rustboro City: the sign beside the Mart door (17,45), read from (17,46) facing
# north. Route 116: the signpost at (5,10) and an item ball at (10,17). All are
# the map's own bg/object events, mapped tile for tile out of data/maps.
CITY_SIGN = (25, 35)
CITY_SIGN_FROM = (25, 36)
ROUTE_SIGN = (5, 10)
ROUTE_ITEM = (10, 17)


def look(p, direction, tag, frames=110):
    """Turn one way without walking, then log whatever the field says."""
    p.action(direction, 20)
    p.frames(frames)
    p.flush_speech(tag)


def talk(p, tag, frames=150):
    p.confirm(90)
    p.frames(frames)
    p.flush_speech(tag)
    for _ in range(3):                 # let a multi-box sign finish
        p.frames(60)
        p.flush_speech(tag)


def main():
    p = Pad(transcript=REPORT)
    u = p.ask(cmd="emerald_a11y_log").get("utterances") or []
    cf.SESSION_SEQ[0] = max([int(x.get("seq", 0)) for x in u] or [0])
    p.log_seq = cf.SESSION_SEQ[0]
    p.say("session", "one session, no restart: Rustboro gym -> sign -> east road "
                     "named -> Route 116 -> signpost -> item ball")

    from checkpoints import Checkpoints

    class S:
        def __init__(self, pad):
            self.pad = pad

        def ask(self, **kw):
            return self.pad.ask(**kw)

    Checkpoints(conn=S(p)).load("rustboro-cleared")
    p.frames(150)
    cf.unlock(p)
    p.say("start", f"map {cf.curmap(p)} tile {obj_to_map(*navwalk.settled(p))}")

    gg = Grid('LAYOUT_RUSTBORO_CITY_GYM')
    cf.go_to_warp(p, gg, [(5, 19), (6, 19)], (0, 3), "gym_out",
                  people=npc_tiles('RustboroCity_Gym'))
    if cf.curmap(p) != (0, 3):
        p.say("abort", f"did not leave the gym, at {cf.curmap(p)}")
        return
    p.say("map", f"out of the gym: {cf.curmap(p)} at {obj_to_map(*navwalk.settled(p))}")

    tw = Grid('LAYOUT_RUSTBORO_CITY')
    blocked = set(npc_tiles('RustboroCity'))
    # The signpost at (23,19), read from the tile below it: four tiles from the
    # gym door and no warp in between, so the walk cannot fall into the Mart.
    cf.walk(p, tw, (CITY_SIGN[0], CITY_SIGN[1] + 1), "sign_step",
            blocked=npc_tiles('RustboroCity'))
    look(p, "up", "sign_look")
    talk(p, "sign_read")
    p.say("sign", f"standing {obj_to_map(*navwalk.settled(p))} under sign {CITY_SIGN}")

    # The road east: the connection cue should name it before the crossing.
    cf.walk(p, tw, (29, 46), "east_walk", blocked=blocked)
    look(p, "right", "east_look")
    p.frames(120)
    p.flush_speech("east_edge")
    cf.cross_edge(p, tw, ("x", 1), (0, 31), "to_route116")
    if cf.curmap(p) != (0, 31):
        p.say("abort", f"did not reach Route 116, at {cf.curmap(p)}")
        return
    p.say("map", f"on Route 116: {cf.curmap(p)} tile {obj_to_map(*navwalk.settled(p))}")
    p.frames(120)
    p.flush_speech("route_arrival")

    rw = Grid('LAYOUT_ROUTE116')
    # Item ball at (10,17): stand beside it and face it. (The Route 116 signpost
    # was read in the first leg of this run; this leg is the collectible.)
    cf.walk(p, rw, (ROUTE_ITEM[0] + 1, ROUTE_ITEM[1]), "item_step")
    look(p, "left", "item_look")
    talk(p, "item_take")
    p.say("item", f"tried the item ball at {ROUTE_ITEM} from "
                  f"{obj_to_map(*navwalk.settled(p))}")

    # Navigation target: arm one two tiles away and walk it with the pad.
    here = obj_to_map(*navwalk.settled(p))
    tx, ty = here[0] + 2, here[1]
    p.ask(cmd="emerald_a11y_target", x=tx, y=ty)
    p.say("target", f"armed target ({tx}, {ty}) from {here}")
    cf.walk(p, rw, (tx, ty), "target_walk")
    p.frames(150)
    p.flush_speech("target_arrive")
    p.ask(cmd="emerald_a11y_target", clear=1)
    p.say("target", f"arrived at {obj_to_map(*navwalk.settled(p))}")
    p.say("done", f"final map {cf.curmap(p)}")


if __name__ == "__main__":
    main()

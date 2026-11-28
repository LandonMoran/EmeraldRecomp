"""Diagnostic: what actually changes in the bag across a purchase, and how to
leave the Mart counter. Run once; prints only, appends to its own transcript."""

import struct
import sys

sys.path.insert(0, "artifacts/playtest")

import catch_final as cf
from pad import Pad
from maps import Grid, obj_to_map, npc_tiles
from bot import rd
import navwalk
from checkpoints import Checkpoints

p = Pad(transcript="artifacts/playtest/reports/pocket-probe.txt")


class S:
    def __init__(self, pad):
        self.pad = pad

    def ask(self, **kw):
        return self.pad.ask(**kw)


def window(p):
    sb1 = p.saveblock()
    sb2 = struct.unpack("<I", rd(p.s, "read_iwram", 0x03005D90, 4))[0]
    key = struct.unpack("<H", rd(p.s, "read_ewram", sb2 + 0xAC, 2))[0]
    raw = rd(p.s, "read_ewram", sb1 + 0x560, 0x1A0)
    return sb1, sb2, key, raw


Checkpoints(conn=S(p)).load("rustboro-cleared")
p.frames(150)
cf.unlock(p)
p.say("probe", f"start {cf.curmap(p)} {obj_to_map(*navwalk.settled(p))}")

gg = Grid('LAYOUT_RUSTBORO_CITY_GYM')
cf.go_to_warp(p, gg, [(5, 19), (6, 19)], (0, 3), "gym_out",
              people=npc_tiles('RustboroCity_Gym'))
tw = Grid('LAYOUT_RUSTBORO_CITY')
cf.go_to_warp(p, tw, [(16, 45)], (11, 7), "mart_door", people=npc_tiles('RustboroCity'))
p.say("probe", f"in mart {cf.curmap(p)} {obj_to_map(*navwalk.settled(p))}")

sb1_a, sb2_a, key_a, raw_a = window(p)
p.say("probe", f"before: sb1 {sb1_a:#x} key {key_a:#06x}")

cf.buy_first_ball(p)
cf.finish_shop(p, "probe_shop")

sb1_b, sb2_b, key_b, raw_b = window(p)
p.say("probe", f"after: sb1 {sb1_b:#x} key {key_b:#06x}")

if sb1_a == sb1_b and key_a == key_b:
    for i in range(0, len(raw_a), 2):
        if raw_a[i:i + 2] != raw_b[i:i + 2]:
            a, b = raw_a[i:i + 2], raw_b[i:i + 2]
            qa = struct.unpack("<H", a)[0] ^ key_a
            qb = struct.unpack("<H", b)[0] ^ key_b
            p.say("probe", f"off +0x{i:03x}: {a.hex()} -> {b.hex()}  qty {qa} -> {qb}")
else:
    p.say("probe", "bag window moved (saveblock or key changed) - need a stable read")

st = p.status()
p.say("probe", f"scene {st.get('scene')} items {st.get('items')} sel {st.get('selected')} "
               f"msg {(st.get('message') or '')[:50]!r}")

d = p.ask(cmd="emerald_dev_state")
p.say("probe", f"locked {d.get('controls_locked')} mbox {d.get('message_box')} "
               f"tile {obj_to_map(*navwalk.settled(p))} map {cf.curmap(p)}")

for attempt in range(3):
    st = p.status()
    if st.get("scene") != "shop":
        break
    p.action("cancel", 22)
    p.frames(70)
    d = p.ask(cmd="emerald_dev_state")
    p.say("probe", f"cancel {attempt}: scene {p.status().get('scene')} "
                   f"locked {d.get('controls_locked')} mbox {d.get('message_box')} "
                   f"msg {(p.status().get('message') or '')[:40]!r}")

for i in range(8):
    if cf.curmap(p) != (11, 7):
        break
    moved, _ = p.step("south")
    p.frames(85)
    d = p.ask(cmd="emerald_dev_state")
    p.say("probe", f"south {i}: moved {moved} tile {obj_to_map(*navwalk.settled(p))} "
                   f"map {cf.curmap(p)} scene {p.scene()} locked {d.get('controls_locked')} "
                   f"mbox {d.get('message_box')}")

p.say("probe", f"end {cf.curmap(p)} {obj_to_map(*navwalk.settled(p))} scene {p.scene()}")

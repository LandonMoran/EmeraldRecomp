"""Write a real Pokémon into party slot 0.

The checkpoints only ever held test blocks (the "Torchic" in party-starter is a
nicknamed placeholder: its species field is not 255), and a test block is why a
battle hangs after "gained EXP. Points!". This builds a genuine Torchic from the
game's own numbers instead:

    base stats   45 / 60 / 40 / 45 / 70 / 50   (species_info.h, SPECIES_TORCHIC)
    growth rate  GROWTH_MEDIUM_SLOW            (same entry)
    moves        Scratch, Ember, Peck, Growl   (level-up learnset)

Stats use Gen 3's formula with IV 15, EV 0 and a neutral nature (PID chosen so
PID % 25 == 0), so what is written matches exactly what the game would compute
for this Pokémon.

    python3 artifacts/playtest/make_mon.py --level 40
"""

import argparse
import struct
import sys

sys.path.insert(0, "artifacts/playtest")

from bot import rd  # noqa: E402
from checkpoints import Checkpoints  # noqa: E402
from pad import Pad  # noqa: E402

PARTY = 0x020244EC
COUNT = 0x020244E9
MY_OTID = 0x816EACCF          # IDNo. 44239, read from SaveBlock2

# substruct order table, indexed by PID % 24
ORDERS = [(0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 1, 3), (0, 3, 1, 2), (0, 2, 3, 1), (0, 3, 2, 1),
          (1, 0, 2, 3), (1, 0, 3, 2), (2, 0, 1, 3), (3, 0, 1, 2), (2, 0, 3, 1), (3, 0, 2, 1),
          (1, 2, 0, 3), (1, 3, 0, 2), (2, 1, 0, 3), (3, 1, 0, 2), (2, 3, 0, 1), (3, 2, 0, 1),
          (1, 2, 3, 0), (1, 3, 2, 0), (2, 1, 3, 0), (3, 1, 2, 0), (2, 3, 1, 0), (3, 2, 1, 0)]

TORCHIC = dict(hp=45, atk=60, df=40, spe=45, spa=70, spd=50)
MOVES = [(10, 35), (52, 25), (64, 35), (45, 40)]   # (move id, PP): Scratch, Ember, Peck, Growl
NICK = bytes([0xCE, 0xC9, 0xCC, 0xBD, 0xC2, 0xC3, 0xBD])   # "TORCHIC"


def exp_for(level, growth=3):
    """GROWTH_MEDIUM_SLOW experience for a level."""
    n = level
    return max(0, 6 * n ** 3 // 5 - 15 * n ** 2 + 100 * n - 140)


def stats_for(level, iv=15):
    def other(base):
        return (2 * base + iv) * level // 100 + 5
    return dict(
        hp=(2 * TORCHIC["hp"] + iv) * level // 100 + level + 10,
        atk=other(TORCHIC["atk"]), df=other(TORCHIC["df"]), spe=other(TORCHIC["spe"]),
        spa=other(TORCHIC["spa"]), spd=other(TORCHIC["spd"]),
    )


def build(level):
    pid = 400000000                       # % 25 == 0 -> neutral nature; % 24 decides order
    assert pid % 25 == 0
    key = pid ^ MY_OTID
    order = ORDERS[pid % 24]

    growth = struct.pack("<HHIBBH", 255, 0, exp_for(level), 0, 70, 0)
    attacks = b"".join(struct.pack("<H", m) for m, _ in MOVES) + bytes(p for _, p in MOVES)
    evs = bytes(12)
    misc = struct.pack("<BBHII", 0, 0, 0, 15 | 15 << 5 | 15 << 10 | 15 << 15 | 15 << 20 | 15 << 25, 0)
    subs = [growth, attacks, evs, misc]
    assert all(len(s) == 12 for s in subs), [len(s) for s in subs]

    plain = b"".join(subs[kind] for kind in order)
    enc = bytearray(plain)
    for i in range(0, 48, 4):
        struct.pack_into("<I", enc, i, struct.unpack_from("<I", enc, i)[0] ^ key)

    st = stats_for(level)
    mon = bytearray(100)
    struct.pack_into("<II", mon, 0, pid, MY_OTID)
    mon[0x08:0x12] = NICK + b"\xff" + b"\x00\x00"
    mon[0x12] = 0x02                      # language: English
    mon[0x13] = 0x00                      # not egg, not bad egg
    mon[0x14:0x1B] = b"\xbb" + b"\xff" * 6   # OT name "A"
    struct.pack_into("<H", mon, 0x1C, sum(struct.unpack("<24H", plain)) & 0xFFFF)
    mon[0x20:0x50] = enc
    mon[0x50] = 0x00                      # status: healthy
    mon[0x54] = level
    mon[0x55] = 0x00                      # pokerus
    struct.pack_into("<HHHHHHH", mon, 0x56, st["hp"], st["hp"], st["atk"], st["df"],
                     st["spe"], st["spa"], st["spd"])
    return bytes(mon), st


def adv(p, n):
    while n > 0:
        k = min(n, 300)
        p.frames(k)
        n -= k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=40)
    ap.add_argument("--checkpoint", default="mauville-plate4-before")
    ap.add_argument("--save", default="mauville-real-mon")
    args = ap.parse_args()

    mon, st = build(args.level)
    print("built level %d TORCHIC: hp %d atk %d def %d spe %d spa %d spd %d"
          % (args.level, st["hp"], st["atk"], st["df"], st["spe"], st["spa"], st["spd"]),
          flush=True)

    p = Pad(None)
    p.s.settimeout(60)
    ck = Checkpoints(conn=p)
    ck.load(args.checkpoint)
    adv(p, 560)
    p.ask(cmd="write_mem", addr=PARTY, hex=mon.hex())
    p.ask(cmd="write_mem", addr=COUNT, hex="01")
    adv(p, 120)

    back = rd(p.s, "read_ewram", PARTY, 100)
    print("read back: level %d hp %s match %s"
          % (back[0x54], struct.unpack_from("<HH", back, 0x56), back == mon), flush=True)
    ck.save(args.save, "level-%d TORCHIC built from game data" % args.level)
    print("saved %s" % args.save, flush=True)


if __name__ == "__main__":
    main()

"""Read and prepare the party inside a playtest checkpoint.

Why this exists
---------------
A checkpoint taken before a gym has no party, so the gym's unavoidable trainer
battles lock the field before the puzzle is ever reachable. The party can be
obtained honestly by playing the Route 101 rescue (the starter is created by the
game's own script), but a level 5 starter loses to a gym trainer.

This module is harness scaffolding, exactly like the bag writes the battle
transcripts use: it reads ``gPlayerParty`` and can set a *test* stat block so
battles can be won while the puzzle is what gets measured. It never touches the
player's save file, and a checkpoint boosted this way is labelled as such in the
playtest report.

Layout
------
``struct Pokemon`` from the pinned decompilation
(third_party/pokeemerald/include/pokemon.h, c2dcc629): BoxPokemon (0x50 bytes)
followed by status, level, mail, hp, maxHP and the five battle stats. PP lives
inside the encrypted Moves substruct and is deliberately left alone, so a
boosted checkpoint keeps the moves and PP the game gave it.

``gPlayerParty`` is a 6 x 0x64 array at 0x020244EC with its count at 0x020244E9
(variants/emerald/symbols/imported_data_symbols.tsv).

    python3 artifacts/playtest/party.py --dump
    python3 artifacts/playtest/party.py --boost --level 50
"""

import argparse
import struct
import sys

sys.path.insert(0, "artifacts/playtest")

from tcp import Conn  # noqa: E402

G_PARTY_COUNT = 0x020244E9
G_PARTY = 0x020244EC
PARTY_SIZE = 6
MON_SIZE = 0x64

OFF_LEVEL = 0x54
OFF_HP = 0x56
OFF_MAX_HP = 0x58
OFF_ATTACK = 0x5A
OFF_DEFENSE = 0x5C
OFF_SPEED = 0x5E
OFF_SP_ATTACK = 0x60
OFF_SP_DEFENSE = 0x62

# A stat block a level-50 Pokémon could plausibly have: enough to win a gym
# trainer battle, not enough to be mistaken for a legitimate team.
BOOST_DEFAULT = {"level": 50, "hp": 400, "attack": 300, "defense": 300,
                 "speed": 300, "sp_attack": 300, "sp_defense": 300}


def read_ewram(conn, addr, n):
    """Read EWRAM through tcp.Conn or through a Pad (which owns a socket)."""
    if hasattr(conn, "read_ewram"):
        return conn.read_ewram(addr, n)
    reply = conn.ask(cmd="read_ewram", addr=addr, len=n)
    if reply.get("error"):
        raise RuntimeError(f"read_ewram at 0x{addr:08X}: {reply['error']}")
    data = reply.get("data")
    if data is None:
        data = reply.get("hex", "")
    return bytes(data) if isinstance(data, list) else bytes.fromhex(data)


def _write(conn, addr, blob):
    if hasattr(conn, "write"):
        return conn.write(addr, blob)
    reply = conn.ask(cmd="write_mem", addr=addr, hex=blob.hex())
    if reply.get("error"):
        raise RuntimeError(f"write_mem at 0x{addr:08X}: {reply['error']}")
    return reply


def count(conn):
    return read_ewram(conn, G_PARTY_COUNT, 1)[0]


def read_mon(conn, index):
    base = G_PARTY + index * MON_SIZE
    raw = read_ewram(conn, base, MON_SIZE)

    def u16(off):
        return struct.unpack_from("<H", raw, off)[0]

    return {
        "index": index,
        "address": base,
        "personality": struct.unpack_from("<I", raw, 0x00)[0],
        "ot_id": struct.unpack_from("<I", raw, 0x04)[0],
        "status": struct.unpack_from("<I", raw, 0x50)[0],
        "level": raw[OFF_LEVEL],
        "hp": u16(OFF_HP),
        "max_hp": u16(OFF_MAX_HP),
        "attack": u16(OFF_ATTACK),
        "defense": u16(OFF_DEFENSE),
        "speed": u16(OFF_SPEED),
        "sp_attack": u16(OFF_SP_ATTACK),
        "sp_defense": u16(OFF_SP_DEFENSE),
    }


def dump(conn):
    n = count(conn)
    return [read_mon(conn, i) for i in range(min(n, PARTY_SIZE))]


def boost(conn, **overrides):
    """Set level and battle stats on every party member, full HP included.

    The level byte is what the game reports and what damage uses; exp is left
    at the value the game gave the Pokémon, so nothing levels up on its own.
    """
    stats = dict(BOOST_DEFAULT)
    stats.update({k: v for k, v in overrides.items() if v is not None})
    n = count(conn)
    for i in range(min(n, PARTY_SIZE)):
        base = G_PARTY + i * MON_SIZE
        level = min(int(stats["level"]), 100)
        hp = min(int(stats["hp"]), 0xFFFF)
        max_hp = max(hp, 1)
        _write(conn, base + OFF_LEVEL, bytes([level]))
        blob = struct.pack("<HHHHHHH", hp, max_hp,
                           min(int(stats["attack"]), 0xFFFF),
                           min(int(stats["defense"]), 0xFFFF),
                           min(int(stats["speed"]), 0xFFFF),
                           min(int(stats["sp_attack"]), 0xFFFF),
                           min(int(stats["sp_defense"]), 0xFFFF))
        _write(conn, base + OFF_HP, blob)
    return dump(conn)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=19892)
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--boost", action="store_true")
    ap.add_argument("--level", type=int, default=None)
    ap.add_argument("--hp", type=int, default=None)
    args = ap.parse_args()

    conn = Conn(port=args.port)
    if args.boost:
        mons = boost(conn, level=args.level, hp=args.hp)
        print(f"boosted {len(mons)} party member(s)")
    if args.dump or not args.boost:
        mons = dump(conn)
        print(f"party count {count(conn)}")
        for m in mons:
            print(f"  [{m['index']}] level {m['level']:3d}  hp {m['hp']:3d}/{m['max_hp']:3d}"
                  f"  atk {m['attack']:3d} def {m['defense']:3d} spd {m['speed']:3d}"
                  f"  spa {m['sp_attack']:3d} spd {m['sp_defense']:3d}"
                  f"  pid {m['personality']:08X}")


if __name__ == "__main__":
    main()

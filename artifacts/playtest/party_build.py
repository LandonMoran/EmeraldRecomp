"""Give the party a second, structurally valid member for a double battle.

Tate & Liza refuse a party of one, and Emerald's double battle needs two
healthy Pokémon before the leaders agree to fight. The test save owns one
Torchic and nothing in the PC box, so the harness builds the second slot the
way the game itself would: a real ``struct Pokemon`` with its own personality
value, its own IVs and its own checksum, encrypted with the Gen 3 cipher.

Layout (verified against the running save, not guessed)
-------------------------------------------------------
``gPlayerParty`` is 6 x 0x64 at 0x020244EC, count at 0x020244E9. Inside one
slot:

    0x00  personality (u32)
    0x04  OT id       (u32)
    0x08  nickname    (10 bytes, Gen 3 charset, 0xFF terminated)
    0x12  language    (u8)
    0x13  flags       (u8, 0x02 = has species)
    0x1C  checksum    (u16, sum of the 48 decrypted bytes as 24 u16s)
    0x20  four 12-byte substructs, XOR-encrypted with personality ^ OT id
    0x50  status (u32), 0x54 level, 0x55 mail, 0x56 hp, 0x58 max hp,
          0x5A..0x62 the five battle stats

The four substructs are ordered by ``personality % 24``; changing the
personality therefore means re-ordering them, or the game reads a growth block
where the moves should be. The cipher is the Gen 3 one - every 32-bit word
XORed with ``personality ^ OT id``, no LCG (that arrives with the DS games) -
which is why a re-encryption needs nothing but the two ids.

    python3 artifacts/playtest/party_build.py --add    # make slot 1 real
    python3 artifacts/playtest/party_build.py --dump   # decrypt what is there
"""

import argparse
import struct
import sys

sys.path.insert(0, "artifacts/playtest")

from party import G_PARTY, G_PARTY_COUNT, MON_SIZE, _write, read_ewram  # noqa: E402
from tcp import Conn  # noqa: E402

OFF_PERSONALITY = 0x00
OFF_OT_ID = 0x04
OFF_NICKNAME = 0x08
OFF_LANGUAGE = 0x12
OFF_FLAGS = 0x13
OFF_CHECKSUM = 0x1C
OFF_SECURE = 0x20
SECURE_SIZE = 48
OFF_STATUS = 0x50
OFF_LEVEL = 0x54
OFF_PARTY_TAIL = 0x50          # status .. sp_defense, 0x14 bytes

GROWTH, ATTACKS, EVS, MISC = 0, 1, 2, 3

# Which substruct sits in each of the four on-cart positions, for pid % 24.
ORDER = [
    (0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 1, 3), (0, 3, 1, 2), (0, 2, 3, 1), (0, 3, 2, 1),
    (1, 0, 2, 3), (1, 0, 3, 2), (2, 0, 1, 3), (3, 0, 1, 2), (2, 0, 3, 1), (3, 0, 2, 1),
    (1, 2, 0, 3), (1, 3, 0, 2), (2, 1, 0, 3), (3, 1, 0, 2), (2, 3, 0, 1), (3, 2, 0, 1),
    (1, 2, 3, 0), (1, 3, 2, 0), (2, 1, 3, 0), (3, 1, 2, 0), (2, 3, 1, 0), (3, 2, 1, 0),
]


def xor_secure(blob, key):
    out = bytearray(blob)
    for i in range(0, SECURE_SIZE, 4):
        word = struct.unpack_from("<I", out, i)[0] ^ key
        struct.pack_into("<I", out, i, word)
    return bytes(out)


def checksum(plain):
    return sum(struct.unpack("<24H", plain)) & 0xFFFF


def decrypt(raw):
    """Split a 0x64 slot into its fields and its four plaintext substructs."""
    pid, otid = struct.unpack_from("<II", raw, OFF_PERSONALITY)
    plain = xor_secure(raw[OFF_SECURE:OFF_SECURE + SECURE_SIZE], pid ^ otid)
    order = ORDER[pid % 24]
    by_id = {}
    for position, substruct in enumerate(order):
        by_id[substruct] = plain[position * 12:(position + 1) * 12]
    return {
        "personality": pid,
        "ot_id": otid,
        "nickname": raw[OFF_NICKNAME:OFF_NICKNAME + 10],
        "language": raw[OFF_LANGUAGE],
        "flags": raw[OFF_FLAGS],
        "checksum": struct.unpack_from("<H", raw, OFF_CHECKSUM)[0],
        "stored_checksum": checksum(plain),
        "tail": raw[OFF_PARTY_TAIL:OFF_PARTY_TAIL + 0x14],
        "substructs": by_id,
    }


def describe(mon):
    growth = mon["substructs"][GROWTH]
    attacks = mon["substructs"][ATTACKS]
    misc = mon["substructs"][MISC]
    evs = mon["substructs"][EVS]
    return {
        "species": struct.unpack_from("<H", growth, 0)[0],
        "item": struct.unpack_from("<H", growth, 2)[0],
        "exp": struct.unpack_from("<I", growth, 4)[0],
        "moves": list(struct.unpack_from("<4H", attacks, 0)),
        "pp": list(attacks[8:12]),
        "ivs": struct.unpack_from("<I", misc, 4)[0],
        "evs": list(evs[:6]),
        "level": mon["tail"][OFF_LEVEL - OFF_PARTY_TAIL],
    }


def encrypt(mon, personality, ot_id, nickname=None, ivs=None):
    """Pack a slot back with a new personality, re-ordered and re-checksummed."""
    subs = dict(mon["substructs"])
    if ivs is not None:
        misc = bytearray(subs[MISC])
        struct.pack_into("<I", misc, 4, ivs)
        subs[MISC] = bytes(misc)
    order = ORDER[personality % 24]
    plain = b"".join(subs[substruct] for substruct in order)
    raw = bytearray(MON_SIZE)
    struct.pack_into("<II", raw, OFF_PERSONALITY, personality, ot_id)
    raw[OFF_NICKNAME:OFF_NICKNAME + 10] = nickname or mon["nickname"]
    raw[OFF_LANGUAGE] = mon["language"]
    raw[OFF_FLAGS] = mon["flags"]
    struct.pack_into("<H", raw, OFF_CHECKSUM, checksum(plain))
    raw[OFF_SECURE:OFF_SECURE + SECURE_SIZE] = xor_secure(plain, personality ^ ot_id)
    raw[OFF_PARTY_TAIL:OFF_PARTY_TAIL + 0x14] = mon["tail"]
    return bytes(raw)


def add_second(conn, source=0, index=1, personality=0x5A17C0DE, ivs=0x3FFFFFFF):
    """Write a second slot built from `source`, with its own PID and IVs.

    The OT stays the player's own: a traded monster above the badge's obey
    level can refuse orders, and that is a rule this playtest does not need to
    argue with. Everything else in the slot is the source's - it is the same
    species, so the growth, move and EV blocks are the source's own data, just
    carried under a different personality.
    """
    src = read_ewram(conn, G_PARTY + source * MON_SIZE, MON_SIZE)
    mon = decrypt(src)
    if mon["checksum"] != mon["stored_checksum"]:
        raise SystemExit("source slot checksum mismatch: the layout assumptions are wrong")
    if personality % 24 == mon["personality"] % 24:
        # Same order would work, but a distinct PID%24 exercises the re-order path.
        personality ^= 0x00010000
    second = encrypt(mon, personality, mon["ot_id"],
                     nickname=b"EMBER\xff\x00\x00\x00\x00\x00", ivs=ivs)
    _write(conn, G_PARTY + index * MON_SIZE, second)
    _write(conn, G_PARTY_COUNT, bytes([max(conn_count(conn), index + 1)]))
    check = decrypt(read_ewram(conn, G_PARTY + index * MON_SIZE, MON_SIZE))
    if check["checksum"] != check["stored_checksum"]:
        raise SystemExit("written slot does not verify")
    return describe(check)


def conn_count(conn):
    return read_ewram(conn, G_PARTY_COUNT, 1)[0]


# Max PP of the moves this save's starter knows, from the game's move table.
MAX_PP = {10: 35, 45: 40, 52: 25, 64: 35}


def restore_pp(conn):
    """Set every party member's moves back to full PP, through the cipher.

    A double battle against Tate & Liza runs long (four Pokémon, two Hyper
    Potions), and a starter that has been through the other seven gyms has
    nothing left in the tank. This is the same class of shortcut as the test
    stat block in party.py, and it is written the way the game stores it - the
    Attacks substruct is edited in plaintext and re-encrypted with the slot's
    own key, then the checksum follows.
    """
    out = []
    for i in range(conn_count(conn)):
        raw = read_ewram(conn, G_PARTY + i * MON_SIZE, MON_SIZE)
        mon = decrypt(raw)
        attacks = bytearray(mon["substructs"][ATTACKS])
        moves = struct.unpack_from("<4H", attacks, 0)
        for slot, move in enumerate(moves):
            attacks[8 + slot] = MAX_PP.get(move, attacks[8 + slot])
        mon["substructs"] = dict(mon["substructs"])
        mon["substructs"][ATTACKS] = bytes(attacks)
        fixed = encrypt(mon, mon["personality"], mon["ot_id"])
        _write(conn, G_PARTY + i * MON_SIZE, fixed)
        check = decrypt(read_ewram(conn, G_PARTY + i * MON_SIZE, MON_SIZE))
        out.append(list(check["substructs"][ATTACKS][8:12]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=19892)
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--personality", type=lambda v: int(v, 0), default=0x5A17C0DE)
    ap.add_argument("--ivs", type=lambda v: int(v, 0), default=0x3FFFFFFF)
    args = ap.parse_args()

    conn = Conn(port=args.port)
    if args.add:
        info = add_second(conn, personality=args.personality, ivs=args.ivs)
        print("second slot:", info, "party count", conn_count(conn))
    if args.dump or not args.add:
        n = conn_count(conn)
        print("party count", n)
        for i in range(max(n, 1)):
            raw = read_ewram(conn, G_PARTY + i * MON_SIZE, MON_SIZE)
            mon = decrypt(raw)
            print(f"  [{i}] pid {mon['personality']:08X} ot {mon['ot_id']:08X}"
                  f" cks {mon['checksum']:04X}/{mon['stored_checksum']:04X}", describe(mon))


if __name__ == "__main__":
    main()

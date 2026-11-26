"""Pad driver for EmeraldRecomp playtests.

Why this exists
---------------
The runtime re-latches KEYINPUT every frame from the mod's own per-frame input
hook, so poking the keypad register over TCP (``set_keyinput``) never survives
a frame: the game reads 0 keys and the field ignores you. Input has to go
through ``emerald_a11y_action``, which the hook turns into a real held press.

Since 2026-11-26 a pad direction in the overworld is a *step request* (the mod
holds the key for ~one tile) instead of a one-frame nudge, so one action moves
exactly one tile. In menus the same action is still a single-frame tap.

Everything here is harness code. Nothing in this file ships with the mod.
"""

import struct
import sys
import time

sys.path.insert(0, "/tmp")
sys.path.insert(0, "artifacts/playtest")

from p import ask                      # noqa: E402  (TCP helpers)
from bot import rd                     # noqa: E402

GOBJ = 0x02037350                      # gObjectEvents
GAVATAR = 0x02037590                   # gPlayerAvatar
GSB1PTR = 0x03005D8C                   # gSaveBlock1Ptr
GMAIN = 0x030022C0                     # gMain
CB2_LOADMAP = 0x08085FCD               # CB2_LoadMap | thumb bit

MAP_NAME = {(0, 9): "LittlerootTown", (0, 16): "Route101", (0, 17): "OldaleTown",
            (25, 40): "InsideOfTruck"}


class Pad:
    def __init__(self, transcript=None):
        import bot
        self.s = bot.conn()
        self.s.settimeout(20)
        self.log_index = 0
        self.transcript = transcript
        self.lines = []
        if transcript:
            open(transcript, "w").close()

    # ── transport ────────────────────────────────────────────────────────
    def ask(self, **kw):
        return ask(self.s, kw)

    def frames(self, n):
        r = self.ask(cmd="run_frames", n=n)
        if isinstance(r, dict) and r.get("error"):
            raise RuntimeError(f"run_frames({n}): {r['error']}")

    def status(self):
        return self.ask(cmd="emerald_a11y_status")

    def nav(self):
        return self.ask(cmd="emerald_a11y_nav")

    def scene(self):
        return self.status().get("scene", "")

    def box(self):
        st = self.status()
        return bool(st.get("box_open") or st.get("box"))

    def menu(self):
        return bool(self.status().get("menu"))

    # ── state ────────────────────────────────────────────────────────────
    def pid(self):
        return rd(self.s, "read_ewram", GAVATAR + 5, 1)[0]

    def obj(self):
        e = rd(self.s, "read_ewram", GOBJ + 0x24 * self.pid(), 0x24)
        return {
            "x": struct.unpack("<h", e[0x10:0x12])[0],
            "y": struct.unpack("<h", e[0x12:0x14])[0],
            "flags0": e[0], "flags1": e[1], "flags2": e[2],
            "facing": e[0x18] & 0xF, "map_num": e[9], "map_group": e[10],
            "elevation": e[0x0B] & 0xF,
        }

    def map(self):
        o = self.obj()
        return (o["map_group"], o["map_num"])

    def map_name(self):
        return MAP_NAME.get(self.map(), str(list(self.map())))

    def grass(self):
        """In tall grass (ObjectEvent.inShortGrass, byte 2 bit 2)."""
        return bool(self.obj()["flags2"] & 0x04)

    def saveblock(self):
        return struct.unpack("<I", rd(self.s, "read_iwram", GSB1PTR, 4))[0]

    def keys(self):
        b = rd(self.s, "read_iwram", GMAIN + 0x28, 8)
        return struct.unpack("<HHHH", b)

    # ── speech ───────────────────────────────────────────────────────────
    def words(self):
        r = self.ask(cmd="emerald_a11y_log")
        u = r.get("utterances") or []
        new = u[self.log_index:]
        self.log_index = len(u)
        return [(x["frame"], x["text"]) for x in new]

    def say(self, tag, text=""):
        line = f"[{tag}] {text}".rstrip()
        self.lines.append(line)
        if self.transcript:
            with open(self.transcript, "a") as fh:
                fh.write(line + "\n")
        return line

    def flush_speech(self, tag):
        for frame, text in self.words():
            self.say(f"{tag} f{frame}", text)

    # ── input ────────────────────────────────────────────────────────────
    def action(self, name, frames=6):
        self.ask(cmd="emerald_a11y_action", action=name)
        self.frames(frames)

    def confirm(self, wait=26):
        self.action("confirm", 2)
        self.frames(wait)

    def cancel(self, wait=16):
        self.action("cancel", 2)
        self.frames(wait)

    def start(self, wait=20):
        self.action("start", 2)
        self.frames(wait)

    def step(self, direction, settle=52):
        """One pad direction. Returns (moved, obj-after)."""
        before = self.obj()
        self.ask(cmd="emerald_a11y_action", action=direction)
        self.frames(settle)
        after = self.obj()
        moved = (after["x"], after["y"]) != (before["x"], before["y"])
        return moved, after

    def walk(self, direction, tiles=1, tag="walk"):
        """Walk up to `tiles` tiles, stopping if the game stops moving us."""
        out = 0
        for i in range(tiles):
            moved, o = self.step(direction)
            self.flush_speech(f"{tag}{i + 1}")
            if not moved:
                # one retry: the first press may only have turned us
                moved, o = self.step(direction)
                self.flush_speech(f"{tag}{i + 1}b")
                if not moved:
                    self.say(tag, f"blocked at ({o['x']},{o['y']}) facing {o['facing']}")
                    break
            out += 1
            self.say(tag, f"({o['x']},{o['y']}) facing {o['facing']}"
                          f"{' grass' if self.grass() else ''}")
            if self.scene() == "battle":
                self.say(tag, "BATTLE STARTED")
                break
        return out

    def advance_all_text(self, limit=40):
        for _ in range(limit):
            if not self.box():
                return True
            self.confirm(30)
        return False

    def npc_tiles(self):
        """Tiles occupied by other people/objects on this map (plan around them)."""
        out = set()
        me = self.pid()
        mg, mn = self.obj()["map_group"], self.obj()["map_num"]
        for i in range(16):
            if i == me:
                continue
            e = rd(self.s, "read_ewram", GOBJ + 0x24 * i, 0x24)
            if not (e[0] & 0x01):            # not active
                continue
            if e[1] & 0x60:                  # invisible / off-screen
                continue
            if e[2] & 0x01:                  # the player
                continue
            if e[9] != mn or e[10] != mg:    # other map
                continue
            out.add((struct.unpack("<h", e[0x10:0x12])[0],
                     struct.unpack("<h", e[0x12:0x14])[0]))
        return out

    # ── harness scaffolding ──────────────────────────────────────────────
    def force_map(self, group, num, x, y, settle=240):
        """Harness-only: make the game load a map from a chosen location.

        The intro's truck scene leaves this build with the player object parked
        outside the 5x5 truck layout (9,9), where every direction is blocked, so
        nothing can be walked. Rather than trust a save file, we write the
        SaveBlock location and point gMain.callback2 at CB2_LoadMap: the game
        then performs its own map load (scripts, object spawn, warp arrow
        update) exactly as a warp would.
        """
        sb1 = self.saveblock()
        blob = (struct.pack("<hh", x, y) + bytes([group, num, 0xFF, 0]) +
                struct.pack("<hh", x, y))
        self.ask(cmd="write_mem", addr=sb1, hex=blob.hex())
        self.ask(cmd="write_mem", addr=GMAIN + 4,
                 hex=struct.pack("<I", CB2_LOADMAP).hex())
        self.frames(settle)
        self.say("scaffold", f"force_map -> {self.map_name()} at "
                             f"({self.obj()['x']},{self.obj()['y']})")


def boot_to_field(p, name_ok=True):
    """Title -> naming -> yes/no -> field, pressing A like a player would."""
    # The BIOS intro runs before the game; nothing the pad does matters until
    # the scene is no longer "unknown".
    for _ in range(80):
        if p.scene() not in ("", "unknown"):
            break
        p.frames(150)
    p.say("boot", f"scene {p.scene()}")
    for _ in range(400):
        if p.scene() == "naming":
            break
        p.confirm(26)
    p.say("boot", f"naming reached, scene {p.scene()}")
    if name_ok:
        # Start jumps to OK, A accepts the name, then "So it's ...?" wants a
        # Yes. Stay on the naming screen until the game leaves it.
        p.start(3)
        p.frames(30)
        for _ in range(10):
            if p.scene() != "naming":
                break
            p.confirm(28)
    # Intro movie + Birch's send-off: nothing here can be hurt by A, and the
    # text boxes in this stretch are drawn by code the field probes do not
    # cover, so press A rather than waiting for a box to be detected.
    for _ in range(200):
        if p.scene() == "overworld":
            break
        p.confirm(22)
    p.frames(200)
    p.say("boot", f"field: scene {p.scene()} map {p.map_name()} "
                  f"({p.obj()['x']},{p.obj()['y']})")

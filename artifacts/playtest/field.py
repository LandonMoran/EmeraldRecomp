"""Field driver for EmeraldRecomp playtests (no /tmp dependency).

A thin wrapper over the TCP debug protocol in gbarecomp/TCP.md plus the
accessibility commands the mod registers (emerald_a11y_*). Everything the
harness presses goes through ``emerald_a11y_action``, i.e. the same queued-action
path TalkBack uses on Android, so the speech these presses produce is produced by
the game, not by the harness.
"""

import struct

from tcp import Conn

GOBJ = 0x02037350          # gObjectEvents, stride 0x24
GAVATAR = 0x02037590       # gPlayerAvatar
GSB1PTR = 0x03005D8C       # gSaveBlock1Ptr
GMAIN = 0x030022C0         # gMain (callback2 at +4)
CB2_LOADMAP = 0x08085FCD   # CB2_LoadMap | thumb
SFIELDMESSAGEBOX = 0x020375BC   # sFieldMessageBoxMode (non-zero = box up)
GSTRINGVAR4 = 0x02021FC4        # full text of the box being drawn

MAP_NAME = {
    (0, 9): "LittlerootTown",
    (0, 16): "Route101",
    (0, 17): "OldaleTown",
    (25, 40): "InsideOfTruck",
    (0, 10): "OldaleTown",        # proven by the town sign it reads
    (1, 0): "PlayersHouse1F",
    (1, 1): "PlayersHouse2F",     # the bedroom: wall clock, PC, posters
    (25, 1): "BrendansHouse2F",   # not used; kept for older saves
}


class Field:
    def __init__(self, port=19892, transcript=None):
        self.c = Conn(port=port)
        self.stats = {"frames": 0, "actions": 0}
        self.log_index = 0
        self.lines = []
        self.transcript = transcript
        if transcript:
            open(transcript, "w").close()

    # ── transport ────────────────────────────────────────────────────────
    def ask(self, **kw):
        return self.c.ask(**kw)

    def frames(self, n):
        r = self.ask(cmd="run_frames", n=n)
        if isinstance(r, dict) and r.get("error"):
            raise RuntimeError(f"run_frames({n}): {r['error']}")
        self.stats["frames"] += n
        return r

    def status(self):
        return self.ask(cmd="emerald_a11y_status")

    def nav(self):
        return self.ask(cmd="emerald_a11y_nav")

    def scene(self):
        return self.status().get("scene", "")

    def box(self):
        """A field message box is on screen (sFieldMessageBoxMode != 0).

        The a11y status' own "message" field is the *last* thing spoken and
        stays set forever, so it cannot be used to answer "is a box open"; the
        game's own flag is the truth. Directions are ignored by the game while
        a box is up, so every walk here is gated on this.
        """
        return self.c.read_ewram(SFIELDMESSAGEBOX, 1)[0] != 0

    def menu(self):
        return bool(self.status().get("menu"))

    def busy(self):
        st = self.status()
        return bool(st.get("box_open") or st.get("box") or st.get("menu")
                    or st.get("list") or st.get("battle"))

    def frame(self):
        return self.status().get("frame", 0)

    # ── player object ────────────────────────────────────────────────────
    def pid(self):
        return self.c.read_ewram(GAVATAR + 5, 1)[0]

    def obj(self):
        e = self.c.read_ewram(GOBJ + 0x24 * self.pid(), 0x24)
        return {
            "x": struct.unpack("<h", e[0x10:0x12])[0],
            "y": struct.unpack("<h", e[0x12:0x14])[0],
            "flags0": e[0], "flags1": e[1], "flags2": e[2],
            "facing": e[0x18] & 0xF, "map_num": e[9], "map_group": e[10],
            "elevation": e[0x0B] & 0xF,
        }

    def tile(self):
        """Map-tile position. Object-event coords carry the field MAP_OFFSET."""
        o = self.obj()
        return (o["x"] - 7, o["y"] - 7)

    def map(self):
        o = self.obj()
        return (o["map_group"], o["map_num"])

    def map_name(self):
        return MAP_NAME.get(self.map(), str(list(self.map())))

    def grass(self):
        return bool(self.obj()["flags2"] & 0x04)

    def saveblock(self):
        return struct.unpack("<I", self.c.read_iwram(GSB1PTR, 4))[0]

    # ── speech ───────────────────────────────────────────────────────────
    def words(self):
        """New utterances since the last call, as (frame, text).

        The mod's log is a 64-entry ring, so positions are not stable: entries
        are tracked by their monotonic ``seq`` and anything older than the ring
        is gone. Indexing by position silently returned nothing once a battle
        printed more than 64 lines between reads.
        """
        r = self.ask(cmd="emerald_a11y_log")
        u = r.get("utterances") or []
        new = [x for x in u if x.get("seq", 0) > self.log_index]
        if new:
            self.log_index = max(x.get("seq", 0) for x in new)
        return [(x["frame"], x["text"]) for x in new]

    def say(self, tag, text=""):
        line = f"[{tag}] {text}".rstrip()
        self.lines.append(line)
        if self.transcript:
            with open(self.transcript, "a") as fh:
                fh.write(line + "\n")
        return line

    def flush_speech(self, tag):
        out = []
        for frame, text in self.words():
            out.append(self.say(f"{tag} f{frame}", text))
        return out

    # ── input ────────────────────────────────────────────────────────────
    def action(self, name, frames=6):
        self.ask(cmd="emerald_a11y_action", action=name)
        self.stats["actions"] += 1
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
        self.stats["actions"] += 1
        self.frames(settle)
        after = self.obj()
        moved = (after["x"], after["y"]) != (before["x"], before["y"])
        return moved, after

    def walk(self, direction, tiles=1, tag="walk"):
        out = 0
        for i in range(tiles):
            moved, o = self.step(direction)
            self.flush_speech(f"{tag}{i + 1}")
            if not moved:
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

    def box_text(self):
        """The whole string the game is drawing in the message box."""
        raw = self.c.read_ewram(GSTRINGVAR4, 240)
        out = []
        for i in range(0, len(raw) - 1, 2):
            ch = raw[i] | (raw[i + 1] << 8)
            if ch in (0xFF, 0xFE, 0x00):
                break
            out.append(chr(ch) if 32 <= ch < 0x2500 else " ")
        return "".join(out)

    def advance_all_text(self, limit=40):
        for _ in range(limit):
            if not self.box():
                return True
            self.confirm(30)
            self.flush_speech("text")
        return False

    def close(self):
        self.c.close()

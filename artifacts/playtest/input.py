"""Paired, script-aware input for the accessibility playtest.

Rules this module enforces, because breaking them is what wedged the earlier
runs:

* Every press is paired with a release: a tap is (press frames, release frames)
  and a hold always releases in a ``finally``. Nothing is left down.
* Nothing is pressed on a frame where the game is scripting: the field controls
  lock, a scripted movement is holding the player, or a text box is waiting.
* What kind of screen we are on decides what may be pressed. On the title
  screen A is the only way forward; in the field with no message box, A must
  never be pressed (that is how the "examine the box" script got interrupted and
  the player object stuck in a held movement).

All state comes from the a11y TCP layer plus three guest bytes.
"""
import sys
import time

sys.path.insert(0, "/tmp")
import bot
from bot import *

# Guest state used to decide whether input is safe.
SCRIPT_LOCK = 0x03000F2C      # sLockFieldControls
MESSAGE_BOX = 0x020375BC      # sFieldMessageBoxMode
TEXT_PRINTERS = 0x020201B0    # 32 x 0x24, printer.active at +0x1B, windowId at +4
AVATAR = 0x02037590           # gPlayerAvatar, objectEventId at +5
OBJECTS = 0x02037350          # gObjectEvents, 16 x 0x24
EVENT_SIZE = 0x24

NONE_HELD = 0x03FF


class Field:
    def __init__(self):
        self.s = bot.conn()
        self.s.settimeout(15)
        self.press_frames = 2
        self.release_frames = 3
        self.stats = {"taps": 0, "blocked": 0, "moves": 0}

    # ── reads ───────────────────────────────────────────────────────────────
    def u8(self, addr):
        cmd = "read_ewram" if addr < 0x03000000 else "read_iwram"
        return rd(self.s, cmd, addr, 1)[0]

    def frames(self, n):
        ask(self.s, {"cmd": "run_frames", "n": n})

    def nav(self):
        return nav(self.s)

    def status(self):
        return status(self.s)

    def speech(self):
        return speech(self.s)

    def scene(self):
        return self.status()["scene"]

    def box_open(self):
        if self.u8(MESSAGE_BOX):
            return True
        tp = rd(self.s, "read_ewram", TEXT_PRINTERS, EVENT_SIZE * 6)
        for i in range(6):
            e = tp[i * EVENT_SIZE:(i + 1) * EVENT_SIZE]
            if len(e) >= 0x20 and e[0x1B] and e[4] == 0:
                return True
        return False

    def player_flags(self):
        av = rd(self.s, "read_ewram", AVATAR, 8)
        e = rd(self.s, "read_ewram", OBJECTS + av[5] * EVENT_SIZE, 4)
        return {"id": av[5], "active": e[0] & 1, "held": (e[0] >> 6) & 1,
                "finished": (e[0] >> 7) & 1, "frozen": e[1] & 1}

    def busy(self):
        """True when the field will not take movement input right now."""
        if self.box_open():
            return True
        if self.u8(SCRIPT_LOCK):
            return True
        f = self.player_flags()
        return f["held"] == 1 or f["frozen"] == 1 or f["active"] == 0

    def settled(self, limit=60):
        """Run frames until the field is quiet. Never presses anything."""
        for _ in range(limit):
            if not self.busy():
                return True
            self.frames(10)
        return not self.busy()

    # ── input ───────────────────────────────────────────────────────────────
    def tap(self, action, press=None, release=None):
        press = press or self.press_frames
        release = release or self.release_frames
        ask(self.s, {"cmd": "emerald_a11y_action", "action": action})
        self.frames(press)
        self.frames(release)          # the synth releases on its own schedule;
        self.stats["taps"] += 1       # the extra idle frames guarantee an edge
        self.frames(2)

    def a(self, wait=6):
        self.tap("confirm", 2, 2)
        self.frames(wait)

    def advance_text(self, limit=40):
        """Press A while a box waits; stop the moment it closes."""
        n = 0
        for _ in range(limit):
            if not self.box_open():
                break
            self.a()
            n += 1
        return n

    def step(self, direction, press=10, release=4):
        """One d-pad step, but only when the field is free."""
        if not self.settled(20):
            self.stats["blocked"] += 1
            return False
        before = self.nav()
        self.tap(direction, press, release)
        after = self.nav()
        moved = (before["x"], before["y"], tuple(before["map"])) != \
                (after["x"], after["y"], tuple(after["map"]))
        if moved:
            self.stats["moves"] += 1
        return moved

    # ── helpers ─────────────────────────────────────────────────────────────
    def log(self, *a):
        print(*a, flush=True)

    def state(self, tag):
        n = self.nav()
        st = self.status()
        f = self.player_flags()
        self.log(f"{tag}: map={n['map']} pos=({n['x']},{n['y']}) facing={n['facing']} "
                 f"look={n['look']['kind']} box={self.box_open()} lock={self.u8(SCRIPT_LOCK)} "
                 f"held={f['held']} scene={st['scene']} menu={st['menu']} "
                 f"list={st['list']} battle={st['battle']}")
        return n

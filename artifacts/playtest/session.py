"""Session helpers on top of live.Link: mashing, walking, transcript capture.

Everything the transcript records is the mod's own utterance log
(``Link.words`` -> the strings handed to the speech sink), never a harness
paraphrase. Map coordinates in this file are *map* coordinates (engine object
coords minus MAP_OFFSET) so they match the decomp's map.json.
"""

import struct
import sys
import time

sys.path.insert(0, "artifacts/playtest")
from live import Link, GOBJ, GAVATAR, GSB1PTR, GMAIN  # noqa: E402

MAP_OFFSET = 7
VAR_INTRO = 0x4092
VAR_HOUSES_BRENDAN = 0x408C
VAR_ROUTE101 = 0x4060


class Session(Link):
    def __init__(self, transcript=None, **kw):
        super().__init__(**kw)
        self.transcript = transcript
        if transcript:
            open(transcript, "w").close()
        self.sb1 = None
        self.all_lines = []

    # ── state ────────────────────────────────────────────────────────────
    def save_block(self):
        if self.sb1 is None:
            self.sb1 = struct.unpack("<I", self.iwram(GSB1PTR, 4))[0]
        return self.sb1

    def var(self, v):
        return struct.unpack("<h", self.ewram(self.save_block() + 0x139C + 2 * (v - 0x4000), 2))[0]

    def pos(self):
        o = self.obj()
        return (o["x"] - MAP_OFFSET, o["y"] - MAP_OFFSET)

    def lock(self):
        return self.iwram(0x03000F2C, 1)[0]

    def box(self):
        return self.ewram(0x020375BC, 1)[0] != 0

    # ── transcript ───────────────────────────────────────────────────────
    def beat(self, tag, scene=None):
        """Flush the mod's newest utterances to the transcript under a tag.

        The scene the mod believes it is in is stored alongside each line so a
        repeat can be judged: the same line twice in one scene is a narration
        bug, the same line after a scene change is the game going back.
        """
        out = []
        fresh = self.words()
        if not fresh:
            return out
        scene = scene if scene is not None else self.status().get("scene", "")
        for frame, text in fresh:
            self.all_lines.append((tag, frame, text, scene))
            out.append(text)
            if self.transcript:
                with open(self.transcript, "a") as fh:
                    fh.write(f"[{tag}] {text}\n")
        return out

    def mark(self, text):
        if self.transcript:
            with open(self.transcript, "a") as fh:
                fh.write(f"# {text}\n")

    # ── input ────────────────────────────────────────────────────────────
    def mash(self, tag, until=None, max_presses=400, gap=4, on_press=None):
        """Press A repeatedly (the way a blind player would) until `until`."""
        for i in range(max_presses):
            self.ask(cmd="emerald_a11y_action", action="confirm")
            self.frames(gap)
            self.beat(tag)
            if until is not None and until():
                return True
            if on_press:
                on_press(i)
        return until is None

    def mash_until_map(self, tag, maps, max_presses=400, gap=4):
        return self.mash(tag, lambda: self.map() in maps, max_presses, gap)

    def face(self, direction):
        self.ask(cmd="emerald_a11y_action", action=direction)
        self.frames(10)

    def step(self, direction, settle=70):
        return super().step(direction, settle)

    def walk_to(self, x, y, tag="walk", tries=3, max_steps=60, settle=70):
        """Axis-aligned walk with one retry per blocked step."""
        self.mark(f"walk to ({x},{y})")
        for _ in range(max_steps):
            cx, cy = self.pos()
            if (cx, cy) == (x, y):
                self.beat(tag)
                return True
            d = None
            if cx != x:
                d = "right" if x > cx else "left"
            elif cy != y:
                d = "down" if y > cy else "up"
            moved = False
            for _try in range(tries):
                moved, _o = self.step(d, settle)
                if moved:
                    break
            self.beat(tag)
            if not moved:
                self.mark(f"blocked going {d} at ({cx},{cy})")
                return False
        return self.pos() == (x, y)

    def interact(self, direction="up"):
        self.face(direction)
        self.beat("look")
        self.ask(cmd="emerald_a11y_action", action="confirm")
        self.frames(24)
        self.beat("use")

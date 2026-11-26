"""Self-contained TCP driver for EmeraldRecomp a11y playtests.

Every line the harness records comes from the mod itself: the runtime keeps the
exact strings handed to the speech sink (``say()`` in
src/accessibility/emerald_a11y.cpp logs, then calls the platform sink), and
``emerald_a11y_log`` returns them. So a transcript built from ``words()`` is the
Android TTS input, not a harness paraphrase.

No dependency outside the standard library; the process under test is
``./build/EmeraldRecomp --tcp 19892`` (see run_session.py).
"""

import json
import socket
import struct
import time

GOBJ = 0x02037350       # gObjectEvents
GAVATAR = 0x02037590    # gPlayerAvatar
GSB1PTR = 0x03005D8C    # gSaveBlock1Ptr
GMAIN = 0x030022C0      # gMain
CB2_LOADMAP = 0x08085FCD

MAP_NAME = {
    (0, 9): "LittlerootTown",
    (0, 10): "LittlerootTown_BrendansHouse_1F",
    (0, 16): "Route101",
    (0, 17): "OldaleTown",
    (25, 40): "InsideOfTruck",
}


class Link:
    def __init__(self, host="127.0.0.1", port=19892, timeout=60, retries=40):
        self.s = None
        last = None
        for _ in range(retries):
            try:
                self.s = socket.create_connection((host, port), timeout=timeout)
                break
            except OSError as exc:      # the emulator may still be booting
                last = exc
                time.sleep(0.5)
        if self.s is None:
            raise RuntimeError(f"no TCP debugger on {host}:{port}: {last}")
        self.s.settimeout(timeout)
        self.buf = b""
        self.log_index = 0

    # ── transport ────────────────────────────────────────────────────────
    def ask(self, **kw):
        self.s.sendall(json.dumps(kw).encode() + b"\n")
        while b"\n" not in self.buf:
            chunk = self.s.recv(1 << 20)
            if not chunk:
                raise RuntimeError("debugger closed the connection")
            self.buf += chunk
        line, _, self.buf = self.buf.partition(b"\n")
        return json.loads(line.decode())

    def frames(self, n):
        out = self.ask(cmd="run_frames", n=int(n))
        if isinstance(out, dict) and out.get("error"):
            raise RuntimeError(f"run_frames({n}): {out['error']}")
        return out

    # ── state ────────────────────────────────────────────────────────────
    def status(self):
        return self.ask(cmd="emerald_a11y_status")

    def scene(self):
        return self.status().get("scene", "")

    def nav(self):
        return self.ask(cmd="emerald_a11y_nav")

    def ewram(self, addr, n):
        r = self.ask(cmd="read_ewram", addr=addr, len=n)
        return bytes.fromhex(r["data"]) if r.get("data") else b""

    def iwram(self, addr, n):
        r = self.ask(cmd="read_iwram", addr=addr, len=n)
        return bytes.fromhex(r["data"]) if r.get("data") else b""

    def write(self, addr, data):
        return self.ask(cmd="write_mem", addr=addr, hex=data.hex())

    def pid(self):
        return self.ewram(GAVATAR + 5, 1)[0]

    def obj(self):
        e = self.ewram(GOBJ + 0x24 * self.pid(), 0x24)
        return {
            "x": struct.unpack("<h", e[0x10:0x12])[0],
            "y": struct.unpack("<h", e[0x12:0x14])[0],
            "flags0": e[0], "flags1": e[1], "flags2": e[2],
            "facing": e[0x18] & 0xF,
            "map_num": e[9], "map_group": e[10],
            "elevation": e[0x0B] & 0xF,
        }

    def map(self):
        o = self.obj()
        return (o["map_group"], o["map_num"])

    def map_name(self):
        return MAP_NAME.get(self.map(), str(list(self.map())))

    def box(self):
        st = self.status()
        return bool(st.get("box_open") or st.get("box"))

    # ── speech ───────────────────────────────────────────────────────────
    def words(self):
        """Utterances the mod handed to the speech sink since the last call."""
        r = self.ask(cmd="emerald_a11y_log")
        u = r.get("utterances") or []
        new = u[self.log_index:]
        self.log_index = len(u)
        return [(x.get("frame", -1), x.get("text", "")) for x in new]

    # ── input ────────────────────────────────────────────────────────────
    def action(self, name, frames=6):
        self.ask(cmd="emerald_a11y_action", action=name)
        self.frames(frames)

    def confirm(self, wait=24):
        self.action("confirm", wait)

    def cancel(self, wait=16):
        self.action("cancel", wait)

    def start(self, wait=20):
        self.action("start", wait)

    def step(self, direction, settle=56):
        before = self.obj()
        self.ask(cmd="emerald_a11y_action", action=direction)
        self.frames(settle)
        after = self.obj()
        moved = (after["x"], after["y"]) != (before["x"], before["y"])
        return moved, after


class Recorder:
    """Collects mod utterances into a transcript, flagging repeats."""

    def __init__(self, path):
        self.path = path
        self.lines = []
        self.seen = {}
        open(path, "w").close()

    def add(self, frame, text):
        self.lines.append((frame, text))
        self.seen[text] = self.seen.get(text, 0) + 1
        with open(self.path, "a") as fh:
            fh.write(f"[f{frame}] {text}\n")

    def drain(self, link, tag=None):
        out = []
        for frame, text in link.words():
            self.add(frame, text)
            out.append(text)
        return out

    def note(self, text):
        with open(self.path, "a") as fh:
            fh.write(f"# {text}\n")

    def duplicates(self):
        return {t: n for t, n in self.seen.items() if n > 1}

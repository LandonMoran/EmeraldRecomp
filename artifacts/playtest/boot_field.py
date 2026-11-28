"""Boot the recompiled game to a usable overworld, then optionally warp.

The rule that keeps the field healthy, learned the hard way:

  * A is pressed freely while the game is not yet in the field (title, movie,
    naming, intro speech);
  * once the field is live, A is pressed *only* while a text box is waiting;
  * directions are the only field input, and only when no box is open and
    `sLockFieldControls` (0x03000F2C) is clear.

Pressing a direction while a box is open does nothing, which looks exactly like
broken input. That is why this script waits for the truck's text box to close
before stepping east out of the truck.

    python3 artifacts/playtest/boot_field.py --spawn
    python3 artifacts/playtest/boot_field.py --spawn --warp 10,0,4,20,north

The emulator is started in its own session so it survives this script.
"""

import argparse
import os
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcp import Conn  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))

SLOCK = 0x03000F2C        # sLockFieldControls
MSGBOX = 0x020375BC       # sFieldMessageBoxMode

SCENE_TIMEOUT = 1800      # frames of boot to tolerate


def port_busy(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


def spawn(port):
    exe = os.path.join(ROOT, "build", "EmeraldRecomp")
    if not os.path.exists(exe):
        sys.exit("no build/EmeraldRecomp — build it first (docs/PLAYTEST.md)")
    log_path = os.path.join(HERE, "dev-emulator.log")
    log = open(log_path, "w")
    proc = subprocess.Popen(
        [exe, "--bios", "gbarecomp/bios/gba_bios.bin",
         "--rom", "variants/emerald/roms/emerald_usa.gba",
         "--tcp", str(port), "--frames", "8000000", "variants/emerald/game.toml"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True)
    print(f"started EmeraldRecomp pid={proc.pid} log={log_path}", flush=True)
    return proc


def wait_tcp(port, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return Conn(port=port, timeout=60)
        except OSError:
            time.sleep(0.5)
    raise SystemExit(f"no debug server on 127.0.0.1:{port}")


class Field:
    def __init__(self, conn):
        self.c = conn

    # ── reads ────────────────────────────────────────────────────────────
    def frames(self, n):
        self.c.ask(cmd="run_frames", n=n)

    def status(self):
        return self.c.ask(cmd="emerald_a11y_status")

    def scene(self):
        return self.status().get("scene", "")

    def u8(self, addr):
        region = "read_ewram" if addr < 0x03000000 else "read_iwram"
        r = self.c.ask(cmd=region, addr=addr, len=1)
        data = r.get("data") or r.get("hex") or ""
        if isinstance(data, list):
            return data[0] if data else 0
        return bytes.fromhex(data)[0] if data else 0

    def lock(self):
        return self.u8(SLOCK)

    def box(self):
        return self.u8(MSGBOX) != 0

    def busy(self):
        return self.box() or self.lock() != 0

    def state(self):
        return self.c.ask(cmd="emerald_dev_state")

    def action(self, name):
        self.c.ask(cmd="emerald_a11y_action", action=name)

    def confirm(self, wait=24):
        self.action("confirm")
        self.frames(wait)

    def step(self, direction, settle=70):
        before = self.state()
        self.action(direction)
        self.frames(settle)
        after = self.state()
        return (before.get("pos") != after.get("pos")), after

    # ── boot ─────────────────────────────────────────────────────────────
    def advance_text(self, limit=40, tag=""):
        n = 0
        for _ in range(limit):
            if not self.box():
                break
            self.confirm(30)
            n += 1
        if tag:
            print(f"  {tag}: advanced {n} lines", flush=True)
        return n

    def boot(self):
        # Everything before the field: A until the naming screen.
        for _ in range(90):
            if self.scene() == "naming":
                break
            if self.scene() == "overworld":
                break
            self.frames(60)
            if not self.box():
                self.confirm(24)
        for _ in range(600):
            if self.scene() == "naming":
                break
            if self.scene() == "overworld":
                break
            self.confirm(24)
        print("scene:", self.scene(), flush=True)

        if self.scene() == "naming":
            self.action("start")
            self.frames(40)
            for _ in range(20):
                if self.scene() != "naming":
                    break
                self.confirm(28)
            print("after naming:", self.scene(), flush=True)

        for _ in range(400):
            if self.scene() == "overworld":
                break
            self.confirm(24)
        self.frames(120)
        print("field scene:", self.scene(), flush=True)

        # Let the truck's opening script finish and its text close.
        for _ in range(240):
            if not self.busy():
                break
            self.advance_text(4)
            self.frames(30)
        self.frames(60)
        self.advance_text(40, "truck")

        # Walk east out of the truck (the only way out) until the map changes.
        for i in range(12):
            if self.scene() != "overworld":
                break
            loc = (self.state().get("location") or {}).get("map")
            if loc != [25, 40]:
                break
            self.advance_text(10)
            moved, after = self.step("right", 80)
            print(f"  truck step {i + 1}: moved={moved} pos={after.get('pos')} "
                  f"map={(after.get('location') or {}).get('map')}", flush=True)
            if not moved:
                self.confirm(40)
                self.frames(40)
        # The post-truck scene keeps the player in a scripted (forced) walk and
        # opens text boxes. Warping out of it carries PLAYER_AVATAR_FLAG_FORCED_MOVE
        # into the new map and the field then ignores the D-pad, so wait until
        # the game really hands control back: box closed, lock clear, no forced
        # move, for a sustained window.
        quiet = 0
        for i in range(240):
            self.advance_text(6)
            free = (not self.busy()) and not self.forced_move()
            quiet = quiet + 1 if free else 0
            if quiet >= 30:
                break
            self.frames(10)
        print(f"field free: quiet={quiet} forced={self.forced_move()} "
              f"box={self.box()} lock={self.lock()}", flush=True)
        self.frames(60)
        return self.state()

    def forced_move(self):
        """PLAYER_AVATAR_FLAG_FORCED_MOVE: a scripted walk owns the player."""
        return bool(self.u8(0x02037590) & 0x20)

    def warp(self, group, num, x, y, facing):
        for _ in range(120):
            if not self.busy() and not self.forced_move():
                break
            self.advance_text(4)
            self.frames(10)
        r = self.c.ask(cmd="emerald_dev_warp", map_group=group, map_num=num,
                       x=x, y=y, facing=facing)
        if not r.get("ok"):
            raise RuntimeError(f"warp refused: {r.get('error')}")
        for _ in range(90):
            self.frames(20)
            w = (self.state().get("warp") or {})
            if w.get("done"):
                return w
        raise RuntimeError("warp never completed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spawn", action="store_true")
    ap.add_argument("--port", type=int, default=19892)
    ap.add_argument("--warp", default="", help="group,num,x,y,facing")
    ap.add_argument("--keep", action="store_true", help="leave the emulator running")
    args = ap.parse_args()

    proc = None
    if args.spawn and not port_busy(args.port):
        proc = spawn(args.port)
    conn = wait_tcp(args.port)
    f = Field(conn)

    state = f.boot()
    print("field:", (state.get("location") or {}), state.get("pos"), flush=True)
    if (state.get("location") or {}).get("map") == [25, 40]:
        raise SystemExit("still inside the truck; boot did not finish")

    if args.warp:
        group, num, x, y, facing = args.warp.split(",")
        w = f.warp(int(group), int(num), int(x), int(y), facing)
        print("warp:", w, flush=True)
        f.frames(120)
        self_state = f.state()
        print("after warp: pos", self_state.get("pos"),
              "lock", self_state.get("controls_locked"),
              "box", self_state.get("message_box"), flush=True)
        # Verify the field really moves here: one step and back.
        moved, after = f.step("north")
        print("test step north:", moved, after.get("pos"), flush=True)
        back, after2 = f.step("south")
        print("test step south:", back, after2.get("pos"), flush=True)

    if not args.keep and proc:
        pass  # the emulator stays up on purpose: callers warp or checkpoint it


if __name__ == "__main__":
    main()

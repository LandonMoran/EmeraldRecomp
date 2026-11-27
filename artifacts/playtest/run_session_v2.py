"""Scripted accessibility session against the real game (headless, this VM).

What this is
------------
A headless session driver for EmeraldRecomp. It launches the actual game
binary, then plays it the way a blind player would: everything is pressed
through ``emerald_a11y_action`` -- the same queued-action path TalkBack and the
pad hotkeys use -- and every line the spoken interface delivers is copied out
of the mod's own utterance log (``emerald_a11y_log``), which is written at the
single point where the mod hands text to its speech sink (``say()`` ->
``g_speak_fn``, the callback Android's JNI bridge registers). Nothing here
prints speech of its own: if the transcript has a line, the game said it.

Why it exists
-------------
There is no Android device in this VM and no audio. The screenshot-proof of a
spoken interface is the text it hands to the platform voice, in order, at the
frame it said it -- which is exactly what this writes to
``transcript-session-v2.txt``.

Scaffolding (disclosed)
-----------------------
Two writes are harness-only and marked in the transcript:

  * ``force_map``   -- SaveBlock1 location + gMain.callback2 = CB2_LoadMap, so
                       the game performs its own map load from a chosen tile.
                       Used to skip the walk from the truck to Route 101.
  * ``VAR_ROUTE101_STATE=1`` -- arms Route 101's rescue coord event, the same
                       value the Littleroot gate script sets.

Everything else (naming, menus, walking, talking, battles) is played.

Run:  python3 artifacts/playtest/run_session_v2.py
"""

import json
import os
import socket
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "../.."))
sys.path.insert(0, HERE)

from field import Field                      # noqa: E402
from mapdata import Layout                   # noqa: E402

OUT = os.path.join(HERE, "transcript-session-v2.txt")
GAME_LOG = os.path.join(HERE, "session-game.log")
PORT = 19892
ARGV = [
    os.path.join(ROOT, "build/EmeraldRecomp"),
    "--bios", "gbarecomp/bios/gba_bios.bin",
    "--rom", "variants/emerald/roms/emerald_usa.gba",
    "--tcp", str(PORT),
    "--frames", "6000000",
    "variants/emerald/game.toml",
]

BEATS = []


def wait_for_port(port, timeout=45.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


# ── Poké Ball path helpers ───────────────────────────────────────────────

SLOCKFIELDCONTROLS = 0x03000F2C   # sLockFieldControls (non-zero = no input)
GSB2PTR = 0x03005D90            # gSaveBlock2Ptr (IWRAM)
SB2_ENCRYPTION_KEY = 0xAC       # struct SaveBlock2.encryptionKey
SB1_BALL_POCKET = 0x650         # struct SaveBlock1.bagPocket_PokeBalls
ITEM_POKE_BALL = 4
ITEM_MASTER_BALL = 1


def grant_balls(f, poke_balls=30, master_balls=1):
    """Put balls in the bag's ball pocket, as a save file would.

    A Poké Ball comes first so the transcript shows an ordinary throw (and, if
    the target breaks free, the game's own failure line). A Master Ball sits
    behind it so the run reaches the catch and nickname screens every time
    instead of depending on the catch roll and Torchic's remaining HP.
    """
    sb1 = f.saveblock()
    sb2 = struct.unpack("<I", f.c.read_iwram(GSB2PTR, 4))[0]
    key = struct.unpack("<I", f.c.read_ewram(sb2 + SB2_ENCRYPTION_KEY, 4))[0]
    # struct ItemSlot { u16 itemId; u16 quantity; }; the quantity is XORed with
    # SaveBlock2.encryptionKey (pokeemerald src/item.c, SetBagItemQuantity).
    low = key & 0xFFFF
    blob = (struct.pack("<HH", ITEM_POKE_BALL, poke_balls ^ low) +
            struct.pack("<HH", ITEM_MASTER_BALL, master_balls ^ low))
    f.ask(cmd="write_mem", addr=sb1 + SB1_BALL_POCKET, hex=blob.hex())
    back = f.c.read_ewram(sb1 + SB1_BALL_POCKET, 8)
    out = []
    for i in range(2):
        item, qty = struct.unpack("<HH", back[4 * i:4 * i + 4])
        out.append({"item": item, "quantity": qty ^ low})
    return {"pocket": hex(sb1 + SB1_BALL_POCKET), "slots": out}


# ── Background events (signs, the wall clock, the TV) ────────────────────

GMAPHDR = 0x02037318          # gMapHeader (MapHeader.events at +4)
BG_EVENT_SIZE = 12            # struct BgEvent: x u16, y u16, elev u8, kind u8, script u32
KIND_FACING = {0: None, 1: 2, 2: 1, 3: 4, 4: 3}   # BG_EVENT_PLAYER_FACING_* -> facing
FACING_STEP = {1: (0, 1), 2: (0, -1), 3: (-1, 0), 4: (1, 0)}   # 1 south .. 4 east
FACE_KEY = {1: "down", 2: "up", 3: "left", 4: "right"}


def bg_events(f):
    """This map's background events, read from the ROM table the game uses.

    The harness reads the same MapEvents.bgEvents array the engine's
    GetBackgroundEventAtPosition walks, so the coordinates it stands on are the
    game's own, not a crib sheet.
    """
    hdr = f.c.read_ewram(GMAPHDR, 0x14)
    events = struct.unpack("<I", hdr[4:8])[0]
    if not (0x08000000 <= events < 0x0A000000):
        return []
    e = f.c.read("rom", events, 0x14)
    count = e[3]
    ptr = struct.unpack("<I", e[0x10:0x14])[0]
    if not (0x08000000 <= ptr < 0x0A000000) or not count:
        return []
    raw = f.c.read("rom", ptr, BG_EVENT_SIZE * count)
    out = []
    for i in range(count):
        b = raw[BG_EVENT_SIZE * i:BG_EVENT_SIZE * (i + 1)]
        x, y, elev, kind = struct.unpack("<HHBB", b[:6])
        script = struct.unpack("<I", b[8:12])[0]
        out.append({"x": x, "y": y, "elev": elev, "kind": kind, "script": script})
    return out


def force_map(f, group, num, x, y):
    """Harness-only: SaveBlock1 position + CB2_LoadMap, i.e. the game's own
    map load from a chosen tile."""
    sb1 = f.saveblock()
    blob = (struct.pack("<hh", x, y) + bytes([group, num, 0xFF, 0]) +
            struct.pack("<hh", x, y))
    f.ask(cmd="write_mem", addr=sb1, hex=blob.hex())
    f.ask(cmd="write_mem", addr=0x030022C0 + 4,
          hex=struct.pack("<I", 0x08085FCD).hex())
    f.frames(300)


def text_of(st):
    return st.get("status") or ""


def items_of(st):
    return [str(x).upper() for x in (st.get("items") or [])]


def naming_ready(st):
    """The nickname keyboard is up: the mod reads its cursor and keys."""
    return "Name entry." in text_of(st)


def frames_until(session, pred, limit=100, wait=10, tag="wait"):
    f = session.f
    st = f.status()
    for i in range(limit):
        if pred(st):
            return st
        f.frames(wait)
        session.harvest(f"{tag}{i}")
        st = f.status()
    return st


def advance_until(session, pred, limit=120, wait=22, tag="adv"):
    f = session.f
    st = f.status()
    for i in range(limit):
        if pred(st):
            return st
        f.confirm(2)
        f.frames(wait)
        session.harvest(f"{tag}{i}")
        st = f.status()
    return st


def in_action_menu(txt):
    """Any of the four battle action labels with its "N of 4" counter."""
    return "of 4." in txt and any(k in txt for k in
                                  ("Fight,", "Bag,", "Pok\xc3\xa9mon,", "Run,"))


def wait_action_menu(session, limit=240, tag="menu"):
    """Advance battle text until FIGHT is the selected battle action.

    Pressing A blindly walks straight through the action menu into the move
    list and a turn, so A is pressed only when no menu is showing; a deeper
    menu is backed out of. The action cursor may still sit on Bag from an
    earlier turn, so the cursor is walked back to Fight before returning.
    """
    f = session.f
    for i in range(limit):
        st = f.status()
        txt = text_of(st)
        if "Fight," in txt:
            return st
        if in_action_menu(txt):
            f.action("up", 2)       # any row -> top row
            f.frames(10)
            f.action("left", 2)     # top row -> FIGHT
            f.frames(10)
        elif "SCRATCH," in txt or "is selected" in txt or "Yes." in txt:
            f.action("cancel", 2)
            f.frames(18)
        else:
            f.action("confirm", 2)
            f.frames(20)
        session.harvest(f"{tag}{i}")
    return f.status()


def open_bag(session, tag):
    """From the battle action menu: Bag, then step to the ball pocket."""
    f = session.f
    st = wait_action_menu(session, 240, f"{tag}-intro")
    if "Fight," not in text_of(st):
        session.line(f"[bag] action menu never came up: {text_of(st)!r}")
        return False
    session.line(f"[bag] action menu: {text_of(st)!r}")
    # The action menu is a 2x2 grid (Fight/Bag, Pokémon/Run): Right reaches Bag.
    for step in ("right", "up", "left", "down"):
        f.action(step, 2)
        f.frames(14)
        session.harvest(f"{tag}-{step}")
        st = frames_until(session, lambda s: "Bag," in text_of(s), 30, 8,
                          f"{tag}-cursor-{step}")
        session.line(f"[bag] after {step}: {text_of(st)!r}")
        if "Bag," in text_of(st):
            break
    f.action("confirm", 2)
    f.frames(24)
    session.harvest(f"{tag}-confirm")
    st = frames_until(session, lambda s: bool(s.get("list")), 80, 10,
                      f"{tag}-open")
    session.line(f"[bag] open: scene={st.get('scene')} items={items_of(st)[:6]}")
    for i in range(4):
        st = f.status()
        if any("BALL" in x for x in items_of(st)):
            break
        f.action("right", 2)
        f.frames(16)
        session.harvest(f"{tag}-right{i}")
        st = frames_until(session, lambda s: bool(s.get("list")), 50, 10,
                          f"{tag}-rightwait{i}")
        session.line(f"[bag] pocket {i}: items={items_of(st)[:6]}")
    session.line(f"[bag] at balls: items={items_of(f.status())[:6]}")
    return True


def pick_ball(session, tag, index=0):
    """Open the bag, pick the index-th ball, press USE."""
    f = session.f
    if not open_bag(session, tag):
        return "no-menu"
    for _ in range(index):
        f.action("down", 2)
        f.frames(14)
        session.harvest(f"{tag}-cursor")
    f.action("confirm", 2)
    f.frames(22)
    session.harvest(f"{tag}-ball")
    st = frames_until(session,
                      lambda s: "is selected" in (s.get("message") or ""),
                      40, 8, f"{tag}-selected")
    session.line(f"[throw] ball selected: {(st.get('message') or '')[:80]!r}")
    f.action("confirm", 2)      # USE
    f.frames(30)
    session.harvest(f"{tag}-use")
    return "thrown"


class Session:
    def __init__(self):
        open(OUT, "w").close()
        self.f = None
        self.proc = None

    # ── transcript ───────────────────────────────────────────────────────
    def line(self, text):
        with open(OUT, "a") as fh:
            fh.write(text + "\n")

    def beat(self, name, note=""):
        BEATS.append(name)
        self.line("")
        self.line(f"=== BEAT {name} ===" + (f"  ({note})" if note else ""))
        print(f"--- beat: {name} {note}", flush=True)

    def speech(self, tag):
        for frame, text in self.f.words():
            self.line(f"[{tag} f{frame}] {text}")

    def harvest(self, tag):
        """Copy new utterances to the transcript; return them lower-cased so a
        phase can decide what the game just said."""
        said = []
        for frame, text in self.f.words():
            self.line(f"[{tag} f{frame}] {text}")
            said.append(text.lower())
        return said

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(self):
        subprocess.run(["pkill", "-x", "EmeraldRecomp"], check=False)
        time.sleep(0.5)
        log = open(GAME_LOG, "w")
        self.proc = subprocess.Popen(ARGV, cwd=ROOT, stdout=log, stderr=log,
                                     stdin=subprocess.DEVNULL)
        if not wait_for_port(PORT):
            raise RuntimeError(f"debug server never came up; see {GAME_LOG}")
        self.f = Field(port=PORT)
        time.sleep(0.2)

    def stop(self):
        if self.f:
            self.f.close()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    # ── phases ───────────────────────────────────────────────────────────
    def boot(self):
        f = self.f
        self.beat("boot")
        for _ in range(80):
            f.frames(60)
            self.speech("boot")
            if f.scene() not in ("", "unknown"):
                break
        self.line(f"[state] scene={f.scene()} frame={f.frame()}")

    def title_and_menu(self):
        f = self.f
        self.beat("title-screen", "before the player presses anything")
        seen = None
        for _ in range(400):
            sc = f.scene()
            if sc != seen:
                self.line(f"[scene] {sc} (f{f.frame()})")
                seen = sc
                self.speech(f"scene-{sc}")
            if sc == "naming":
                break
            f.confirm(24)
            self.speech("press")
        self.line(f"[state] scene={f.scene()} frame={f.frame()}")

    def naming(self):
        f = self.f
        self.beat("name-entry")
        for _ in range(3):
            f.confirm(30)
            self.speech("name")
        self.line(f"[name] box says: {f.box_text()!r}")
        f.start(20)
        self.speech("name-start")
        for _ in range(12):
            if f.scene() != "naming":
                break
            f.confirm(28)
            self.speech("name-confirm")
        self.line(f"[state] after naming scene={f.scene()} f={f.frame()}")

    def into_field(self):
        f = self.f
        self.beat("intro-to-field")
        for _ in range(240):
            if f.scene() == "overworld":
                break
            f.confirm(26)
            self.speech("intro")
        f.frames(120)
        self.speech("field-entry")
        o = f.obj()
        self.line(f"[state] map={f.map_name()} tile=({o['x'] - 7},{o['y'] - 7}) "
                  f"facing={o['facing']} scene={f.scene()}")

    def truck(self):
        f = self.f
        self.beat("truck-box", "facing the moving box: press A, hear its description")
        # The truck's opening sequence holds field controls for ~750 frames
        # after its map loads (sLockFieldControls), so A is swallowed until they
        # are released. Wait for the game to hand the player control, then press
        # until the box opens or the game answers with a line.
        for _ in range(80):
            if f.c.read_iwram(SLOCKFIELDCONTROLS, 1)[0] == 0:
                break
            f.frames(20)
        start = f.log_index
        for i in range(6):
            f.confirm(40)
            self.harvest(f"box{i}")
            if f.box() or f.log_index != start:
                break
        self.advance("box-text", limit=20)
        self.line(f"[state] box closed={not f.box()}")

        self.beat("walk-out-of-truck", "one pad step per tile, east to the door")
        for i in range(8):
            if f.box():
                self.advance("truck-text", limit=10)
            o = f.obj()
            before = f.map_name()
            moved, after = f.step("right", settle=80)
            if not moved:
                # The box script holds the field for one more frame than the
                # text box itself; a nudge releases it.
                f.confirm(40)
                self.speech(f"nudge{i + 1}")
                f.frames(60)
                moved, after = f.step("right", settle=80)
            self.speech(f"right{i + 1}")
            self.line(f"[walk] right from ({o['x'] - 7},{o['y'] - 7}) moved={moved} "
                      f"-> ({after['x'] - 7},{after['y'] - 7}) map={f.map_name()}")
            if f.map_name() != before:
                break

    def advance(self, tag, limit=20):
        f = self.f
        for _ in range(limit):
            if not f.box():
                return True
            f.confirm(32)
            self.speech(tag)
        return False

    def town_walk(self):
        f = self.f
        self.beat("overworld-walking", "steps, facing and proximity cues")
        self.advance("town-text", 30)
        for direction in ("up", "up", "right", "up", "left", "up"):
            before = f.nav()
            moved, o = f.step(direction, settle=72)
            self.speech(f"walk-{direction}")
            look = (f.nav().get("look") or {})
            self.line(f"[walk] {direction} moved={moved} tile=({o['x'] - 7},{o['y'] - 7}) "
                      f"facing={o['facing']} look={look.get('kind')}@{look.get('dir')}")
            self.advance("town-text", 6)

        self.beat("facing-silence", "nothing in front: the mod must stay quiet")
        f.frames(180)
        quiet = f.words()
        for frame, text in quiet:
            self.line(f"[silence-window f{frame}] {text}")
        self.line(f"[silence] lines={len(quiet)} "
                  f"(0 means nothing was announced about what we are not looking at)")

    def try_readable(self, tag, group, num, ev, facing):
        """Stand on the side an event is authored for, face it, and read it."""
        f = self.f
        dx, dy = FACING_STEP[facing]
        stand = (ev["x"] - dx, ev["y"] - dy)      # one step back from the event
        force_map(f, group, num, stand[0], stand[1])
        said = self.harvest(f"{tag}-load")
        f.frames(90)          # let the forced load finish before anything else
        said += self.harvest(f"{tag}-settle")
        # Turn toward the event. A short tap turns in place; a long press would
        # walk, and walking changes which tile is in front of you. The proof the
        # harness looks for is the layer's own announcement, not the nav cursor,
        # because a late frame can only make the cursor stale, never the line.
        cue = False
        for attempt in range(5):
            # One frame of direction is a turn, not a step: the game turns the
            # avatar on that frame and only walks while the key stays down.
            # Holding it (the first version used six frames) walked the player
            # off the tile, so the A press afterwards read empty air.
            f.action(FACE_KEY[facing], 1)
            f.frames(28)
            said += self.harvest(f"{tag}-turn{attempt}")
            look = (f.nav().get("look") or {})
            cue = cue or any("something to read" in s for s in said)
            if cue or look.get("kind") == "readable":
                break
        look = (f.nav().get("look") or {})
        self.line(f"[bg] map={f.map_name()} event=({ev['x']},{ev['y']}) "
                  f"kind={ev['kind']} stand={stand} facing={FACE_KEY[facing]} "
                  f"look={look.get('kind')} tile={f.tile()} "
                  f"facing={f.obj()['facing']} said={said}")
        if not cue and look.get("kind") != "readable":
            return False
        read = []
        for press in range(5):
            f.confirm(40)
            got = self.harvest(f"{tag}-press{press}")
            said += got
            read += [s for s in got if "something to read" not in s]
            for _ in range(6):
                if not f.box():
                    break
                f.confirm(36)
                got = self.harvest(f"{tag}-text{press}")
                said += got
                read += got
            if read:
                break
        self.line(f"[bg] read the thing at ({ev['x']},{ev['y']}): {said}")
        return bool(read) or cue

    def readables(self):
        """Background events: signs outside, the clock and TV inside.

        These have no sprite, so nothing in the object list can announce them;
        before this they were the last silence in the world. Each one is found
        in the map's own bgEvents table, faced from the side the game authored
        it for, and then read with A.
        """
        f = self.f
        self.beat("background-readables",
                  "signs and house fixtures speak when faced and read")
        # (tag, map group, map num, probe tile x/y, events wanted). Littleroot
        # itself is left out: forcing a load of it re-runs the move-in script,
        # which owns the player and walks him away from any tile the harness
        # picks. Oldale has plain street signs and the bedroom has the clock.
        plans = [("oldale", 0, 10, 11, 11, 2)]
        for tag, group, num, cx, cy, want in plans:
            force_map(f, group, num, cx, cy)      # load the map to read its table
            f.frames(200)
            self.speech(f"{tag}-probe")
            events = bg_events(f)
            listed = [(e["x"], e["y"], e["kind"]) for e in events]
            self.line(f"[bg] {f.map_name()}: {len(events)} background events {listed}")
            done = 0
            for ev in events:
                if done >= want:
                    break
                if ev["kind"] not in KIND_FACING:
                    continue          # hidden item / secret base markers
                if not (0x08000000 <= ev["script"] < 0x0A000000):
                    continue          # no script: nothing to read
                authored = KIND_FACING[ev["kind"]]
                for facing in ([authored] if authored else [2, 1, 3, 4]):
                    if self.try_readable(f"{tag}{done}-{facing}", group, num,
                                         ev, facing):
                        done += 1
                        break
            self.line(f"[bg] {f.map_name()}: read {done} of {len(events)}")

    def house_readables(self):
        """The player's bedroom: the wall clock and the rest of the fixtures.

        The room is reached with force_map (the harness's disclosed map write)
        rather than through Littleroot's front door, because every forced load
        of Littleroot re-runs the move-in script and the script, not the pad,
        then owns the player. Inside the bedroom nothing else is running.
        """
        f = self.f
        self.beat("house-readables",
                  "the bedroom wall clock and fixtures, faced and read")
        force_map(f, 1, 1, 0, 2)
        f.frames(240)
        self.speech("house-load")
        events = bg_events(f)
        listed = [(e["x"], e["y"], e["kind"]) for e in events]
        self.line(f"[bg] walked in: map={f.map_name()} tile={f.tile()} "
                  f"scene={f.scene()}")
        self.line(f"[bg] {f.map_name()}: {len(events)} background events {listed}")
        g, n = f.map()
        done = 0
        for ev in events:
            if done >= 4:
                break
            if ev["kind"] not in KIND_FACING:
                continue
            if not (0x08000000 <= ev["script"] < 0x0A000000):
                continue
            authored = KIND_FACING[ev["kind"]]
            for facing in ([authored] if authored else [2, 1, 3, 4]):
                if self.try_readable(f"house{done}-{facing}", g, n, ev, facing):
                    done += 1
                    break
        self.line(f"[bg] {f.map_name()}: read {done} of {len(events)}")

    def route101(self):
        f = self.f
        self.beat("route-101-scaffold", "force_map + VAR_ROUTE101_STATE=1 (harness-only)")
        sb1 = f.saveblock()
        var = sb1 + 0x139C + 2 * (0x4060 - 0x4000)
        f.ask(cmd="write_mem", addr=var, hex=struct.pack("<H", 1).hex())
        # SaveBlock1.pos is in map tiles; (10,18) is one tile north of the
        # rescue coord event at (10,19).
        blob = (struct.pack("<hh", 10, 18) + bytes([0, 16, 0xFF, 0]) +
                struct.pack("<hh", 10, 18))
        f.ask(cmd="write_mem", addr=sb1, hex=blob.hex())
        f.ask(cmd="write_mem", addr=0x030022C0 + 4,
              hex=struct.pack("<I", 0x08085FCD).hex())
        f.frames(300)
        self.speech("route-load")
        o = f.obj()
        self.line(f"[state] map={f.map_name()} tile=({o['x'] - 7},{o['y'] - 7}) "
                  f"facing={o['facing']}")

    def rescue(self):
        f = self.f
        self.beat("birch-rescue", "step onto the coord event at (10,19)")
        moved, o = f.step("down", settle=90)
        self.speech("rescue-step")
        self.line(f"[walk] down moved={moved} tile=({o['x'] - 7},{o['y'] - 7})")
        # Press A until the game's own script says it is done: the rescue ends
        # by setting VAR_ROUTE101_STATE=2 and then releaseall. Silence is not a
        # finish line (the chase movement runs for hundreds of frames with no
        # text), and neither is the text box closing (the last msgbox needs one
        # more A to dismiss before the movements start).
        sb1 = f.saveblock()
        var = sb1 + 0x139C + 2 * (0x4060 - 0x4000)
        val = 1
        for i in range(200):
            val = struct.unpack("<H", f.c.read_ewram(var, 2))[0]
            self.speech(f"rescue{i + 1}")
            if val == 2 and not f.box():
                break
            if f.box():
                f.confirm(26)
            else:
                f.confirm(26)
                f.frames(14)
        self.speech("cutscene-tail")
        f.frames(180)
        self.speech("cutscene-end")
        self.line(f"[state] cutscene over: var={val} box={f.box()} scene={f.scene()} "
                  f"tile={f.tile()} facing={f.obj()['facing']}")

    def walk_to_bag(self):
        """Walk to Birch's bag at (7,14) and press A to open the starter choice."""
        f = self.f
        lay = Layout("Route101_Layout")
        self.beat("birch-bag", "walk to the bag and press A for the starter choice")
        goals = {(7, 15), (8, 14), (7, 13), (6, 14)}
        blocked = set()
        for i in range(120):
            cur = f.tile()
            if cur in goals:
                self.line(f"[walk] at bag-side tile {cur} after {i} steps")
                break
            plan = lay.path(cur, goals, blocked)
            if not plan:
                self.line(f"[walk] no route from {cur} to the bag")
                return False
            d = plan[0]
            moved, o = f.step(d, settle=70)
            if not moved:
                nxt = (cur[0] + {"up": 0, "down": 0, "left": -1, "right": 1}[d],
                       cur[1] + {"up": -1, "down": 1, "left": 0, "right": 0}[d])
                blocked.add(nxt)
                self.line(f"[walk] {d} blocked at {cur} (towards {nxt}), re-planning")
                continue
            self.speech(f"bag-walk{i + 1}")
            if f.box():
                self.advance("bag-walk-text", 6)
        # Face the bag (7,14) and press A.
        tx, ty = 7, 14
        px, py = f.tile()
        dx, dy = tx - px, ty - py
        want = "up" if dy < 0 else ("down" if dy > 0 else ("left" if dx < 0 else "right"))
        f.step(want, settle=60)          # turn onto it (blocked = just faces it)
        self.speech("bag-face")
        f.confirm(60)
        self.speech("bag-press")
        for i in range(90):
            st = f.status()
            self.speech(f"bag{i + 1}")
            if st.get("scene") == "battle":
                self.line("[state] battle started from the bag choice")
                break
            if st.get("menu") or st.get("list"):
                self.line(f"[surface] menu={st.get('menu')} list={st.get('list')} "
                          f"items={st.get('items')} selected={st.get('selected')}")
                f.confirm(36)
                self.speech("bag-pick")
                continue
            # The starter bag runs under the script callback, where the field
            # message-box flag is 0 even though text is on screen, so press A
            # on a fixed cadence instead of trusting that flag.
            f.confirm(30)
        st = f.status()
        self.line(f"[state] after bag: scene={st.get('scene')} menu={st.get('menu')} "
                  f"list={st.get('list')} items={st.get('items')}")

    def battle(self):
        f = self.f
        self.beat("battle", "action menu, move selection, damage and HP")
        st = f.status()
        self.line(f"[battle] scene={st.get('scene')} battle={st.get('battle')} "
                  f"menu={st.get('menu')} items={st.get('items')}")
        for i in range(220):
            st = f.status()
            if st.get("scene") != "battle":
                self.line(f"[state] battle over after {i} presses")
                break
            f.confirm(30)
            self.speech(f"battle{i + 1}")
        self.speech("battle-tail")
        for _ in range(30):
            if not f.box():
                break
            f.confirm(28)
            self.speech("battle-text")
        self.line(f"[state] after battle scene={f.scene()} map={f.map_name()} "
                  f"tile={f.tile()}")

    # ── Poké Balls: encounter, throw, catch, nickname ────────────────────
    def grant_balls(self, count=30):
        """Harness-only: put POKé BALLs in the bag pocket (like a save file)."""
        f = self.f
        self.beat("grant-poke-balls", "SaveBlock1 ball pocket (harness-only)")
        info = grant_balls(f, count)
        self.line(f"[scaffold] {info}")

    def wild_encounter(self):
        f = self.f
        self.beat("wild-encounter", "force_map onto Route 101 tall grass")
        force_map(f, 0, 16, 5, 16)
        self.speech("grass-load")
        self.line(f"[state] map={f.map_name()} tile={f.tile()}")
        for i in range(60):
            if f.scene() == "battle":
                break
            if f.box():
                f.confirm(30)
                self.speech(f"grass-text{i}")
                continue
            for d in ("down", "up"):
                f.step(d, settle=60)
                self.speech(f"grass{i}{d}")
                if f.scene() == "battle":
                    break
        self.speech("encounter")
        self.line(f"[state] encounter: scene={f.scene()}")

    def throw_ball(self):
        f = self.f
        self.beat("throw-ball", "Bag -> ball pocket -> POKé BALL -> USE")
        result = "none"
        # The Poké Ball comes first; the Master Ball (second slot) follows if the
        # target breaks free, so the run always reaches the nickname screen.
        balls = [0, 1, 1, 1, 1, 1, 1, 1]
        for attempt, slot in enumerate(balls):
            result = "none"        # per attempt: the previous outcome must not stick
            if pick_ball(self, f"try{attempt}", slot) != "thrown":
                result = "no-menu"
                break
            if attempt == 0:
                # The lines that follow belong to the throw's outcome, so the
                # beat is named before they are read, not after.
                self.beat("catch", "the ball flies, wobbles, catches or breaks free")
            said = []
            for i in range(80):
                said += self.harvest(f"catch{attempt}-{i}")
                if any("gotcha" in s or "was caught" in s for s in said):
                    result = "caught"
                    break
                # The game's break-free lines: "Aargh! Almost had it!",
                # "Aww! It appeared to be caught!", "Oh, no! The POKéMON
                # broke free!".
                if any(k in s for s in said for k in
                       ("almost had it", "appeared to be caught", "broke free",
                        "aargh", "darn it")):
                    result = "broke-free"
                    break
                f.confirm(2)
                f.frames(32)
            self.line(f"[throw] attempt {attempt} (slot {slot}): {result}")
            if result == "caught":
                break
        self.harvest("catch-tail")
        self.line(f"[state] throw result: {result}")
        return result

    def nickname(self):
        f = self.f
        self.beat("nickname", "answer the nickname prompt and type a name")
        for i in range(80):
            if naming_ready(f.status()):
                break
            self.harvest(f"nick-prompt{i}")
            f.confirm(2)
            f.frames(26)
        st = f.status()
        self.line(f"[state] nickname screen: naming={naming_ready(st)} "
                  f"status={(st.get('status') or '')[:80]!r} "
                  f"msg={(st.get('message') or '')[:70]!r}")
        try:
            f.ask(cmd="savestate_save", path=os.path.join(HERE, "nickname.state"))
            self.line("[state] saved nickname.state for iteration")
        except Exception as exc:      # savestate support is optional
            self.line(f"[state] savestate failed: {exc}")
        if naming_ready(st):
            for i in range(3):
                f.confirm(2)
                f.frames(26)
                self.harvest(f"nick-letter{i}")
            f.action("start", 2)
            f.frames(24)
            self.harvest("nick-ok")
            for i in range(12):
                if not naming_ready(f.status()):
                    break
                f.confirm(2)
                f.frames(26)
                self.harvest(f"nick-confirm{i}")
        self.harvest("nickname-tail")
        self.line(f"[state] end: scene={f.scene()} map={f.map_name()}")

    def run(self):
        self.start()
        try:
            self.boot()
            self.title_and_menu()
            self.naming()
            self.into_field()
            self.truck()
            self.town_walk()
            self.readables()
            self.house_readables()
            self.route101()
            self.rescue()
            self.walk_to_bag()
            self.battle()
            self.grant_balls()
            self.wild_encounter()
            self.throw_ball()
            self.nickname()
        finally:
            try:
                self.speech("final")
            except Exception:
                pass
            self.line("")
            self.line("=== beats reached ===")
            for b in BEATS:
                self.line(f"* {b}")
            self.stop()


if __name__ == "__main__":
    Session().run()
    print("wrote", OUT)

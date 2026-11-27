"""Reproduce the trainer-battle hang and dump exactly where the battle stopped.

The hang parks `gBattleMainFunc` in `RunBattleScriptCommands_PopCallbacksStack`.
That function either pops the battle callback stack (when the current action is
finishing) or executes `gBattleScriptingCommandsTable[gBattlescriptCurrInstr[0]]`
(when `gBattleControllerExecFlags` is clear). So the interesting state is the
command byte it keeps re-reading, the exec flags, and the callback stack.

    python3 artifacts/playtest/diag_hang.py

The emulator must already be running with a checkpoint that has a party.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from checkpoints import Checkpoints  # noqa: E402
from tcp import Conn  # noqa: E402
import gym_walk as G  # noqa: E402

G_ACTION_FUNC_ID = 0x02024083
G_EXEC_FLAGS = 0x02024068
G_CURR_INSTR = 0x02024214
G_BATTLE_RESOURCES = 0x020244A8
G_BATTLE_MAIN_FUNC = 0x03005D04
G_BATTLE_SCRIPTING = 0x02024474
G_BATTLE_OUTCOME = 0x0202433A
COMMAND_TABLE = 0x0831BD10
BATTLE_MAIN_CB2 = 0x08038420


def symbols():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                        "variants/emerald/symbols/imported_symbols.tsv")
    table = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3 and parts[0].startswith("0x"):
                table[int(parts[0], 16)] = parts[2]
    return table


def name_of(syms, ptr):
    return syms.get(ptr & ~1, syms.get(ptr, f"0x{ptr:08X}"))


def u32(c, addr):
    return struct.unpack("<I", c.read_ewram(addr, 4))[0]


def main():
    c = Conn()
    syms = symbols()
    ck = Checkpoints(conn=c)
    ck.load("party-lab")
    c.ask(cmd="run_frames", n=60)

    def state():
        return c.ask(cmd="emerald_dev_state")

    for _ in range(20):
        d = state()
        if not d.get("message_box") and not d.get("controls_locked"):
            break
        c.ask(cmd="emerald_a11y_action", action="confirm")
        c.ask(cmd="run_frames", n=45)

    c.ask(cmd="emerald_dev_warp", map_group=10, map_num=0, x=4, y=19, facing="north")
    for _ in range(90):
        if (state().get("warp") or {}).get("done"):
            break
        c.ask(cmd="run_frames", n=5)

    def pos():
        return tuple(state().get("pos") or ())

    grid = G.Grid("MauvilleCity_Gym_Layout")
    for goal in [(4, 17), (2, 17), (2, 16)]:
        for step in grid.path(pos(), goal, set()) or []:
            c.ask(cmd="emerald_a11y_action", action=step)
            c.ask(cmd="run_frames", n=60)
    c.ask(cmd="emerald_a11y_action", action="left")
    c.ask(cmd="run_frames", n=60)
    c.ask(cmd="emerald_a11y_action", action="confirm")
    c.ask(cmd="run_frames", n=90)

    last = None
    stalled = 0
    for _ in range(140):
        st = c.ask(cmd="emerald_a11y_status")
        key = (st.get("prints"), st.get("scene"))
        stalled = stalled + 1 if key == last else 0
        last = key
        if stalled >= 25:
            break
        c.ask(cmd="emerald_a11y_action", action="confirm")
        c.ask(cmd="run_frames", n=45)

    print("scene", c.ask(cmd="emerald_a11y_status").get("scene"),
          "callback2", hex(state().get("callback2") or 0),
          "expected BattleMainCB2", hex(BATTLE_MAIN_CB2))
    print("gCurrentActionFuncId", c.read_ewram(G_ACTION_FUNC_ID, 1)[0])
    print("gBattleControllerExecFlags", hex(u32(c, G_EXEC_FLAGS)))
    print("gBattleOutcome", c.read_ewram(G_BATTLE_OUTCOME, 1)[0])
    main_func = struct.unpack("<I", c.read_iwram(G_BATTLE_MAIN_FUNC, 4))[0]
    print("gBattleMainFunc", hex(main_func), "=", name_of(syms, main_func))

    instr = u32(c, G_CURR_INSTR)
    cmd = c.read_rom(instr, 1)[0] if instr >= 0x08000000 else None
    print("gBattlescriptCurrInstr", hex(instr), "cmd byte", cmd,
          "bytes", c.read_rom(instr, 8).hex() if instr >= 0x08000000 else "-")
    if cmd is not None:
        entry = struct.unpack("<I", c.read_rom(COMMAND_TABLE + 4 * cmd, 4))[0]
        print("  command ->", hex(entry), name_of(syms, entry))

    resources = u32(c, G_BATTLE_RESOURCES)
    print("gBattleResources", hex(resources))
    if resources:
        stack_ptr = u32(c, resources + 0x0C)
        print("battleCallbackStack", hex(stack_ptr))
        if stack_ptr:
            funcs = struct.unpack("<8I", c.read_ewram(stack_ptr, 32))
            size = c.read_ewram(stack_ptr + 0x20, 1)[0]
            print("  size", size)
            for i, f in enumerate(funcs):
                if f:
                    print(f"  [{i}]", hex(f), name_of(syms, f))


if __name__ == "__main__":
    main()

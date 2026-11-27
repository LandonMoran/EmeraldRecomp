"""Connection and memory reads for the older harnesses.

``bot.conn()`` and ``bot.rd()`` used to live in /tmp and were lost on a
checkpoint restore; pad.py and the run_*.py scripts import them, so they are
tracked here. New code can use tcp.Conn instead.
"""

import socket

from p import ask

PORT = 19892


def conn(port=PORT, timeout=30.0):
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.settimeout(timeout)
    return s


def rd(sock, cmd, addr, n):
    """Read ``n`` bytes with read_ewram/read_iwram/read_rom/read_mem."""
    reply = ask(sock, {"cmd": cmd, "addr": addr, "len": n})
    if reply.get("error"):
        raise RuntimeError(f"{cmd} at 0x{addr:08X}: {reply['error']}")
    data = reply.get("data")
    if data is None:
        data = reply.get("hex", "")
    if isinstance(data, list):
        return bytes(data)
    return bytes.fromhex(data)

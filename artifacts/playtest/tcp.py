"""Minimal TCP debug client for EmeraldRecomp playtests.

The old harness imported ``bot``/``p`` from /tmp, which does not survive a
checkpoint restore. This module replaces both with a single dependency-free
client speaking the protocol in gbarecomp/TCP.md (one JSON request per line,
one JSON response per line).
"""

import json
import socket


class Conn:
    def __init__(self, host="127.0.0.1", port=19892, timeout=30.0):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.buf = b""
        self.s.settimeout(timeout)

    def ask(self, **kw):
        self.s.sendall((json.dumps(kw) + "\n").encode())
        while b"\n" not in self.buf:
            chunk = self.s.recv(1 << 20)
            if not chunk:
                raise RuntimeError("debug server closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line.decode())

    def cmd(self, name, **kw):
        r = self.ask(cmd=name, **kw)
        if isinstance(r, dict) and r.get("ok") is False:
            raise RuntimeError(f"{name}: {r.get('error')}")
        return r

    # ── memory helpers ──────────────────────────────────────────────────
    def read(self, region, addr, n):
        r = self.ask(cmd=f"read_{region}", addr=addr, len=n)
        data = r.get("data") or r.get("hex") or ""
        if isinstance(data, list):
            return bytes(data)
        return bytes.fromhex(data)

    def read_ewram(self, addr, n):
        return self.read("ewram", addr, n)

    def read_iwram(self, addr, n):
        return self.read("iwram", addr, n)

    def write(self, addr, blob):
        return self.cmd("write_mem", addr=addr, hex=blob.hex())

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass

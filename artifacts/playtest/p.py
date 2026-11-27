"""One-JSON-per-line request/response over a raw socket.

The older harnesses (pad.py and everything built on it) imported this from
/tmp, which does not survive a checkpoint restore. It lives here now, next to
the scripts that use it, and speaks the protocol in gbarecomp/TCP.md.

``ask(sock, {...})`` returns the parsed reply dict; a per-socket read buffer
keeps a reply that arrived early from being dropped.
"""

import json

_buffers = {}


def ask(sock, request):
    sock.sendall((json.dumps(request) + "\n").encode())
    key = sock.fileno()
    buf = _buffers.get(key, b"")
    while b"\n" not in buf:
        chunk = sock.recv(1 << 20)
        if not chunk:
            raise RuntimeError("debug server closed the connection")
        buf += chunk
    line, rest = buf.split(b"\n", 1)
    _buffers[key] = rest
    return json.loads(line.decode())

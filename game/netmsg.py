"""Newline-delimited JSON message framing over a TCP socket, shared by
server.py and coop_client.py. Deliberately simple (plaintext JSON, no
auth, no encryption) - this is a LAN/trusted-friend co-op protocol, not a
hardened multiplayer backend."""
import json


def send_msg(sock, obj):
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))


class MessageReader:
    """Buffers partial TCP reads and yields complete JSON messages."""

    def __init__(self, sock):
        self.sock = sock
        self.buf = b""

    def read_available(self):
        """Blocking recv of whatever's ready, split into whole JSON messages.
        Raises ConnectionError if the peer closed the socket."""
        chunk = self.sock.recv(65536)
        if chunk == b"":
            raise ConnectionError("peer closed the connection")
        self.buf += chunk
        out = []
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            if line:
                out.append(json.loads(line.decode("utf-8")))
        return out

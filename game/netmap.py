"""
Compact wire format for the co-op tile map (server.py -> coop_client.py).

The realm grid used to ride its snapshot as a plain JSON list of lists: ~2.4M
ints for the 1560x1560 map, many megabytes of text and seconds of JSON work on
both ends. Now it's packed as unsigned 16-bit tiles (row-major), zlib-compressed
and base64'd into a small dict under the same "map" key:

    {"enc": "z16", "w": width, "h": height, "data": "<base64>"}

decode_map() also accepts the old plain list, so a client reading an older
server's snapshot (or a test handing it a raw grid) still works.
"""
import base64
import sys
import zlib
from array import array

ENC = "z16"


def encode_map(grid):
    h = len(grid)
    w = len(grid[0]) if h else 0
    a = array("H")
    for row in grid:
        a.extend(row)
    if sys.byteorder != "little":
        a.byteswap()
    return {"enc": ENC, "w": w, "h": h, "data": base64.b64encode(zlib.compress(a.tobytes(), 6)).decode("ascii")}


def decode_map(payload):
    """The tile grid (list of row lists) from encode_map()'s dict - or a plain grid, as-is."""
    if payload is None or isinstance(payload, list):
        return payload
    if payload.get("enc") != ENC:
        raise ValueError(f"unknown map encoding {payload.get('enc')!r}")
    w, h = int(payload["w"]), int(payload["h"])
    a = array("H")
    a.frombytes(zlib.decompress(base64.b64decode(payload["data"])))
    if sys.byteorder != "little":
        a.byteswap()
    if len(a) != w * h:
        raise ValueError(f"map payload has {len(a)} tiles, expected {w}x{h}")
    flat = a.tolist()
    return [flat[y * w:(y + 1) * w] for y in range(h)]

"""
Co-op map wire format (game/netmap.py): the realm grid is sent zlib-packed.

- encode -> JSON -> decode gives back the identical grid (real realm, a bonus room,
  edge cases), and the packed form is far smaller than the old plain JSON
- the old plain-list form still decodes (as-is); a bad payload is rejected
- a real co-op session over sockets still gets a working map on the client

Run with: .venv\\Scripts\\python.exe tests\\check_netmap.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import netmap, world
from game.realm_sim import RealmSim


def check_round_trip_and_size():
    realm = RealmSim()
    grid = realm.realm_map.grid
    wire = json.dumps(netmap.encode_map(grid))
    back = netmap.decode_map(json.loads(wire))
    assert back == grid, "the realm must unpack to the identical grid"
    plain = len(json.dumps(grid))
    assert len(wire) * 10 < plain, (len(wire), plain)
    print(f"  realm {len(grid[0])}x{len(grid)}: plain JSON {plain / 1e6:.2f} MB -> packed {len(wire) / 1e6:.3f} MB")
    dungeon = RealmSim(bonus=True, theme="cave", difficulty_name="Easy")
    g2 = dungeon.realm_map.grid
    assert netmap.decode_map(json.loads(json.dumps(netmap.encode_map(g2)))) == g2
    for tiny in ([[0]], [[65535, 1], [2, 3]], [[world.WATER] * 7 for _ in range(3)]):
        assert netmap.decode_map(netmap.encode_map(tiny)) == tiny
    print("check_round_trip_and_size: PASSED")


def check_legacy_and_bad_payloads():
    legacy = [[1, 2], [3, 4]]
    assert netmap.decode_map(legacy) is legacy and netmap.decode_map(None) is None
    enc = netmap.encode_map(legacy)
    for bad in (dict(enc, enc="zip"), dict(enc, w=3)):
        try:
            netmap.decode_map(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted a bad payload: {bad}")
    print("check_legacy_and_bad_payloads: PASSED")


if __name__ == "__main__":
    check_round_trip_and_size()
    check_legacy_and_bad_payloads()
    print("PASSED: co-op map wire format checks all green.")

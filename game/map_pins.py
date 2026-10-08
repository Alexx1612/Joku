"""
Your own map pins (doc 42): click the full map (M), the Quest Map or the Dictionary's little map
to drop a pin there; click a pin again to remove it. Up to MAX_PINS, the oldest goes when you add
one more. Pins live in the open Realm, are saved with the character (Player.map_pins, world px)
and show everywhere quest markers do - a pin on the world with an edge arrow and the distance, on
the corner minimap and the full map, and in the tracker list - in their own green.
Co-op: pins are yours alone; the client tells the server ("map_pins") so they're saved with you.
"""
import math

MAX_PINS = 5
PIN_COLOR = (110, 255, 160)
HIT_TILES = 6  # a click this close (in tiles) to a pin removes it instead of adding one


def toggle(pins, wx, wy, tile=32):
    """Adds a pin at (wx, wy) world px - or removes the pin under it. Returns "added" / "removed"."""
    for i, (x, y, _label) in enumerate(pins):
        if math.hypot(x - wx, y - wy) <= HIT_TILES * tile:
            pins.pop(i)
            return "removed"
    used = {p[2] for p in pins}
    n = next(k for k in range(1, MAX_PINS + 2) if f"Pin {k}" not in used)
    pins.append([float(wx), float(wy), f"Pin {n}"])
    del pins[:-MAX_PINS]
    return "added"


def clean(pins):
    """Pins from a save / the network, made safe."""
    out = []
    for p in pins or []:
        try:
            out.append([float(p[0]), float(p[1]), str(p[2])[:16]])
        except (TypeError, ValueError, IndexError):
            continue
    return out[-MAX_PINS:]


def marks(pins, player_pos, in_realm, tile=32):
    """Quest-marker dicts (game/quest_markers.py format) for the pins - only in the Realm."""
    if not in_realm:
        return []
    px, py = player_pos
    return [{"qid": f"pin:{label}", "title": label, "color": PIN_COLOR, "pos": (x, y), "note": "", "label": label,
             "dist_tiles": int(math.hypot(x - px, y - py) / tile)} for x, y, label in pins]

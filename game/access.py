"""
Readability & accessibility (Options > Accessibility), read at draw time so a change shows at once.

  Colour-blind palette  - attack telegraphs and enemy bullets are red (aim lanes) vs orange (ground
                          zones) by default. For deuteranopia / protanopia (red-green) reds become
                          magenta, oranges a clear yellow and greens blue; for tritanopia (blue-
                          yellow) blues become teal-green and yellows pink. Hue is remapped, the
                          brightness kept, so "hot" vs "cool" still reads.
  Bullet outline        - a dark ring + a pale rim round every enemy bullet (busy backgrounds).
  Telegraph strength    - how opaque the ground warnings are (x0.5 .. x1.5).
  Text size             - Normal / Large (the HUD's small and medium fonts, +2 px).
  Reduce flashing       - softer lightning (no flicker), a calmer Blood Moon heartbeat, and the
                          last-moment telegraph flash stays steady instead of blinking.
"""
import colorsys

from game import settings

CB_MODES = (("off", "Off"), ("deuteranopia", "Deuteranopia (red-green)"),
            ("protanopia", "Protanopia (red-green)"), ("tritanopia", "Tritanopia (blue-yellow)"))
TEXT_SIZES = (("normal", "Normal"), ("large", "Large"))
_CACHE = {}

# hue bands (degrees) -> new hue, per mode
_REMAP = {
    "deuteranopia": ((330, 360, 300), (0, 25, 300), (25, 70, 55), (70, 170, 210)),
    "protanopia": ((330, 360, 295), (0, 25, 295), (25, 70, 52), (70, 170, 215)),
    "tritanopia": ((170, 260, 160), (40, 70, 330)),
}


def mode():
    return settings.get("colorblind")


def color(c):
    """A telegraph / enemy-bullet colour through the colour-blind palette (unchanged when off)."""
    m = mode()
    if m == "off" or m not in _REMAP:
        return tuple(c[:3])
    key = (m, tuple(c[:3]))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    r, g, b = (v / 255 for v in c[:3])
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    deg = h * 360
    out = tuple(c[:3])
    if s > 0.18:  # greys / whites stay as they are
        for lo, hi, new in _REMAP[m]:
            if lo <= deg < hi:
                nr, ng, nb = colorsys.hls_to_rgb(new / 360, min(0.75, max(0.45, l)), min(1.0, s * 1.1))
                out = (int(nr * 255), int(ng * 255), int(nb * 255))
                break
    if len(_CACHE) > 512:
        _CACHE.clear()
    _CACHE[key] = out
    return out


def tele_alpha(a):
    """A telegraph alpha scaled by Telegraph strength (0..1 -> x0.5..x1.5), clamped to 255."""
    return max(0, min(255, int(a * (0.5 + settings.get("tele_strength")))))


def outline():
    return bool(settings.get("bullet_outline"))


def reduced_flashing():
    return bool(settings.get("reduce_flashing"))


def apply_text_size():
    """Rebuilds the HUD's small / medium fonts for the chosen text size."""
    import pygame
    from game import ui
    large = settings.get("text_size") == "large"
    ui._FONT_S = pygame.font.SysFont("consolas", 16 if large else 14)
    ui._FONT_M = pygame.font.SysFont("consolas", 20 if large else 18, bold=True)

"""
World zoom (Options > Display > Zoom, default 125%): the WORLD - tiles, you, the monsters,
bullets, effects, the night lighting - is drawn bigger; the HUD, the dock and every window stay at
their normal size, so nothing gets cut off or squeezed.

How: each frame the client draws the world on a small canvas (screen / zoom) with the camera at
zoom 1 (world_begin), scales that up onto the real screen (world_end), then draws the HUD on top
at full resolution. Outside that world pass the camera has camera.zoom = zoom, so anything that
maps world -> screen (a bag window over its bag, the mouse aim, labels) lands exactly where the
scaled-up world shows it. Headless runs (SDL_VIDEODRIVER=dummy: the test suite, the screenshot
tools) stay at 100% unless RR_ZOOM says otherwise, so their fixed layouts keep holding.
"""
import os

import pygame

from game import constants as C

ZOOM_CHOICES = (1.0, 1.1, 1.25, 1.5)
_SMALL = {}
_saved = []


def zoom():
    env = os.environ.get("RR_ZOOM")
    if env:
        try:
            return max(1.0, min(2.0, float(env)))
        except ValueError:
            return 1.0
    if os.environ.get("SDL_VIDEODRIVER") == "dummy":
        return 1.0
    from game import settings
    z = settings.get("zoom")
    return z if z in ZOOM_CHOICES else 1.25


def sync_camera(cam):
    """Outside the world pass: the camera speaks real screen pixels at the current zoom."""
    cam.zoom = zoom()


def world_begin(screen, cam):
    """Start the world pass: returns the surface to draw the world on (the small canvas when
    zoomed, else the screen itself). Must be paired with world_end."""
    z = zoom()
    if z == 1.0:
        cam.zoom = 1.0
        _saved.append(None)
        return screen
    w, h = screen.get_size()
    sw, sh = max(160, int(round(w / z))), max(120, int(round(h / z)))
    small = _SMALL.get((sw, sh))
    if small is None:
        _SMALL.clear()
        small = _SMALL[(sw, sh)] = pygame.Surface((sw, sh))
    _saved.append((C.SCREEN_W, C.SCREEN_H, cam.screen_w, cam.screen_h))
    C.SCREEN_W, C.SCREEN_H = sw, sh
    cam.screen_w, cam.screen_h, cam.zoom = sw, sh, 1.0
    small.fill(C.COL_BG)
    return small


def world_end(world_surf, screen, cam):
    """End the world pass: scale the world up onto the screen, restore the screen size and put the
    camera back into screen pixels (zoom). Returns the screen."""
    saved = _saved.pop() if _saved else None
    if saved is None:
        sync_camera(cam)
        return screen
    C.SCREEN_W, C.SCREEN_H, cam.screen_w, cam.screen_h = saved
    pygame.transform.smoothscale(world_surf, screen.get_size(), screen)
    sync_camera(cam)
    return screen

"""
Regression: TileMap.draw's big-prop overhang scan indexed past the end of a row
on maps narrower than the view (the vault room crashed with IndexError on entry).
Draws every hub map with the camera parked at each edge/corner and beyond.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((1366, 820))

from game import constants as C, world


def check_hub_maps_draw_at_every_edge():
    maps = {"vault_room": world.make_vault_room(), "bazaar": world.make_bazaar(), "nexus": world.make_nexus()}
    for name, grid in maps.items():
        tmap = world.TileMap(grid)
        w, h = tmap.w * C.TILE, tmap.h * C.TILE
        # far = a whole screen past the edge: the vault room drawn while the camera
        # still sits on (big) Nexus coordinates - the case that crashed
        far_x, far_y = C.SCREEN_W + w, C.SCREEN_H + h
        for cx in (-far_x, -400, 0, w // 2, w, w + 400, far_x):
            for cy in (-far_y, -400, 0, h // 2, h, h + 400, far_y):
              for angle in (0, 45, 90, 135, 180, 225, 270, 315):   # Q/E camera rotation
                cam = world.Camera(C.SCREEN_W, C.SCREEN_H)
                cam.follow(pygame.Vector2(cx, cy))
                cam.rotate(angle)
                for overlay in (False, True):
                    tmap.canopy_overlay = overlay
                    # the real client path: floor through the rotate-a-buffer pipeline
                    world.render_rotated_world(screen, cam, lambda surf, c: tmap.draw(surf, c, surf.get_size()))
                    if overlay:
                        tmap.draw_canopies(screen, cam, (cx, cy))
    print("check_hub_maps_draw_at_every_edge: PASSED")


if __name__ == "__main__":
    check_hub_maps_draw_at_every_edge()
    print("PASSED: small map draw checks all green.")

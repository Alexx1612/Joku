"""
The Vault room's 12 permanent chests (Batch 15): each CHEST tile in the vault room
is one real 8-slot chest (index = row-major order, same numbering the save file's
flat slot list uses - chest i owns slots [i*8, i*8+8)). Walking up to a chest and
pressing F/Enter opens THAT chest as a small bag-style window next to it; there is
no full-screen paged vault menu any more. Shared by main.py, server.py and
coop_client.py so all three agree on which chest is which.
"""
import math

import pygame

from game import constants as C
from game import world

OPEN_RANGE_TILES = 1.7  # how close (in tiles, centre to centre) you must stand to open a chest


def chest_tiles(tmap):
    """[(tx, ty), ...] of every CHEST tile, in row-major (= chest index) order."""
    grid = tmap.grid
    return [(x, y) for y in range(len(grid)) for x in range(len(grid[0])) if grid[y][x] == world.CHEST]


def chest_world_pos(tmap, idx):
    tiles = chest_tiles(tmap)
    if not 0 <= idx < len(tiles):
        return None
    tx, ty = tiles[idx]
    return pygame.Vector2((tx + 0.5) * C.TILE, (ty + 0.5) * C.TILE)


def nearest_chest(tmap, pos, max_tiles=OPEN_RANGE_TILES):
    """(chest_index, world_pos) of the closest chest within reach of `pos`, or None."""
    best, best_d = None, max_tiles * C.TILE
    for i, (tx, ty) in enumerate(chest_tiles(tmap)):
        c = pygame.Vector2((tx + 0.5) * C.TILE, (ty + 0.5) * C.TILE)
        d = math.hypot(c.x - pos[0], c.y - pos[1])
        if d <= best_d:
            best, best_d = (i, c), d
    return best

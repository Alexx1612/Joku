"""RotMG-style exploration fog + minimap/full-map rendering.

The realm is a big island you're meant to discover on foot, so the map
isn't shown all at once: a corner minimap and a zoomable full-map (M key)
only reveal tiles you've actually walked near, exactly like RotMG's own
map screen builds up as you explore.
"""
import time

import pygame

from game import constants as C
from game import world

REVEAL_RADIUS_TILES = 10
REBUILD_INTERVAL = 0.4  # seconds between fog-of-war re-renders (cheap enough, avoids per-frame full-grid scans)

CORNER_SIZE = 148
MIN_ZOOM, MAX_ZOOM, ZOOM_STEP = 0.5, 8.0, 0.25
DEFAULT_ZOOM = 1.2

# the corner minimap can ALSO zoom in/out (via the +/- buttons next to it, or the
# +/- keys, without needing the full map open) - 1.0 = whole map fit to the corner
# box, higher = cropped in and centered on the player, like a closer-range radar
CORNER_MIN_ZOOM, CORNER_MAX_ZOOM, CORNER_ZOOM_STEP = 1.0, 8.0, 0.5
ZOOM_BTN_SIZE = 20

TILE_MM_COLORS = {
    world.GRASS: (52, 104, 52), world.GRASS2: (58, 112, 58), world.DIRT: (104, 82, 58),
    world.ROCK: (98, 98, 104), world.WATER: (32, 64, 108), world.NEXUS_FLOOR: (94, 82, 126),
    world.PORTAL: (210, 100, 230), world.BAZAAR_FLOOR: (112, 92, 60), world.STALL: (156, 124, 72),
    world.VAULT_TILE: (176, 156, 62), world.BAZAAR_PORTAL: (96, 206, 226), world.SAND: (206, 186, 124),
    world.SWAMP: (66, 84, 52), world.SNOW: (224, 232, 238),
}


class MinimapState:
    """One per active realm/bonus-room instance - tracks which tiles this
    player has explored and caches the rendered fog-of-war surface."""

    def __init__(self):
        self.explored = set()
        self.zoom = DEFAULT_ZOOM
        self.corner_zoom = CORNER_MIN_ZOOM
        self.full_map_open = False
        self._base = None
        self._last_build = -999.0
        self._last_count = -1

    def reveal_all(self, tilemap):
        """For small, static, always-safe maps (Nexus/Bazaar) where there's no
        exploration gameplay to gate - just show the whole thing from the start."""
        self.explored = {(x, y) for y in range(tilemap.h) for x in range(tilemap.w)}

    def reveal(self, player_pos, radius=REVEAL_RADIUS_TILES):
        tx, ty = int(player_pos.x // C.TILE), int(player_pos.y // C.TILE)
        r2 = radius * radius
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= r2:
                    self.explored.add((tx + dx, ty + dy))

    def adjust_zoom(self, delta):
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom + delta))

    def adjust_corner_zoom(self, delta):
        self.corner_zoom = max(CORNER_MIN_ZOOM, min(CORNER_MAX_ZOOM, self.corner_zoom + delta))

    def _base_surface(self, tilemap):
        if self._base is None:
            self._rebuild(tilemap)
            return self._base
        now = time.perf_counter()
        if now - self._last_build > REBUILD_INTERVAL and len(self.explored) != self._last_count:
            self._rebuild(tilemap)
            self._last_build = now
        return self._base

    def _rebuild(self, tilemap):
        w, h = tilemap.w, tilemap.h
        base = pygame.Surface((w, h))
        base.fill((7, 7, 11))
        grid = tilemap.grid
        for (x, y) in self.explored:
            if 0 <= x < w and 0 <= y < h:
                base.set_at((x, y), TILE_MM_COLORS.get(grid[y][x], (60, 60, 66)))
        self._base = base
        self._last_count = len(self.explored)


def _world_dot(surf, ox, oy, px_per_tile, wx, wy, color, radius, outline=None):
    px = ox + int(wx / C.TILE * px_per_tile)
    py = oy + int(wy / C.TILE * px_per_tile)
    pygame.draw.circle(surf, color, (px, py), radius)
    if outline:
        pygame.draw.circle(surf, outline, (px, py), radius, width=1)


NEUTRAL_BLIP_COLOR = (110, 220, 120)
HOSTILE_BLIP_COLOR = (225, 70, 70)
BOSS_BLIP_COLOR = (255, 40, 40)


def _visible_enemy_blips(enemies, explored):
    """Yields (pos, color, is_boss) for every enemy that should show a minimap
    blip - a tracked/ranked boss always shows (a directional aid toward it even
    from across the dungeon, per the user's ask), everything else only once its
    own tile has actually been explored (so the whole roster doesn't reveal
    itself the instant a dungeon is entered)."""
    for e in enemies:
        if not getattr(e, "alive", True):
            continue
        is_boss = getattr(e, "rank", None) == "boss"
        if not is_boss:
            etx, ety = int(e.pos.x // C.TILE), int(e.pos.y // C.TILE)
            if (etx, ety) not in explored:
                continue
        color = BOSS_BLIP_COLOR if is_boss else (NEUTRAL_BLIP_COLOR if getattr(e, "neutral", False)
                                                   else HOSTILE_BLIP_COLOR)
        yield e.pos, color, is_boss


def corner_origin():
    return C.SCREEN_W - CORNER_SIZE - 14, 74


def corner_block_height():
    """Total vertical footprint of the corner minimap block (map + zoom buttons +
    hint text), so other UI (e.g. the right-docked player panel) can anchor itself
    below it without the exact button/text layout leaking into ui.py."""
    return CORNER_SIZE + 6 + ZOOM_BTN_SIZE + 4 + 16


def corner_zoom_button_rects():
    """[(rect, delta), ...] for the +/- buttons under the corner minimap - lets you
    zoom it without opening the full map or touching the keyboard. Kept within the
    minimap's own horizontal footprint (not stuck out to the side) so they can never
    end up off-screen regardless of C.SCREEN_W."""
    x, y = corner_origin()
    row_y = y + CORNER_SIZE + 6
    return [
        (pygame.Rect(x, row_y, ZOOM_BTN_SIZE, ZOOM_BTN_SIZE), -CORNER_ZOOM_STEP),
        (pygame.Rect(x + CORNER_SIZE - ZOOM_BTN_SIZE, row_y, ZOOM_BTN_SIZE, ZOOM_BTN_SIZE), CORNER_ZOOM_STEP),
    ]


def draw_corner(surf, tilemap, mm, player_pos, peers=(), portals=(), enemies=()):
    """Always-on small map in the corner - RotMG keeps this up permanently
    without blocking the view of the play area. corner_zoom > 1 crops a region
    centered on the player instead of showing the whole map, like a radar."""
    base = mm._base_surface(tilemap)
    size = CORNER_SIZE
    x, y = corner_origin()

    if mm.corner_zoom <= CORNER_MIN_ZOOM:
        view = base
        view_w_tiles = tilemap.w
        origin_tx, origin_ty = 0, 0
    else:
        span = max(4, int(min(tilemap.w, tilemap.h) / mm.corner_zoom))
        ptx, pty = int(player_pos.x // C.TILE), int(player_pos.y // C.TILE)
        origin_tx = max(0, min(tilemap.w - span, ptx - span // 2))
        origin_ty = max(0, min(tilemap.h - span, pty - span // 2))
        view = base.subsurface((origin_tx, origin_ty, span, span))
        view_w_tiles = span

    scaled = pygame.transform.scale(view, (size, size))
    gold = (196, 162, 94)
    panel = pygame.Surface((size + 6, size + 6), pygame.SRCALPHA)
    panel.fill((10, 10, 14, 205))
    pygame.draw.rect(panel, (*gold, 90), (0, 0, size + 6, size + 6), width=1, border_radius=5)
    surf.blit(panel, (x - 3, y - 3))
    surf.blit(scaled, (x, y))
    pygame.draw.rect(surf, gold, (x - 3, y - 3, size + 6, size + 6), width=2, border_radius=4)
    tick = 4
    for cx, cy, dx, dy in ((x - 3, y - 3, 1, 1), (x - 3 + size + 6, y - 3, -1, 1),
                            (x - 3, y - 3 + size + 6, 1, -1), (x - 3 + size + 6, y - 3 + size + 6, -1, -1)):
        pygame.draw.line(surf, gold, (cx, cy), (cx + dx * tick, cy), 2)
        pygame.draw.line(surf, gold, (cx, cy), (cx, cy + dy * tick), 2)
    px_per_tile = size / view_w_tiles

    def local(wx, wy):
        return wx - origin_tx * C.TILE, wy - origin_ty * C.TILE

    for pt in portals:
        lx, ly = local(pt.pos.x, pt.pos.y)
        _world_dot(surf, x, y, px_per_tile, lx, ly, (220, 120, 255), 3)
    for peer in peers:
        lx, ly = local(peer.pos.x, peer.pos.y)
        _world_dot(surf, x, y, px_per_tile, lx, ly, (120, 200, 255), 2)
    for epos, color, is_boss in _visible_enemy_blips(enemies, mm.explored):
        lx, ly = local(epos.x, epos.y)
        _world_dot(surf, x, y, px_per_tile, lx, ly, color, 4 if is_boss else 2,
                    outline=(255, 255, 255) if is_boss else None)
    plx, ply = local(player_pos.x, player_pos.y)
    _world_dot(surf, x, y, px_per_tile, plx, ply, (255, 230, 90), 3, outline=(0, 0, 0))

    font_s = pygame.font.SysFont("consolas", 12)
    for rect, delta in corner_zoom_button_rects():
        pygame.draw.rect(surf, (24, 22, 20), rect, border_radius=3)
        pygame.draw.rect(surf, (0, 0, 0), rect, width=1, border_radius=3)
        pygame.draw.rect(surf, gold, (rect.x + 1, rect.y + 1, rect.w - 2, rect.h - 2), width=1, border_radius=3)
        label = font_s.render("+" if delta > 0 else "-", True, (230, 220, 195))
        surf.blit(label, (rect.centerx - label.get_width() // 2, rect.centery - label.get_height() // 2))
    hint = font_s.render(f"M: full map ({mm.corner_zoom:.1f}x)", True, (170, 170, 185))
    surf.blit(hint, (x, y + size + 6 + ZOOM_BTN_SIZE + 4))


def draw_full_map(surf, tilemap, mm, player_pos, peers=(), portals=(), zone_name="", enemies=()):
    """The M-key full map overlay: same fog data, zoomed in/out and centered
    on the player, with scroll-wheel / +- zoom (see MinimapState.adjust_zoom)."""
    surf.fill((8, 8, 12))
    base = mm._base_surface(tilemap)
    px_per_tile = max(2, int(5 * mm.zoom))
    ox = C.SCREEN_W // 2 - int(player_pos.x / C.TILE * px_per_tile)
    oy = C.SCREEN_H // 2 - int(player_pos.y / C.TILE * px_per_tile)
    # crop to just the tiles that could land on screen before scaling, instead of
    # scaling the WHOLE map every frame just to blit a screen-sized window of it -
    # harmless at the old 800x800 size but it was already the single most expensive
    # thing this screen did (pygame.transform.scale on the full map), and it grows
    # with map area: at 900x900 that's a 5400x5400px scale target for a 1280x720
    # destination, mostly thrown away by the blit's own clipping. Cropping first
    # ties the scale() cost to the viewport instead of the whole continent.
    view_w = tilemap.w if px_per_tile == 0 else min(tilemap.w, C.SCREEN_W // px_per_tile + 3)
    view_h = tilemap.h if px_per_tile == 0 else min(tilemap.h, C.SCREEN_H // px_per_tile + 3)
    crop_x0 = max(0, min(tilemap.w - view_w, int(player_pos.x / C.TILE - view_w / 2)))
    crop_y0 = max(0, min(tilemap.h - view_h, int(player_pos.y / C.TILE - view_h / 2)))
    cropped = base.subsurface((crop_x0, crop_y0, view_w, view_h))
    scaled = pygame.transform.scale(cropped, (view_w * px_per_tile, view_h * px_per_tile))
    surf.blit(scaled, (ox + crop_x0 * px_per_tile, oy + crop_y0 * px_per_tile))
    for pt in portals:
        _world_dot(surf, ox, oy, px_per_tile, pt.pos.x, pt.pos.y, (220, 120, 255), 5, outline=(0, 0, 0))
    for peer in peers:
        _world_dot(surf, ox, oy, px_per_tile, peer.pos.x, peer.pos.y, (120, 200, 255), 4, outline=(0, 0, 0))
    for epos, color, is_boss in _visible_enemy_blips(enemies, mm.explored):
        _world_dot(surf, ox, oy, px_per_tile, epos.x, epos.y, color, 6 if is_boss else 3,
                    outline=(255, 255, 255) if is_boss else (0, 0, 0))
    _world_dot(surf, ox, oy, px_per_tile, player_pos.x, player_pos.y, (255, 230, 90), 5, outline=(0, 0, 0))
    font_m = pygame.font.SysFont("consolas", 18, bold=True)
    font_s = pygame.font.SysFont("consolas", 14)
    title = font_m.render(f"{zone_name} - Map", True, (230, 220, 190))
    surf.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 16))
    hint = font_s.render(f"Scroll or +/- to zoom ({mm.zoom:.2f}x)  |  M or Esc to close", True, (170, 170, 185))
    surf.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, C.SCREEN_H - 30))

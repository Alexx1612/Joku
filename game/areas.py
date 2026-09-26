"""
Batch 15 (E1): big named places - ten hand-composed realm areas (each at least
~40x40 tiles, with paths, huts, tents, fences and big props) stamped onto the
generated continent, plus the enlarged Nexus's districts (tavern, garden park,
dockside, arena plaza).

Placement (place_realm_areas) searches the continent for a spot where the whole
footprint is solidly the area's biome, away from every other structure, then
stamps a layout drawn from world tiles + game/big_props multi-tile props. Each
area records named spots (e.g. its NPC's stand) so game/npcs.py can put people
in them ("area:<key>" area keys).
"""
import math
import random

import pygame

from game import world
from game import big_props as BP

AREA_DEFS = {
    "tavern_town": dict(name="Tavern Town", biome=None, size=(50, 46),
                        lore="A cosy outer-ring village built around a tavern that claims to have invented "
                             "the chair. Safe from monsters; not safe from the karaoke."),
    "oasis_bazaar": dict(name="Oasis Bazaar", biome="desert", size=(46, 44),
                         lore="A palm-ringed pond in the dunes where traders sell sand to people who already "
                              "have plenty."),
    "frozen_lake_camp": dict(name="Frozen Lake Camp", biome="tundra", size=(46, 44),
                             lore="Ice-fishing tents on a frozen lake. The fish are frozen too, which "
                                  "really simplifies the cooking."),
    "witchs_hollow": dict(name="Witch's Hollow", biome="swamp", size=(44, 42),
                          lore="Bubbling cauldrons, crooked huts and a strong smell of 'soup'. Do not ask "
                               "what kind."),
    "mountain_monastery": dict(name="Mountain Monastery", biome="highlands", size=(46, 44),
                               lore="A walled monastery of monks sworn to silence, except about beer."),
    "forge_camp": dict(name="Forge Camp", biome="ashlands", size=(44, 42),
                       lore="Furnaces, anvils and a smith who swears every sword is 'basically finished'."),
    "botanists_glade": dict(name="Botanist's Glade", biome="jungle", size=(44, 42),
                            lore="A tidy clearing of planters and labelled weeds. Some of the weeds have "
                                 "learned to read the labels."),
    "scrapyard": dict(name="Scrapyard", biome="wasteland", size=(46, 42),
                      lore="Heaps of rusted junk, lovingly organised by a golem who calls it 'the good stuff'."),
    "crystal_caverns": dict(name="Crystal Caverns", biome="cave", size=(44, 42),
                            lore="The glittering mouth of the crystal caves. Everything hums faintly, including "
                                 "your teeth."),
    "elk_meadow": dict(name="Elk Meadow", biome="forest", size=(48, 44),
                       lore="Open grass, a pond and a fenced pen the Grand Elk Herd politely ignores."),
}
AREA_ORDER = ["tavern_town", "oasis_bazaar", "frozen_lake_camp", "witchs_hollow", "mountain_monastery",
              "forge_camp", "botanists_glade", "scrapyard", "crystal_caverns", "elk_meadow"]
OUTER_BIOMES = ("forest", "desert", "tundra", "swamp")
_GROUND_OF = {name: g for g, name in world.GROUND_TO_BIOME_NAME.items()}


class _Builder:
    """Stamps one area's layout into the grid, relative to its centre tile."""

    def __init__(self, grid, key, rect, ground, rng):
        self.grid, self.key, self.rect, self.ground, self.rng = grid, key, rect, ground, rng
        self.cx, self.cy = rect.centerx, rect.centery
        self.h, self.w = len(grid), len(grid[0])
        self.spots = {}
        self.inside = set()
        self.reserved = set()   # tiles a later prop must not cover (paths, doors, spots)
        self.road = set()       # path tiles only - gates in a fence ring line up with these

    def ok(self, x, y):
        return 1 <= x < self.w - 1 and 1 <= y < self.h - 1

    def set(self, x, y, tile):
        if self.ok(x, y):
            self.grid[y][x] = tile

    # --- terrain
    def clear_shape(self, power=3.0):
        """Rounded-rect (superellipse) footprint filled with the area's ground, edges
        wobbled so it doesn't read as a stamped box."""
        hw, hh = self.rect.w / 2.0, self.rect.h / 2.0
        ph = self.rng.uniform(0, math.tau)
        for y in range(self.rect.top, self.rect.bottom):
            for x in range(self.rect.left, self.rect.right):
                dx, dy = (x + 0.5 - self.cx) / hw, (y + 0.5 - self.cy) / hh
                ang = math.atan2(dy, dx)
                lim = 1.0 - 0.07 * (1 + math.sin(ang * 5 + ph))
                if abs(dx) ** power + abs(dy) ** power <= lim and self.ok(x, y):
                    self.grid[y][x] = self.ground
                    self.inside.add((x, y))

    def blob(self, ox, oy, rx, ry, tile, wobble=0.18):
        ph = self.rng.uniform(0, math.tau)
        for y in range(int(self.cy + oy - ry - 1), int(self.cy + oy + ry + 2)):
            for x in range(int(self.cx + ox - rx - 1), int(self.cx + ox + rx + 2)):
                dx, dy = (x - self.cx - ox) / max(1, rx), (y - self.cy - oy) / max(1, ry)
                ang = math.atan2(dy, dx)
                if dx * dx + dy * dy <= (1 - wobble * 0.5 * (1 + math.sin(ang * 4 + ph))) and (x, y) in self.inside:
                    self.set(x, y, tile)

    def path(self, x0, y0, x1, y1, tile, width=3):
        """An L-shaped path between two offsets (horizontal first)."""
        ax, ay, bx, by = self.cx + x0, self.cy + y0, self.cx + x1, self.cy + y1
        half = width // 2
        for x in range(min(ax, bx), max(ax, bx) + 1):
            for d in range(-half, width - half):
                self._path_tile(x, ay + d, tile)
        for y in range(min(ay, by), max(ay, by) + 1):
            for d in range(-half, width - half):
                self._path_tile(bx + d, y, tile)

    def _path_tile(self, x, y, tile):
        if (x, y) in self.inside:
            self.set(x, y, tile)
            self.reserved.add((x, y))
            self.road.add((x, y))

    def roads(self, tile, width=3):
        """Cross roads from the centre out to all four edges (so every gate lines up)."""
        hw, hh = self.rect.w // 2 + 1, self.rect.h // 2 + 1
        self.path(-hw, 0, hw, 0, tile, width)
        self.path(0, -hh, 0, hh, tile, width)

    def fence_ring(self, inset=1):
        """Fence posts around the footprint's rim, leaving gates wherever a road exits."""
        for (x, y) in list(self.inside):
            if (x, y) in self.reserved:
                continue
            edge = any((x + dx, y + dy) not in self.inside for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if not edge:
                continue
            if inset and not self._near_road(x, y, 2):
                self.prop("fence", 0, 0, at=(x, y))

    def _near_road(self, x, y, r):
        return any((x + dx, y + dy) in self.road for dx in range(-r, r + 1) for dy in range(-r, r + 1))

    def hut(self, ox, oy, w, h, door="S", wall_biome=None, floor=world.AREA_PLANK):
        """A walled hut (solid building-wall tiles with the gold outline) with a
        2-tile doorway and a path stub leading out of it."""
        wall = world.BUILDING_WALL_TILE.get(wall_biome or self.biome_name(), next(iter(world.BUILDING_WALL_TILE.values())))
        x0, y0 = self.cx + ox - w // 2, self.cy + oy - h // 2
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                if (x, y) not in self.inside:
                    continue
                border = x in (x0, x0 + w - 1) or y in (y0, y0 + h - 1)
                self.set(x, y, wall if border else floor)
                if border:
                    self.reserved.add((x, y))
        mx, my = x0 + w // 2, y0 + h // 2
        doors = {"S": [(mx - 1, y0 + h - 1), (mx, y0 + h - 1)], "N": [(mx - 1, y0), (mx, y0)],
                 "E": [(x0 + w - 1, my - 1), (x0 + w - 1, my)], "W": [(x0, my - 1), (x0, my)]}[door]
        step = {"S": (0, 1), "N": (0, -1), "E": (1, 0), "W": (-1, 0)}[door]
        for (x, y) in doors:
            self.set(x, y, floor)
            for k in range(1, 3):  # keep the doorstep open
                xx, yy = x + step[0] * k, y + step[1] * k
                if (xx, yy) in self.inside and self.grid[yy][xx] in world.SOLID:
                    self.set(xx, yy, self.ground)
                self.reserved.add((xx, yy))
        return (mx - self.cx, my - self.cy)

    def biome_name(self):
        return world.GROUND_TO_BIOME_NAME.get(self.ground, "forest")

    # --- props
    def prop(self, kind, ox, oy, at=None):
        """Places a big prop at an offset (or absolute tile `at`) if its footprint is
        free open ground inside the area. Returns True if placed."""
        ax, ay = at if at is not None else (self.cx + ox, self.cy + oy)
        tiles = BP.footprint_tiles(kind, (ax, ay))
        for (x, y) in tiles:
            if (x, y) not in self.inside or not self.ok(x, y):
                return False
            if (x, y) in self.reserved and at is None:
                return False
            t = self.grid[y][x]
            if t in world.SOLID or t in world.BIG_PROP_ALL_IDS or t == world.WATER or t in world.INTERACTIVE:
                return False
        base = self.grid[ay][ax]
        if (base, kind) not in world.BIG_PROP_TILE:
            base = self.ground
        if not world.stamp_big_prop(self.grid, (ax, ay), kind, base):
            return False
        for (x, y) in tiles:
            self.reserved.add((x, y))
        return True

    def ring(self, kind, n, rx, ry, ox=0, oy=0, phase=0.0):
        placed = 0
        for i in range(n):
            a = phase + math.tau * i / n
            if self.prop(kind, int(ox + math.cos(a) * rx), int(oy + math.sin(a) * ry)):
                placed += 1
        return placed

    def scatter(self, kind, n, spread=0.42, tries=40):
        placed = 0
        hw, hh = self.rect.w * spread, self.rect.h * spread
        for _ in range(n * tries):
            if placed >= n:
                break
            if self.prop(kind, int(self.rng.uniform(-hw, hw)), int(self.rng.uniform(-hh, hh))):
                placed += 1
        return placed

    def row(self, kind, n, ox, oy, dx, dy):
        for i in range(n):
            self.prop(kind, ox + dx * i, oy + dy * i)

    def spot(self, name, ox, oy):
        x, y = self.cx + ox, self.cy + oy
        self.spots[name] = (x, y)
        self.reserved.add((x, y))


# ----------------------------------------------------------------- layouts

def _tavern_town(b):
    b.clear_shape()
    b.roads(world.AREA_COBBLE, 3)
    b.blob(0, 0, 6, 5, world.AREA_COBBLE, wobble=0.0)  # town square
    b.prop("well", 0, -1)
    b.prop("statue", 4, 3)
    tav = b.hut(-12, -9, 14, 10, door="S")
    b.row("barrels", 3, tav[0] - 4, tav[1] - 3, 3, 0)
    b.row("bench", 2, tav[0] - 4, tav[1] + 1, 5, 0)
    b.spot("tavern", tav[0], tav[1] + 1)
    b.spot("square", 3, -3)
    for (hx, hy, door) in ((12, -10, "S"), (13, 10, "N"), (-13, 10, "N"), (-20, 1, "E"), (20, 1, "W")):
        b.hut(hx, hy, 8, 6, door=door)
    for ox in (-8, 8):
        b.prop("market_stall", ox, 5)
    b.row("lamp_post", 5, -18, -2, 9, 0)
    b.row("lamp_post", 4, 2, -18, 0, 10)
    b.scatter("flower_planter", 6)
    b.scatter("hay_bale", 5)
    b.scatter("cart", 2)
    b.scatter("banner", 4)
    b.scatter("oak", 5, spread=0.46)
    b.fence_ring()


def _oasis_bazaar(b):
    b.clear_shape()
    b.roads(world.AREA_COBBLE, 3)
    b.blob(9, -8, 7, 5, world.WATER)      # the oasis pond
    b.blob(9, -8, 9, 7, world.GRASS2, wobble=0.1)
    b.blob(9, -8, 7, 5, world.WATER)
    b.ring("palm", 9, 10, 8, ox=9, oy=-8, phase=0.3)
    b.spot("pond", 1, -6)
    b.spot("stalls", -6, 3)
    for i, (ox, oy) in enumerate(((-12, 5), (-6, 8), (-14, -4), (6, 8), (12, 5))):
        b.prop("market_stall", ox, oy)
    for ox, oy in ((-15, 13), (15, 13), (-16, -14)):
        b.prop("tent", ox, oy)
    b.scatter("cart", 3)
    b.scatter("barrels", 5)
    b.scatter("lamp_post", 5)
    b.scatter("banner", 3)
    b.scatter("dead_big", 2, spread=0.46)


def _frozen_lake_camp(b):
    b.clear_shape()
    b.blob(0, -2, 14, 9, world.AREA_FROZEN, wobble=0.12)
    for ox, oy in ((-6, -3), (3, -6), (7, 1), (-2, 2)):   # ice-fishing holes
        b.set(b.cx + ox, b.cy + oy, world.WATER)
        b.reserved.add((b.cx + ox, b.cy + oy))
    b.path(-22, 12, 22, 12, world.DIRT, 3)
    b.path(0, 12, 0, 22, world.DIRT, 3)
    b.spot("lake", -1, 4)
    for ox, oy in ((-15, 12), (-6, 16), (7, 16), (16, 12)):
        b.prop("tent", ox, oy)
    for ox, oy in ((-10, 9), (10, 9), (0, 18)):
        b.prop("campfire", ox, oy)
    for ox, oy in ((-17, -2), (17, -3), (12, -12)):
        b.prop("fishing_rack", ox, oy)
    b.prop("signboard", 3, 11)
    b.scatter("barrels", 4)
    b.scatter("snow_pine", 10, spread=0.47)
    b.scatter("ice_boulder", 2, spread=0.46)


def _witchs_hollow(b):
    b.clear_shape()
    b.roads(world.DIRT, 2)
    for ox, oy, rx, ry in ((-11, -9, 5, 3), (10, 10, 4, 3), (12, -10, 3, 2)):
        b.blob(ox, oy, rx, ry, world.WATER)
    h1 = b.hut(-9, 7, 9, 7, door="N", wall_biome="swamp")
    b.hut(11, -1, 8, 6, door="W", wall_biome="swamp")
    b.spot("cauldrons", 2, -4)
    b.ring("cauldron", 5, 4, 3, ox=2, oy=-4)
    b.prop("totem_big", -3, -12)
    b.prop("totem_big", 6, 13)
    b.scatter("mushroom_tree", 5, spread=0.44)
    b.scatter("dead_big", 9, spread=0.47)
    b.scatter("lamp_post", 3)
    b.scatter("barrels", 2)


def _mountain_monastery(b):
    b.clear_shape()
    b.roads(world.AREA_COBBLE, 3)
    hall = b.hut(0, -6, 20, 14, door="S", wall_biome="highlands", floor=world.AREA_COBBLE)
    b.prop("shrine", hall[0], hall[1] - 3)
    for dx in (-6, 6):
        b.prop("statue", hall[0] + dx, hall[1] - 1)
    b.row("bench", 2, hall[0] - 4, hall[1] + 3, 7, 0)
    b.spot("courtyard", 3, 7)
    b.prop("bell_tower", 15, 9)
    b.prop("bell_tower", -15, 9)
    b.scatter("flower_planter", 6)
    b.scatter("lamp_post", 5)
    b.scatter("pine", 10, spread=0.47)
    b.scatter("big_boulder", 3, spread=0.46)


def _forge_camp(b):
    b.clear_shape()
    b.roads(world.DIRT, 3)
    b.blob(0, 0, 9, 7, world.AREA_COBBLE, wobble=0.05)   # the work yard
    for ox in (-5, 0, 5):
        b.prop("furnace", ox, -4)
    for ox in (-6, -2, 2, 6):
        b.prop("anvil", ox, 3)
    b.spot("yard", 0, 6)
    for ox, oy in ((-14, 10), (14, 10), (-14, -10)):
        b.prop("tent", ox, oy)
    b.hut(14, -10, 8, 6, door="S", wall_biome="ashlands")
    b.scatter("scrap_pile", 3)
    b.scatter("barrels", 5)
    b.scatter("campfire", 3)
    b.scatter("dead_big", 5, spread=0.47)
    b.fence_ring()


def _botanists_glade(b):
    b.clear_shape()
    b.blob(0, 0, 17, 15, world.GRASS2, wobble=0.1)
    b.roads(world.DIRT, 2)
    lab = b.hut(-10, -8, 10, 7, door="S", wall_biome="jungle")
    b.spot("lab", lab[0], lab[1] + 5)
    for oy in (-2, 4):
        b.row("flower_planter", 4, 4, oy, 3, 0)
    b.prop("well", 9, -9)
    b.row("bench", 2, -12, 6, 4, 0)
    b.prop("signboard", 3, 11)
    b.ring("jungle_giant", 10, 19, 17, phase=0.2)
    b.scatter("mushroom_tree", 3, spread=0.4)
    b.scatter("palm", 4, spread=0.46)


def _scrapyard(b):
    b.clear_shape()
    b.roads(world.DIRT, 3)
    for ox, oy in ((-12, -10), (-5, -12), (8, -10), (13, 7), (-12, 9), (5, 11)):
        b.prop("scrap_pile", ox, oy)
    b.spot("yard", 2, -3)
    b.hut(-2, -2, 8, 6, door="E", wall_biome="wasteland")
    b.scatter("cart", 3)
    b.scatter("barrels", 5)
    b.scatter("lamp_post", 3)
    b.prop("totem_big", 15, -2)
    b.scatter("dead_big", 4, spread=0.47)
    b.fence_ring()


def _crystal_caverns(b):
    b.clear_shape()
    b.roads(world.DIRT, 2)
    # the cave mouth: a rock arch around a dark floor pocket to the north
    for y in range(b.cy - 14, b.cy - 5):
        for x in range(b.cx - 9, b.cx + 10):
            dx, dy = (x - b.cx) / 9.0, (y - (b.cy - 9)) / 5.0
            d = dx * dx + dy * dy
            if (x, y) not in b.inside or (x, y) in b.reserved:
                continue
            if 0.62 < d <= 1.0 and not (abs(x - b.cx) <= 1 and y > b.cy - 9):
                b.set(x, y, world.WALL_CAVE)   # not ROCK - clear_blockers would erase it
            elif d <= 0.62:
                b.set(x, y, world.CAVE)
    b.spot("mouth", 3, -3)
    b.ring("crystal_cluster", 7, 13, 11, oy=2, phase=0.4)
    b.scatter("crystal_spire", 7, spread=0.46)
    b.scatter("big_boulder", 3, spread=0.46)
    for ox in (-5, 5):
        b.prop("tent", ox * 2, 10)
    b.prop("campfire", 0, 7)
    b.prop("signboard", -3, 4)
    b.scatter("lamp_post", 4)


def _elk_meadow(b):
    b.clear_shape()
    b.blob(0, 0, 18, 16, world.GRASS2, wobble=0.15)
    b.blob(-9, -7, 5, 4, world.WATER)
    b.path(-25, 10, 25, 10, world.DIRT, 2)
    b.spot("meadow", 4, -1)
    # a fenced pen with a gate facing the path
    for x in range(b.cx + 2, b.cx + 14):
        for y in (b.cy - 10, b.cy + 5):
            if abs(x - (b.cx + 8)) > 1 or y == b.cy - 10:
                b.prop("fence", 0, 0, at=(x, y))
    for y in range(b.cy - 10, b.cy + 6):
        for x in (b.cx + 2, b.cx + 13):
            b.prop("fence", 0, 0, at=(x, y))
    b.row("hay_bale", 3, 5, -6, 3, 0)
    b.prop("cart", -14, 6)
    b.row("bench", 2, -6, 5, 5, 0)
    b.prop("signboard", 0, 8)
    b.ring("oak", 12, 21, 19, phase=0.1)
    b.scatter("pine", 4, spread=0.46)


LAYOUTS = {"tavern_town": _tavern_town, "oasis_bazaar": _oasis_bazaar, "frozen_lake_camp": _frozen_lake_camp,
           "witchs_hollow": _witchs_hollow, "mountain_monastery": _mountain_monastery,
           "forge_camp": _forge_camp, "botanists_glade": _botanists_glade, "scrapyard": _scrapyard,
           "crystal_caverns": _crystal_caverns, "elk_meadow": _elk_meadow}


def stamp_area(grid, key, rect, biome, rng=None):
    rng = rng or random.Random()
    ground = _GROUND_OF.get(biome, world.GRASS)
    b = _Builder(grid, key, rect, ground, rng)
    LAYOUTS[key](b)
    world.clear_blockers(grid, rect, margin=3, floor_tile=world.DIRT)
    return b.spots


# --------------------------------------------------------------- placement

def _score(grid, rect, biome):
    """Share of sample points inside `rect` (inflated by 2) that belong to `biome`;
    water/ocean counts against it."""
    good = total = 0
    r = rect.inflate(4, 4)
    h, w = len(grid), len(grid[0])
    for y in range(r.top, r.bottom, 5):
        for x in range(r.left, r.right, 5):
            total += 1
            if not (0 <= x < w and 0 <= y < h):
                return 0.0
            t = grid[y][x]
            if world.TILE_TO_BIOME_NAME.get(t) == biome:
                good += 1
            elif t == world.WATER:
                good -= 1
    return good / max(1, total)


def place_realm_areas(sim, placed_rects, rng=None):
    """Finds a spot for and stamps every area. Returns [{key, name, biome, rect,
    spots}] (tile space) and appends each rect to placed_rects."""
    rng = rng or random.Random()
    grid = sim.realm_map.grid
    y0, y1, x0, x1 = sim._continent_bounds()
    sp = sim.spawn_point()
    sp_t = (sp.x / world.C.TILE, sp.y / world.C.TILE)
    cand = {}
    for ty in range(max(30, y0), min(len(grid) - 30, y1), 8):
        row = grid[ty]
        for tx in range(max(30, x0), min(len(grid[0]) - 30, x1), 8):
            b = world.TILE_TO_BIOME_NAME.get(row[tx])
            if b is not None:
                cand.setdefault(b, []).append((tx, ty))
    out = []
    for key in AREA_ORDER:
        d = AREA_DEFS[key]
        w, h = d["size"]
        biomes = [d["biome"]] if d["biome"] else list(OUTER_BIOMES)
        best = None
        for need in (0.85, 0.72, 0.55):
            scored = []
            for b in biomes:
                for (tx, ty) in cand.get(b, ()):
                    rect = pygame.Rect(tx - w // 2, ty - h // 2, w, h)
                    if any(rect.inflate(12, 12).colliderect(r) for r in placed_rects):
                        continue
                    s = _score(grid, rect, b)
                    if s < need:
                        continue
                    if key == "tavern_town":   # a village near where you wash ashore
                        dist = math.hypot(tx - sp_t[0], ty - sp_t[1])
                        if dist < 45:
                            continue
                        scored.append((dist - s * 40, rect, b))
                    else:
                        scored.append((-s + rng.random() * 0.05, rect, b))
            if scored:
                scored.sort(key=lambda it: it[0])
                best = scored[0]
                break
        if best is None:
            continue
        _score_v, rect, b = best
        spots = stamp_area(grid, key, rect, b, rng)
        placed_rects.append(rect)
        out.append(dict(key=key, name=d["name"], biome=b, rect=rect, spots=spots, lore=d["lore"]))
    return out


# ------------------------------------------------------------------- Nexus

NEXUS_DISTRICTS = {
    # name: (offset of district centre from the Nexus centre, in tiles)
    "tavern": (-30, 12),
    "park": (30, -10),
    "dockside": (0, 29),
    "arena": (-30, -20),
}


def build_nexus_districts(grid):
    """Adds the tavern, garden park, dockside and arena plaza to an enlarged Nexus
    grid (deterministic - co-op clients build the same Nexus locally)."""
    rng = random.Random(1505)
    h, w = len(grid), len(grid[0])
    mid_x, mid_y = w // 2, h // 2
    F = world.NEXUS_FLOOR

    def box(x0, y0, x1, y1, tile, only=(F,)):
        for y in range(max(1, y0), min(h - 1, y1)):
            for x in range(max(1, x0), min(w - 1, x1)):
                if only is None or grid[y][x] in only:
                    grid[y][x] = tile

    def put(kind, x, y):
        tiles = BP.footprint_tiles(kind, (x, y))
        if all(1 <= tx < w - 1 and 1 <= ty < h - 1 and grid[ty][tx] not in world.SOLID
               and grid[ty][tx] not in world.BIG_PROP_ALL_IDS and grid[ty][tx] not in world.INTERACTIVE
               and grid[ty][tx] != world.WATER and grid[ty][tx] != world.NEXUS_FOUNTAIN for tx, ty in tiles):
            world.stamp_big_prop(grid, (x, y), kind)

    # tavern (west): a walled hall with a plank floor, door to the east
    tx, ty = mid_x + NEXUS_DISTRICTS["tavern"][0], mid_y + NEXUS_DISTRICTS["tavern"][1]
    wall = world.BUILDING_WALL_TILE["highlands"]
    x0, y0, x1, y1 = tx - 9, ty - 6, tx + 9, ty + 6
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            grid[y][x] = wall if (x in (x0, x1) or y in (y0, y1)) else world.AREA_PLANK
    for y in (ty - 1, ty, ty + 1):
        grid[y][x1] = world.AREA_PLANK
    for i, (bx, by) in enumerate(((x0 + 3, y0 + 3), (x0 + 3, y1 - 2), (x0 + 8, y0 + 3), (x0 + 8, y1 - 2))):
        put("bench", bx, by)
    put("barrels", x0 + 2, ty)
    put("barrels", x0 + 14, y0 + 2)
    put("signboard", x1 + 2, ty - 3)
    put("lamp_post", x1 + 2, ty + 3)

    # garden park (east): grass, a pond, oaks, planters and benches
    px, py = mid_x + NEXUS_DISTRICTS["park"][0], mid_y + NEXUS_DISTRICTS["park"][1]
    for y in range(py - 11, py + 12):
        for x in range(px - 12, px + 13):
            if ((x - px) / 12.5) ** 2 + ((y - py) / 11.5) ** 2 <= 1 and 1 <= x < w - 1 and 1 <= y < h - 1 \
                    and grid[y][x] == F:
                grid[y][x] = world.GRASS
    for y in range(py - 3, py + 4):
        for x in range(px - 4, px + 5):
            if ((x - px) / 4.5) ** 2 + ((y - py) / 3.2) ** 2 <= 1:
                grid[y][x] = world.WATER
    for i in range(9):
        a = math.tau * i / 9 + 0.3
        put("oak", int(px + math.cos(a) * 9.5), int(py + math.sin(a) * 8.5))
    for bx, by in ((px - 6, py + 5), (px + 5, py + 5), (px - 6, py - 5)):
        put("bench", bx, by)
    for bx, by in ((px + 6, py - 5), (px - 2, py + 7)):
        put("flower_planter", bx, by)
    for gy, gx in ((-7, -9), (8, 9)):
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                yy, xx = py + gy + dy, px + gx + dx
                if grid[yy][xx] == world.GRASS:
                    grid[yy][xx] = world.NEXUS_GARDEN

    # dockside (south): a strip of harbour water with plank piers, boats and racks
    dy0 = h - 8
    box(2, dy0, w - 2, h - 1, world.WATER, only=None)
    for x in range(2, w - 2):
        grid[dy0 - 1][x] = world.AREA_PLANK
        grid[dy0 - 2][x] = world.AREA_PLANK
    for pier_x in (mid_x - 24, mid_x - 8, mid_x + 8, mid_x + 24):
        for y in range(dy0, h - 2):
            for x in (pier_x, pier_x + 1):
                grid[y][x] = world.AREA_PLANK
        put("boat", pier_x + 4, dy0 - 3)
    for x in range(mid_x - 30, mid_x + 31, 12):
        put("fishing_rack", x, dy0 - 4)
        put("barrels", x + 5, dy0 - 4)
    for x in range(mid_x - 33, mid_x + 34, 11):
        put("lamp_post", x, dy0 - 5)

    # arena plaza (north-west): a cobble ring with a fenced edge, banners and a statue
    ax, ay = mid_x + NEXUS_DISTRICTS["arena"][0], mid_y + NEXUS_DISTRICTS["arena"][1]
    for y in range(ay - 10, ay + 11):
        for x in range(ax - 11, ax + 12):
            d = ((x - ax) / 11.0) ** 2 + ((y - ay) / 10.0) ** 2
            if d <= 1 and 1 <= x < w - 1 and 1 <= y < h - 1 and grid[y][x] == F:
                grid[y][x] = world.AREA_COBBLE
    for i in range(28):
        a = math.tau * i / 28
        x, y = int(round(ax + math.cos(a) * 10.4)), int(round(ay + math.sin(a) * 9.4))
        if abs(math.sin(a)) < 0.25 or abs(math.cos(a)) < 0.2:   # four gates
            continue
        put("fence", x, y)
    put("statue", ax, ay)
    for dx, dy in ((-7, -6), (7, -6), (-7, 6), (7, 6)):
        put("banner", ax + dx, ay + dy)

    # a few lamp posts / planters along the main walkways (seeded, so identical everywhere)
    for _ in range(14):
        x, y = rng.randint(4, w - 5), rng.randint(4, h - 12)
        if grid[y][x] == F and abs(x - mid_x) + abs(y - mid_y) > 8:
            put(rng.choice(["lamp_post", "flower_planter", "barrels", "bench"]), x, y)
    return {name: (mid_x + ox, mid_y + oy) for name, (ox, oy) in NEXUS_DISTRICTS.items()}

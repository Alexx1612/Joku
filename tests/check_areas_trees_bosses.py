"""
Batch 15 Phase 3B regression checks: the ten big named realm areas (game/areas.py),
the enlarged deterministic Nexus with its districts, multi-tile big props/trees
(game/big_props.py - solid trunk only, canopy walkable, canopy overlay pass), and
bigger bosses / mini-bosses / landmark guardians (sprite + hitbox scale).

Run with: .venv\\Scripts\\python.exe tests\\check_areas_trees_bosses.py
"""
import collections
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((400, 300))

from game import achievements, accounts, characters
achievements._DIR = tempfile.mkdtemp(prefix="rr_atb_ach_")
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_atb_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_atb_char_")

from game import world, areas, big_props, sprites, story, codex, npcs
from game import constants as C
from game.realm_sim import RealmSim
from game.entities import Enemy, Player, ENEMY_KINDS, BOSS_SCALE, MINI_BOSS_SCALE, GUARDIAN_SCALE

random.seed(7)
SIM = RealmSim()
GRID = SIM.realm_map.grid
H, W = len(GRID), len(GRID[0])


def _reachable_from_spawn():
    """Flood fill over walkable tiles (continent + islands) from the arrival point."""
    sp = SIM.spawn_point()
    start = (int(sp.x // C.TILE), int(sp.y // C.TILE))
    seen = bytearray(W * H)
    seen[start[1] * W + start[0]] = 1
    stack = [start]
    solid = world.SOLID
    while stack:
        x, y = stack.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < W and 0 <= ny < H:
                k = ny * W + nx
                if not seen[k] and GRID[ny][nx] not in solid:
                    seen[k] = 1
                    stack.append((nx, ny))
    return seen


REACH = _reachable_from_spawn()


def _reached(tx, ty):
    return REACH[ty * W + tx] == 1


def check_ten_big_areas():
    keys = {a["key"] for a in SIM.areas}
    assert keys == set(areas.AREA_ORDER), f"missing areas: {set(areas.AREA_ORDER) - keys}"
    rects = [a["rect"] for a in SIM.areas]
    for a in SIM.areas:
        r = a["rect"]
        assert r.w >= 40 and r.h >= 40, (a["key"], r.size)
        assert 0 < r.left and 0 < r.top and r.right < W and r.bottom < H, (a["key"], r)
        others = [o for o in rects if o is not r]
        assert not any(r.colliderect(o) for o in others), f"{a['key']} overlaps another area"
        # a real place: lots of big props / huts inside, not a bare patch
        n_big = sum(1 for y in range(r.top, r.bottom) for x in range(r.left, r.right)
                    if GRID[y][x] in world.BIG_PROP_KIND_BY_ID)
        assert n_big >= 12, (a["key"], n_big)
        # every named spot (NPC stands) is reachable on foot from the arrival beach
        for name, (sx, sy) in a["spots"].items():
            ok = any(_reached(sx + dx, sy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            assert ok, (a["key"], name, (sx, sy))
        # towns are safe - no lairs inside
        assert not any(r.collidepoint(int(l["pos"].x // C.TILE), int(l["pos"].y // C.TILE)) for l in SIM.lairs)
    print(f"check_ten_big_areas: PASSED ({', '.join(sorted(keys))})")


def check_npcs_live_in_their_areas():
    by_key = {a["key"]: a["rect"] for a in SIM.areas}
    placed = 0
    for n in SIM.npcs:
        area = npcs.NPCS[n.npc_id]["area"]
        if not area.startswith("area:"):
            continue
        r = by_key[area.split(":", 1)[1]].inflate(8, 8)
        assert r.collidepoint(int(n.home.x // C.TILE), int(n.home.y // C.TILE)), (n.npc_id, n.home, r)
        placed += 1
    assert placed >= 10, placed
    # dictionary + quest map know about the places
    info = codex.realm_areas(SIM)
    assert len(info["places"]) == 10
    assert codex.markers_for({"areas": ["place:forge_camp"]}, info)
    assert codex.entry("area:place:tavern_town") is not None
    assert any(e["title"] == "Scrapyard" for e in codex.search("scrapyard"))
    print(f"check_npcs_live_in_their_areas: PASSED ({placed} NPCs in areas)")


def check_nexus_enlarged_and_deterministic():
    a, b = world.make_nexus(), world.make_nexus()
    assert (len(a[0]), len(a)) == (world.NEXUS_W, world.NEXUS_H) == (96, 72)
    assert a == b, "Nexus must be identical on every build (co-op clients build their own)"
    counts = collections.Counter(t for row in a for t in row)
    assert counts[world.AREA_PLANK] > 150      # tavern floor + dock piers
    assert counts[world.GRASS] > 150           # garden park
    assert counts[world.WATER] > 400           # the harbour
    assert counts[world.AREA_COBBLE] > 200     # arena plaza
    assert counts[world.PORTAL] == 1 and counts[world.VAULT_TILE] == 1 and counts[world.BAZAAR_PORTAL] == 1
    assert sum(1 for t in counts.elements() if t in world.BIG_PROP_KIND_BY_ID) >= 20
    tm = world.TileMap(a)
    bitter = npcs.nexus_positions(tm)["bitterwick"]
    assert a[int(bitter.y // C.TILE)][int(bitter.x // C.TILE)] == world.AREA_PLANK, "barkeep stands in the tavern"
    print("check_nexus_enlarged_and_deterministic: PASSED")


def check_big_trees_solid_trunk_only():
    kinds = collections.Counter(world.BIG_PROP_KIND_BY_ID[t] for row in GRID for t in row
                                if t in world.BIG_PROP_KIND_BY_ID)
    trees = sum(kinds[k] for k in big_props.TREE_KINDS)
    assert trees >= 300, kinds
    for want in ("oak", "pine", "jungle_giant", "snow_pine", "palm"):
        assert kinds[want] > 0, (want, kinds)
    tm = world.TileMap(GRID)
    checked = 0
    for y in range(2, H - 6):
        for x in range(2, W - 2):
            t = GRID[y][x]
            if t in world.BIG_TREE_IDS:
                assert tm.is_solid(x * C.TILE + 16, y * C.TILE + 16), "trunk tile must be solid"
                kind = world.BIG_PROP_KIND_BY_ID[t]
                assert big_props.footprint_tiles(kind, (x, y)) == [(x, y)], "a tree only blocks its trunk tile"
                checked += 1
                if checked > 50:
                    break
        if checked > 50:
            break
    # a 2x2 boulder blocks exactly its footprint
    fp = big_props.footprint_tiles("big_boulder", (10, 10))
    assert len(fp) == 4
    g = [[world.STONE] * 20 for _ in range(20)]
    assert world.can_place_big_prop(g, (10, 10), "big_boulder", {world.STONE})
    world.stamp_big_prop(g, (10, 10), "big_boulder")
    solid = {(x, y) for y in range(20) for x in range(20) if g[y][x] in world.SOLID}
    assert solid == set(fp), (solid, fp)
    # clear_blockers removes a whole big prop footprint around a 1x1 approach
    world.clear_blockers(g, pygame.Rect(10, 10, 1, 1), margin=2)
    assert not any(g[y][x] in world.BIG_PROP_ALL_IDS for y in range(20) for x in range(20))
    print(f"check_big_trees_solid_trunk_only: PASSED ({trees} big trees, {dict(kinds.most_common(4))})")


def check_canopy_overlay_draw():
    tm = world.TileMap(GRID)
    x, y = next((x, y) for y in range(H) for x in range(W) if GRID[y][x] in world.BIG_TREE_IDS)
    cam = world.Camera(400, 300)
    focus = pygame.Vector2(x * C.TILE + 16, (y - 1) * C.TILE)
    cam.follow(focus)
    tm.canopy_overlay = False
    tm.draw(screen, cam, screen.get_size())
    assert not tm._canopy_queue
    tm.canopy_overlay = True
    tm.draw(screen, cam, screen.get_size())
    assert tm._canopy_queue, "trees on screen queue their canopies"
    tm.draw_canopies(screen, cam, focus)   # faded canopy over the player - must not raise
    print("check_canopy_overlay_draw: PASSED")


def check_bosses_bigger():
    boss = Enemy("boss", (0, 0))
    assert boss.scale == BOSS_SCALE and boss.radius == round(ENEMY_KINDS["boss"]["radius"] * BOSS_SCALE)
    assert boss.radius >= 50, boss.radius
    base = sprites.enemy_sprite("boss")
    big = sprites.enemy_sprite("boss", boss.scale)
    assert big.get_width() == round(base.get_width() * BOSS_SCALE), (base.get_size(), big.get_size())
    for k in ("mad_god", "mad_god_phase2", "frost_monarch_phase2"):
        assert ENEMY_KINDS[k]["scale"] == BOSS_SCALE
    mini = Enemy("cinder_colossus", (0, 0))
    assert mini.scale == MINI_BOSS_SCALE
    assert sprites.enemy_sprite("goblin", 1.0) is sprites.enemy_sprite("goblin")
    # landmark guardians spawn 1.5x (sprite + hitbox)
    lm = next(l for l in SIM.landmarks if l["biome"] == "forest")
    saved = SIM.enemies
    SIM.enemies = []
    hero = Player("wizard", name="Big", pid="Big")
    hero.story = story.StoryProgress(1)
    hero.pos = pygame.Vector2(lm["pos"])
    SIM.begin_tick()
    SIM.update(0.01, {hero.pid: hero})
    g = next(e for e in SIM.enemies if getattr(e, "story_guardian", None) == "forest")
    assert g.scale == GUARDIAN_SCALE
    assert g.radius == int(round(ENEMY_KINDS[g.kind]["radius"] * GUARDIAN_SCALE))
    SIM.enemies = saved
    # a huge boss still moves through a 2-tile-wide corridor (movement radius is capped)
    corridor = [[world.ROCK] * 12 for _ in range(12)]
    for yy in range(12):
        corridor[yy][5] = corridor[yy][6] = world.GRASS
    cm = world.TileMap(corridor)
    boss.pos = pygame.Vector2(6 * C.TILE, 3 * C.TILE)
    boss._move(pygame.Vector2(0, 40), cm)
    assert boss.pos.y > 3 * C.TILE, "big boss got stuck in a corridor"
    snap = boss.net_state()
    assert snap["scale"] == BOSS_SCALE
    print(f"check_bosses_bigger: PASSED (boss r={boss.radius} sprite {big.get_size()}, guardian x{g.scale})")


def check_generation_budget():
    import time
    random.seed(11)
    t = time.time()
    RealmSim()
    dt = time.time() - t
    assert dt < 3.0, f"RealmSim() took {dt:.2f}s (budget 3.0s)"
    print(f"check_generation_budget: PASSED ({dt:.2f}s)")


if __name__ == "__main__":
    check_ten_big_areas()
    check_npcs_live_in_their_areas()
    check_nexus_enlarged_and_deterministic()
    check_big_trees_solid_trunk_only()
    check_canopy_overlay_draw()
    check_bosses_bigger()
    check_generation_budget()
    print("PASSED: areas / big trees / bigger bosses checks all green.")

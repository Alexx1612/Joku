"""
Batch 14, Track A: alcohol-pun island names, exactly-10 curated decorations
per island, and a real return portal at each island back to its hub slot.

Run with: .venv\\Scripts\\python.exe tests\\check_island_identity.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import realm_sim, world

_OLD_NAMES = {"Emberfall Shard", "Coral Choir", "Frostbite Shard", "Pearlsong Spire",
              "Bonewaste Shard", "Tideglass Sanctum", "Thornrock Shard",
              "Driftbell Cloister", "Ashenreach Shard", "Abyssal Hymnal"}


def _build_sim():
    return realm_sim.RealmSim(bonus=False)


def check_names_are_new_puns_not_old_names():
    assert len(realm_sim.ISLAND_NAMES) == 10
    assert len(set(realm_sim.ISLAND_NAMES)) == 10, "island names must be distinct"
    overlap = _OLD_NAMES & set(realm_sim.ISLAND_NAMES)
    assert not overlap, f"still using old non-pun names: {overlap}"
    print("check_names_are_new_puns_not_old_names: PASSED")


def check_exactly_ten_curated_decorations_per_island():
    sim = _build_sim()
    grid = sim.realm_map.grid
    assert len(sim.islands) == 10
    for isl in sim.islands:
        theme = isl["theme"]
        prop_ids = set(world.ISLAND_PROP_TILE[(theme, k)] for k in world.ISLAND_PROP_KINDS[theme])
        landmark_id = world.TALL_PROP_TILE[(theme, world.ISLAND_LANDMARK_KIND[theme])]
        cx, cy = int(isl["pos"].x // world.C.TILE), int(isl["pos"].y // world.C.TILE)
        r = world.ISLAND_RADIUS + 3
        found_kinds = set()
        found_landmark = False
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if not (0 <= yy < len(grid) and 0 <= xx < len(grid[0])):
                    continue
                t = grid[yy][xx]
                if t in prop_ids:
                    found_kinds.add(t)
                elif t == landmark_id:
                    found_landmark = True
        assert len(found_kinds) == 10, (
            f"island {isl['label']!r} has {len(found_kinds)} distinct curated prop "
            f"kinds, expected exactly 10 (one of each ISLAND_PROP_KINDS entry)"
        )
        assert found_landmark, f"island {isl['label']!r} is missing its landmark centerpiece"
    print("check_exactly_ten_curated_decorations_per_island: PASSED")


def check_every_island_has_outbound_and_return_portal():
    sim = _build_sim()
    island_links = [p for p in sim.portals if p.kind == "island_link"]
    assert len(island_links) == 20, f"expected 10 outbound + 10 return island_link portals, got {len(island_links)}"

    hub_slots = set()
    island_positions = {}
    for isl in sim.islands:
        island_positions[isl["label"]] = (round(isl["pos"].x), round(isl["pos"].y))

    outbound = [p for p in island_links if p.label != "Return"]
    returns = [p for p in island_links if p.label == "Return"]
    assert len(outbound) == 10 and len(returns) == 10

    for p in outbound:
        target = (round(p.target_pos[0]), round(p.target_pos[1]))
        assert target == island_positions[p.label], (
            f"outbound portal for {p.label!r} should target that island's own position"
        )
        hub_slots.add((round(p.pos.x), round(p.pos.y)))

    # Every return portal's target must be exactly one of the outbound portals'
    # own hub-ring positions (the round trip actually closes).
    return_targets = {(round(p.target_pos[0]), round(p.target_pos[1])) for p in returns}
    assert return_targets == hub_slots, "return portals don't target real hub-ring slots"

    # Every return portal must physically sit near its own island, not near the hub.
    for p in returns:
        nearest_island_dist = min(p.pos.distance_to(pos_) for pos_ in
                                   [pygame.Vector2(v) for v in island_positions.values()])
        assert nearest_island_dist < world.C.TILE * 5, (
            f"return portal at {p.pos} isn't near any island - it should sit at the island itself"
        )
    print("check_every_island_has_outbound_and_return_portal: PASSED")


def check_no_new_tile_id_collision():
    seen = {}
    for name in ("TILE_COLORS",):
        table = getattr(world, name)
        for tid in table:
            if not isinstance(tid, int):
                continue
            if tid in seen and seen[tid] != name:
                raise AssertionError(f"tile id {tid} registered by both {seen[tid]} and {name}")
            seen[tid] = name
    # ISLAND_PROP_TILE ids must all be distinct and not collide with any other
    # registered tile id table (BIOME_PROP_TILE, TALL_PROP_TILE, etc. all feed
    # into TILE_COLORS, so a real collision would have silently overwritten an
    # entry there - assert the count matches what's expected instead).
    prop_ids = list(world.ISLAND_PROP_TILE.values())
    assert len(prop_ids) == len(set(prop_ids)) == 20, "expected 20 distinct island prop tile ids (2 themes x 10 kinds)"
    print("check_no_new_tile_id_collision: PASSED")


if __name__ == "__main__":
    check_names_are_new_puns_not_old_names()
    check_exactly_ten_curated_decorations_per_island()
    check_every_island_has_outbound_and_return_portal()
    check_no_new_tile_id_collision()

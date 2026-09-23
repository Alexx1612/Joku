"""
Regression check for "The Reforging" (islands, 5-minute mini-quest, portal
hub + starting-area plaza) and the redesigned Nexus hallway/mirrored side
portals. Covers normal cases and the exact edge cases the user found live
(hub portals overlapping each other; no real starting area) plus a few more
(teleporting via a portal must never create a dungeon instance, in both
single-player and co-op).

Run with: .venv\\Scripts\\python.exe tests\\check_reforging_and_nexus.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import realm_sim, world, achievements
from game.entities import Player


def _fresh_sim():
    return realm_sim.RealmSim(bonus=False)


def check_islands_and_hub_placement():
    sim = _fresh_sim()
    assert len(sim.islands) >= 8, "expected most/all 10 islands to stamp"
    centers = [isl["pos"] for isl in sim.islands]
    min_sep = min(centers[i].distance_to(centers[j])
                  for i in range(len(centers)) for j in range(i + 1, len(centers)))
    assert min_sep > world.ISLAND_RADIUS * 32 * 1.5, "two islands landed too close together"
    for isl in sim.islands:
        assert sim.realm_map.tile_at(isl["pos"].x, isl["pos"].y) != world.WATER
        assert not sim.realm_map.is_solid(isl["pos"].x, isl["pos"].y)

    hub_portals = [pt for pt in sim.portals if pt.kind == "island_link"]
    assert len(hub_portals) == len(sim.islands)
    # the exact bug the user found in play: portals landing on top of each other
    min_portal_sep = min(hub_portals[i].pos.distance_to(hub_portals[j].pos)
                         for i in range(len(hub_portals)) for j in range(i + 1, len(hub_portals)))
    assert min_portal_sep > 60, f"hub portals are only {min_portal_sep:.0f}px apart - overlapping!"
    for pt in hub_portals:
        assert sim.realm_map.tile_at(pt.pos.x, pt.pos.y) != world.WATER
        assert not sim.realm_map.is_solid(pt.pos.x, pt.pos.y)
    print("check_islands_and_hub_placement: PASSED")


def check_starting_area_plaza():
    sim = _fresh_sim()
    anchor_tile = (int(sim._beach_spawn.x // 32), int(sim._beach_spawn.y // 32))
    plaza_ground = sim.realm_map.grid[anchor_tile[1]][anchor_tile[0]]
    assert plaza_ground != world.WATER
    markers = 0
    for dy in range(-world.REALM_START_RADIUS - 1, world.REALM_START_RADIUS + 2):
        for dx in range(-world.REALM_START_RADIUS - 1, world.REALM_START_RADIUS + 2):
            tx, ty = anchor_tile[0] + dx, anchor_tile[1] + dy
            if 0 <= ty < len(sim.realm_map.grid) and 0 <= tx < len(sim.realm_map.grid[0]):
                tid = sim.realm_map.grid[ty][tx]
                if tid in world.TALL_PROP_TILE_IDS:
                    markers += 1
    assert markers > 0, "expected a real starting-area plaza with marker props, not bare terrain"
    sp = sim.spawn_point()
    assert not sim.realm_map.is_solid(sp.x, sp.y), "spawn_point() must remain valid after plaza stamping"
    print("check_starting_area_plaza: PASSED")


def check_five_minute_wave_and_completion():
    sim = _fresh_sim()
    isl0 = sim.islands[0]
    isl0["cooldown"] = 0.1
    sim.begin_tick()
    for _ in range(20):
        sim.update(1 / 30, {})
    guardians = [e for e in sim.enemies if getattr(e, "island_idx", None) == 0]
    assert len(guardians) == realm_sim.ISLAND_WAVE_SIZE
    theme = realm_sim.ISLAND_THEMES[isl0["theme"]]
    assert any(e.kind == theme["anchor"] for e in guardians), "the anchor mob must always be in the wave"
    assert isl0["alive_guardians"] == realm_sim.ISLAND_WAVE_SIZE

    killer = Player("wizard", "Reforger", pid="p1")
    killer.pos = pygame.Vector2(isl0["pos"])
    bags_before = len(sim.ground_items)
    for g in list(guardians):
        sim._reward(g, killer)
        g.alive = False
    sim.enemies = [e for e in sim.enemies if e.alive]
    assert isl0["alive_guardians"] == 0
    assert isl0["cooldown"] == realm_sim.ISLAND_QUEST_INTERVAL, "cooldown should re-arm to a fresh 5 minutes"
    assert len(sim.ground_items) > bags_before, "completing an island event should drop loot"
    assert "reforger" in achievements.load("Reforger")

    # edge case: killing a normal (non-island) enemy must never touch island state
    normal_kill_isl_state = isl0["alive_guardians"], isl0["cooldown"]
    from game.entities import Enemy
    goblin = Enemy("goblin", (0, 0))
    sim._reward(goblin, killer)
    assert (isl0["alive_guardians"], isl0["cooldown"]) == normal_kill_isl_state
    print("check_five_minute_wave_and_completion: PASSED")


def check_island_link_teleport_single_player():
    import main as main_module
    sim = _fresh_sim()
    hub_portals = [pt for pt in sim.portals if pt.kind == "island_link"]
    game = main_module.Game.__new__(main_module.Game)
    game.player = Player("wizard", "Teleporter", pid="p1")
    game.player.pos = pygame.Vector2(hub_portals[0].pos)
    game.realm_sim = sim
    game.state = main_module.STATE_REALM
    game.bonus_sim = None
    target = hub_portals[0].target_pos
    game._portal_prompt = (game.enter_bonus_room, hub_portals[0].theme, hub_portals[0].kind,
                            hub_portals[0].difficulty, target)
    game._trigger_portal_prompt()
    assert game.player.pos.distance_to(pygame.Vector2(target)) < 1
    assert game.state == main_module.STATE_REALM, "island_link must never change state"
    assert game.bonus_sim is None, "island_link must never create a bonus sim"

    # edge case: an empty portal prompt must not crash
    game._portal_prompt = None
    game._trigger_portal_prompt()
    print("check_island_link_teleport_single_player: PASSED")


def check_island_link_teleport_coop_server():
    import server
    sim = _fresh_sim()
    state = server.ServerState()
    state.realm_sim = sim
    hub_portal = next(pt for pt in sim.portals if pt.kind == "island_link")
    sess = server.Session.__new__(server.Session)
    sess.pid = "p1"
    sess.player = Player("wizard", "CoopTeleporter", pid="p1")
    sess.player.pos = pygame.Vector2(hub_portal.pos)
    sess.zone = server.ZONE_REALM
    sess.bonus_sim_id = None
    sess.pre_bonus_pos = None
    sess.portal_prompt = (hub_portal.theme, hub_portal.kind, hub_portal.difficulty,
                          hub_portal.id, hub_portal.target_pos)
    state.sessions = {"p1": sess}
    server._apply_action(state, sess, {"action": "enter_portal"})
    assert sess.zone == server.ZONE_REALM
    assert sess.bonus_sim_id is None
    assert sess.player.pos.distance_to(pygame.Vector2(hub_portal.target_pos)) < 1
    assert len(state.bonus_sims) == 0, "island_link must never create a bonus_sim server-side"
    print("check_island_link_teleport_coop_server: PASSED")


def check_nexus_hallway_and_mirrored_portals():
    g = world.make_nexus()
    gh, gw = len(g), len(g[0])
    vault_positions = [(x, y) for y in range(gh) for x in range(gw) if g[y][x] == world.VAULT_TILE]
    bazaar_positions = [(x, y) for y in range(gh) for x in range(gw) if g[y][x] == world.BAZAAR_PORTAL]
    portal_positions = [(x, y) for y in range(gh) for x in range(gw) if g[y][x] == world.PORTAL]
    assert len(vault_positions) == 1 and len(bazaar_positions) == 1 and len(portal_positions) == 1
    vx, vy = vault_positions[0]
    bx, by = bazaar_positions[0]
    px, _py = portal_positions[0]
    assert vy == by, "vault and bazaar should be mirrored at the same hallway row"
    assert abs(vx - px) == abs(bx - px), "vault and bazaar should be symmetric distances from center"
    tm = world.TileMap(g)
    assert not tm.is_solid(vx * 32 + 16, vy * 32 + 16)
    assert not tm.is_solid(bx * 32 + 16, by * 32 + 16)
    print("check_nexus_hallway_and_mirrored_portals: PASSED")


if __name__ == "__main__":
    check_islands_and_hub_placement()
    check_starting_area_plaza()
    check_five_minute_wave_and_completion()
    check_island_link_teleport_single_player()
    check_island_link_teleport_coop_server()
    check_nexus_hallway_and_mirrored_portals()
    print("PASSED: Reforging + Nexus checks all green.")

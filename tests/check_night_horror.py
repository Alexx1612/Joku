"""
Night-horror update: the cycle, the time bar, darkness + Luminosity, light sources,
fireflies, safe houses and doors (single-player and co-op).

Later steps (night aggression, events, night mobs, the Blood Moon horde) add their
own checks below.

Run with: .venv\\Scripts\\python.exe tests\\check_night_horror.py
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((1366, 820))

from game import accounts, characters, achievements
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_night_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_night_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_night_ach_")

from game import realm_sim as rs, ui, world, settings, options_menu, audio
from game.realm_sim import RealmSim
from game.entities import Player, Enemy, GLOWING_KINDS
from game.constants import TILE

SHOT_DIR = os.environ.get("RR_SHOT_DIR")
random.seed(5)
SIM = RealmSim()


def check_ten_minute_cycle_four_minute_night():
    assert rs.DAY_LENGTH == 600
    night = sum(1 for t in range(600) if rs.day_light_at(t + 0.5) < 0.5)
    assert 230 <= night <= 250, night
    assert rs.day_light_at(100) == 1.0 and rs.day_light_at(450) == 0.0
    assert rs.day_phase_at(310) == "dusk" and rs.day_phase_at(560) == "dawn" and rs.day_phase_at(590) == "day"
    sim = RealmSim(bonus=True, theme="cave", difficulty_name="Easy")
    assert sim.light_level == 1.0 and sim.phase() == "day"  # dungeons have no night
    # a Blood Moon night runs faster: 3 minutes of darkness instead of 4
    for blood, want in ((False, 240), (True, 180)):
        SIM.day_time, SIM.blood_moon_active, SIM._was_night = rs.NIGHTFALL_T + 0.01, blood, True
        t = 0.0
        while SIM.is_night and t < 400:
            SIM._update_day_night(0.25)
            SIM.blood_moon_active = blood
            t += 0.25
        assert abs(t - want) <= 2, (blood, t)
    print("check_ten_minute_cycle_four_minute_night: PASSED")


def check_clock_countdown_and_time_bar():
    SIM.blood_moon_active = False
    SIM.day_time = 270
    c = SIM.clock_info()
    assert c["until"] == "night" and abs(c["left"] - 45) < 0.2 and c["phase"] == "day"
    SIM.day_time = 400
    c = SIM.clock_info()
    assert c["until"] == "dawn" and abs(c["left"] - 155) < 0.5 and c["night"], c
    SIM.blood_moon_active = True
    assert SIM.clock_info()["left"] < c["left"], "the Blood Moon night ends sooner"
    for t, blood in ((100, False), (318, False), (400, False), (400, True), (580, False)):
        SIM.day_time, SIM.blood_moon_active = t, blood
        screen.fill((40, 60, 40))
        ui.draw_day_night_clock(screen, SIM.light_level, blood, clock=SIM.clock_info())
        ui.draw_night_countdown(screen, SIM.clock_info())
    r = ui.day_night_clock_rect()
    assert screen.get_rect().contains(r)
    if SHOT_DIR:
        pygame.image.save(screen, os.path.join(SHOT_DIR, "night_clock.png"))
    print("check_clock_countdown_and_time_bar: PASSED")


def _dark_at(lum, light_level=0.0):
    surf = pygame.Surface((400, 300)).convert_alpha()
    surf.fill((255, 255, 255, 255))
    ui.draw_day_night_overlay(surf, light_level, luminosity=lum, player_screen=(50, 50))
    return sum(surf.get_at((350, 250))[:3])


def check_luminosity_setting():
    assert settings.DEFAULTS["luminosity"] == 0.5
    assert any(r.label.startswith("Luminosity") for r in options_menu.build_rows(
        lambda: False, lambda v: None, lambda: False, lambda: None, lambda: None, lambda: None))
    pitch, default, clear = _dark_at(0.0), _dark_at(0.5), _dark_at(1.0)
    assert pitch < default < clear, (pitch, default, clear)
    assert pitch <= 40 and clear > 600, (pitch, clear)  # 0% = the night tint itself, fully opaque
    assert 0.17 <= default / 765 <= 0.27, default / 765  # ~79% black at the default
    assert _dark_at(0.5, light_level=1.0) == 765, "daytime is never darkened"
    # the player's light follows the player's REAL screen position
    surf = pygame.Surface((400, 300)).convert_alpha()
    surf.fill((255, 255, 255, 255))
    ui.draw_day_night_overlay(surf, 0.0, luminosity=0.5, player_screen=(50, 50))
    assert sum(surf.get_at((50, 50))[:3]) > sum(surf.get_at((200, 150))[:3])
    print("check_luminosity_setting: PASSED")


def check_light_sources():
    world._build_light_tiles()
    lamp = [tid for tid, kind in world.BIG_PROP_KIND_BY_ID.items() if kind == "lamp_post"]
    assert lamp and all(t in world.LIGHT_TILE_INFO for t in lamp)
    area = next(a for a in SIM.areas if a["key"] == "tavern_town")
    c = pygame.Vector2(area["rect"].centerx * TILE, area["rect"].centery * TILE)
    lights = SIM.light_sources_near(c, 30)
    assert lights, "a town has lamps / campfires that light the night"
    SIM.lanterns_out = True
    assert not world.nearby_lights(SIM.realm_map, c.x, c.y, 30, lit=False)
    SIM.lanterns_out = False
    # a light really cuts the darkness where it stands
    surf = pygame.Surface((400, 300)).convert_alpha()
    surf.fill((255, 255, 255, 255))
    ui.draw_day_night_overlay(surf, 0.0, luminosity=0.5, player_screen=(-500, -500), lights=[(300, 200, 90, (255, 200, 120))])
    assert sum(surf.get_at((300, 200))[:3]) > sum(surf.get_at((60, 60))[:3]) + 300
    ui.draw_light_glows(surf, [(300, 200, 90, (255, 200, 120))], 0.0)
    for kind in ("fireflies", "cave_moth", "fire_beetle", "mushroom_folk", "cinder_wisp"):
        assert kind in GLOWING_KINDS
    print("check_light_sources: PASSED")


def check_fireflies_come_out_at_night_only():
    p = Player("wizard", "Watcher", pid="w")
    forest = [(x, y) for y in range(300, 1200, 7) for x in range(300, 1200, 7)
              if SIM.realm_map.grid[y][x] == world.GRASS]
    tx, ty = forest[len(forest) // 2]
    p.pos = pygame.Vector2(tx * TILE, ty * TILE)
    SIM.enemies = []
    SIM.day_time, SIM.blood_moon_active = 400, False
    SIM._night_cd = 0
    for _ in range(40):
        SIM._night_cd = 0
        SIM._tick_night_creatures(0.1, [p])
    flies = [e for e in SIM.enemies if e.kind == "fireflies"]
    assert flies and all(e.neutral for e in flies), len(flies)
    SIM.day_time = 100
    SIM._tick_night_creatures(0.1, [p])
    assert not any(e.kind == "fireflies" and e.alive for e in SIM.enemies), "they fade at dawn"
    print(f"check_fireflies_come_out_at_night_only: PASSED ({len(flies)} swarms)")


def check_safe_houses_and_doors():
    houses = SIM.safe_houses
    shacks = [h for h in houses if h["label"] == "a wayside shack"]
    assert len(houses) >= 25 and len(shacks) >= 15, (len(houses), len(shacks))
    grid = SIM.realm_map.grid
    h = shacks[0]
    dx, dy = h["doors"][0]
    assert all(grid[y][x] == world.DOOR_OPEN for x, y in h["doors"]), "doors start open"
    door_pos = ((dx + 0.5) * TILE, (dy + 0.5) * TILE)
    assert not SIM.is_solid(*door_pos) and SIM.enemy_view.is_solid(*door_pos), "players pass, mobs never"
    p = Player("warrior", "Hider", pid="h")
    p.pos = pygame.Vector2((dx + 0.5) * TILE, (dy - 0.5) * TILE)
    SIM._story_players = [p]
    assert SIM.toggle_door_near(p)
    assert all(grid[y][x] == world.DOOR_CLOSED for x, y in h["doors"])
    assert SIM.is_solid(*door_pos), "a closed door is a wall for players too"
    assert any(ev[0] == "sfx" and ev[1] == "door_close" for ev in SIM.sound_events)
    # inside + doors shut = sheltered: a mob right outside can't target you
    SIM.enemies = []
    gob = Enemy("goblin", pygame.Vector2((dx + 0.5) * TILE, (dy + 4) * TILE))
    gob.aggro = True
    SIM.enemies = [gob]
    SIM.day_time = 400
    hp0 = p.hp = p.hp_max // 2
    for _ in range(90):
        SIM.begin_tick()
        SIM.update(1 / 30, {p.pid: p})
    assert p.sheltered and not gob.aggro and p.hp > hp0
    # someone in the doorway blocks closing; reopening works
    assert SIM.toggle_door_near(p)
    assert all(grid[y][x] == world.DOOR_OPEN for x, y in h["doors"])
    SIM.begin_tick()
    SIM.update(1 / 30, {p.pid: p})
    assert not p.sheltered
    q = Player("archer", "Doorway", pid="q")
    q.pos = pygame.Vector2(door_pos)
    SIM._story_players = [p, q]
    SIM.toggle_door_near(p)
    assert all(grid[y][x] == world.DOOR_OPEN for x, y in h["doors"]), "not onto someone's toes"
    for key in ("door_open", "door_close"):
        assert key in audio.EVENT_SOUND
    print(f"check_safe_houses_and_doors: PASSED ({len(houses)} houses, {len(shacks)} wayside shacks)")


def check_coop_doors_and_clock():
    import server

    class FakeSock:
        def sendall(self, data):
            pass

    state = server.ServerState()
    state.realm_sim = SIM
    p = Player("warrior", name="CoopDoor", pid="d1")
    s = server.Session("d1", FakeSock(), p)
    state.sessions[s.pid] = s
    s.zone = server.ZONE_REALM
    h = next(h for h in SIM.safe_houses if h["label"] == "a wayside shack")
    dx, dy = h["doors"][0]
    p.pos = pygame.Vector2((dx + 0.5) * TILE, (dy - 0.5) * TILE)
    SIM._story_players = [p]  # nobody else in the doorway
    before = [d for d in SIM.door_states() if (d[0], d[1]) == (dx, dy)][0][2]
    server._apply_action(state, s, {"action": "fish"})  # F
    after = [d for d in SIM.door_states() if (d[0], d[1]) == (dx, dy)][0][2]
    assert before != after, "F next to a door toggles it in co-op too"
    snap = server._snapshot_for(state, s)
    assert snap["clock"]["until"] in ("night", "dawn") and snap["doors"]
    print("check_coop_doors_and_clock: PASSED")


if __name__ == "__main__":
    check_ten_minute_cycle_four_minute_night()
    check_clock_countdown_and_time_bar()
    check_luminosity_setting()
    check_light_sources()
    check_fireflies_come_out_at_night_only()
    check_safe_houses_and_doors()
    check_coop_doors_and_clock()
    print("PASSED: night horror checks all green.")

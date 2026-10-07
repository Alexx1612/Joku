"""
Night realism pass 2 (game/night_sky.py + game/sky_fx.py): night weather (cloudy / rain / storm
with lightning), shooting stars and fallen Star Fragments, night-blooming herbs gathered with F,
owls that fly off when you come close, frost sparkle, and the golden-hour sun sweeping west to
east across the screen at dusk and dawn.

Run with: .venv\\Scripts\\python.exe tests\\check_night_sky.py
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
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_sky_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_sky_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_sky_ach_")

from game import realm_sim as rs, night_sky as NS, sky_fx, lighting, audio, ui, world, items as I, npcs
from game.realm_sim import RealmSim
from game.entities import Player, Enemy, GLOWING_KINDS
from game.constants import TILE

random.seed(9)
SIM = RealmSim()


def _player(pid="s1"):
    p = Player("warrior", "Sky", pid=pid)
    p.pos = SIM.spawn_point()
    p.hp = p.hp_max = 10 ** 6
    return p


def _nightfall(weather, p):
    old = NS.NIGHT_WEATHER
    NS.NIGHT_WEATHER = ((weather, 1),)
    old_bm = rs.BLOOD_MOON_CHANCE
    rs.BLOOD_MOON_CHANCE = 0.0
    try:
        SIM.blood_moon_active = False
        SIM._nights_since_blood_moon = 0
        SIM.day_time, SIM._was_night = rs.NIGHTFALL_T - 0.05, False
        SIM.night._was_night = False
        SIM.sky._was_night = False
        for _ in range(4):
            SIM.begin_tick()
            SIM.update(1 / 20, {p.pid: p})
    finally:
        NS.NIGHT_WEATHER = old
        rs.BLOOD_MOON_CHANCE = old_bm
    assert SIM.is_night and SIM.sky.weather == weather, (SIM.sky.weather, SIM.is_night)


def check_golden_hour_sweeps_west_to_east():
    xs = []
    for t in (rs.DUSK_START - 70, rs.DUSK_START - 20, rs.NIGHT_START - 5):
        SIM.day_time = t
        xs.append(SIM.sky_grade()["sun_x"])
    assert xs[0] < xs[1] < xs[2], xs
    dawn = []
    for t in (rs.NIGHT_END + 5, rs.DAWN_END + 20, rs.DAWN_END + 70):
        SIM.day_time = t
        dawn.append(SIM.sky_grade()["sun_x"])
    assert dawn[0] < dawn[1] < dawn[2], dawn
    # the glow covers the whole screen (every edge gets warmer), brightest near the sun
    SIM.day_time = rs.DUSK_START - 20
    clock = SIM.clock_info()
    base = pygame.Surface((800, 500))
    base.fill((60, 60, 60))
    glow = base.copy()
    ui.draw_sky_grade(glow, clock, 1.0)
    for pt in ((5, 5), (795, 5), (5, 495), (795, 495), (400, 250)):
        assert glow.get_at(pt)[0] > base.get_at(pt)[0], pt
    hot = int(clock["sun_x"] * 800)
    far = hot + 300 if hot < 400 else hot - 300  # away from the sun, but inside the warm rim
    assert glow.get_at((hot, 210))[0] > glow.get_at((far, 210))[0], "the hotspot follows the sun"
    print(f"check_golden_hour_sweeps_west_to_east: PASSED (dusk {xs}, dawn {dawn})")


def check_night_weather():
    p = _player()
    for w in ("clear", "cloudy", "rain", "storm"):
        _nightfall(w, p)
        c = SIM.clock_info()
        assert c["sky"] == w and c["sky_dark"] == NS.CLOUD_DARK[w]
        if w != "clear":
            assert c["moon"] < 0, "clouds hide the moon"
        if w in NS.WEATHER_LIGHT_MULT:
            assert c["light_mult"] < 1.0
    # darker ambient under clouds
    lighting.set_grade({"sky_dark": 1.0})
    clear = sum(lighting.ambient_color(0.0, 0.5, False))
    lighting.set_grade({"sky_dark": NS.CLOUD_DARK["storm"]})
    storm = sum(lighting.ambient_color(0.0, 0.5, False))
    lighting.set_grade({})
    assert storm < clear
    # rain everywhere it can rain on a rainy night
    fx = sky_fx.SkyFX()
    assert fx.rain_kind({"sky": "rain"}, None) == "rain" and fx.rain_kind({"sky": "rain"}, "snow") == "snow"
    assert fx.rain_kind({"sky": "clear"}, None) is None
    # dawn clears it
    SIM.day_time = 100
    SIM.begin_tick()
    SIM.update(1 / 20, {p.pid: p})
    assert SIM.sky.weather == "clear"
    print("check_night_weather: PASSED")


def check_storm_lightning_flash():
    p = _player()
    _nightfall("storm", p)
    SIM.sky._bolt_cd = 0
    fx = sky_fx.SkyFX()
    fx.update(0.01, SIM.clock_info())  # first sight of the clock just records the sequence
    SIM.sound_events.clear()
    SIM.begin_tick()
    SIM.update(1 / 20, {p.pid: p})
    c = SIM.clock_info()
    assert c["bolt"] and any(ev[1] == "thunder" for ev in SIM.sound_events if ev[0] == "sfx")
    fx.update(0.01, c)
    assert fx.flash > 0.9 and fx.light_boost(0.0) > 0.8, "lightning lights everything up"
    surf = pygame.Surface((1000, 700))
    fx.draw(surf, lambda v: (int(v[0] - p.pos.x + 500), int(v[1] - p.pos.y + 350)))
    for _ in range(60):
        fx.update(1 / 60, c)
    assert fx.flash == 0.0 and fx.light_boost(0.0) == 0.0, "and fades back to dark"
    print("check_storm_lightning_flash: PASSED")


def check_shooting_stars_and_fragments():
    p = _player()
    _nightfall("clear", p)
    old = NS.STAR_CHANCE, NS.STAR_FALL_CHANCE
    NS.STAR_CHANCE, NS.STAR_FALL_CHANCE = 1.0, 1.0
    try:
        SIM.sky.fallen = []
        SIM.sky._star_cd = 0
        SIM.events.clear()
        SIM.begin_tick()
        SIM.update(1 / 20, {p.pid: p})
    finally:
        NS.STAR_CHANCE, NS.STAR_FALL_CHANCE = old
    c = SIM.clock_info()
    assert c["star"] and c["star"][2] == 1
    assert SIM.sky.fallen, "a star fell"
    f = SIM.sky.fallen[0]
    assert any("shooting star" in ev[1] for ev in SIM.events)
    lights = SIM.light_sources_near(f["pos"], 4)
    assert any(abs(l[0] - f["pos"].x) < 1 and l[3] == NS.STAR_LIGHT[1] for l in lights), "it glows"
    frag = f["bag"].items[0]
    assert frag.name == "Star Fragment"
    fx = sky_fx.SkyFX()
    fx._star_seq = c["star"][0] - 1
    fx.update(0.3, c)
    fx.draw(screen, lambda v: (0, 0))
    # using it: lucky until it wears off
    p.backpack = [frag]
    assert p.use_potion(0) and "luck" in p.temp_buffs
    f["bag"].items.clear()
    assert not SIM.sky.lights(), "picked up: the glow is gone"
    print("check_shooting_stars_and_fragments: PASSED")


def check_luck_gives_extra_loot():
    random.seed(4)
    p = _player("lk")
    p.temp_buffs = {"luck": (1, 200.0)}
    old = rs.STAR_LUCK_CHANCE
    rs.STAR_LUCK_CHANCE = 1.0
    calls = []
    real = rs.roll_loot
    rs.roll_loot = lambda *a, **k: calls.append(1) or []
    try:
        e = Enemy("goblin", p.pos + pygame.Vector2(200, 0))
        e.damaged_by = {p.pid} if hasattr(e, "damaged_by") else None
        SIM._reward(e, p)
    finally:
        rs.roll_loot = real
        rs.STAR_LUCK_CHANCE = old
    assert len(calls) >= 2, calls
    print("check_luck_gives_extra_loot: PASSED")


def check_herbs_bloom_at_night_and_are_picked():
    p = _player("hb")
    _nightfall("clear", p)
    SIM.enemies = []
    for _ in range(40):
        SIM.sky._spawn_herbs([p])
        p.pos = SIM._find_spawn_pos_near(SIM.spawn_point(), 0, 60 * TILE) or p.pos
    herbs = [e for e in SIM.enemies if e.kind in NS.HERB_GROUNDS]
    assert herbs, "herbs bloom"
    for e in herbs:
        assert SIM._biome_at(e.pos) in NS.HERB_GROUNDS[e.kind]
        assert e.kind in GLOWING_KINDS
    h = herbs[0]
    assert npcs.nearest_wildlife(SIM.enemies, h.pos) is None or npcs.nearest_wildlife(SIM.enemies, h.pos).kind \
        not in NS.HERB_GROUNDS, "herbs aren't chatted to"
    p.pos = pygame.Vector2(h.pos) + pygame.Vector2(10, 0)
    p.backpack = []
    assert SIM.sky.gather_herb(p)
    it = p.backpack[0]
    assert it.name in ("Moonpetal", "Ghostbloom") and h not in SIM.enemies
    p.hp = p.hp_max // 2
    hp0 = p.hp
    assert p.use_potion(0) and p.hp > hp0
    if it.name == "Moonpetal":
        assert "glow" in p.temp_buffs
    assert not SIM.sky.gather_herb(p), "nothing left to pick here"
    ui._tooltip(screen, (100, 100), I.make_moonpetal())
    for shape in ("herb_moonpetal", "herb_ghostbloom", "star_fragment"):
        from game import sprites
        assert sprites.item_icon((255, 255, 255), shape).get_bounding_rect().w > 8, shape
    # daylight: they're gone
    SIM.day_time = 100
    SIM.begin_tick()
    SIM.update(1 / 20, {p.pid: p})
    assert not [e for e in SIM.enemies if e.kind in NS.HERB_GROUNDS and e.alive]
    print(f"check_herbs_bloom_at_night_and_are_picked: PASSED ({sorted({e.kind for e in herbs})})")


def check_owls():
    p = _player("ow")
    _nightfall("clear", p)
    owl = Enemy("owl", p.pos + pygame.Vector2(400, 0))
    SIM.enemies = [owl]
    SIM.sky._tick_owls(0.1, [p])
    assert owl.alive and getattr(owl, "_flying", None) is None, "perched while you're far"
    p.pos = owl.pos + pygame.Vector2(60, 0)
    SIM.sky._tick_owls(0.05, [p])
    assert owl._flying is not None
    start = pygame.Vector2(owl.pos)
    for _ in range(80):
        SIM.sky._tick_owls(0.05, [p])
    assert not owl.alive and start.distance_to(p.pos) < owl.pos.distance_to(p.pos), "flew off, away from you"
    owl2 = Enemy("owl", p.pos)
    owl2.draw(screen, lambda v: (300, 300))
    print("check_owls: PASSED")


def check_frost_sparkle_and_sounds():
    surf = pygame.Surface((800, 600))
    sky_fx.SkyFX.draw_frost_sparkle(surf, lambda v: (int(v[0]) % 800, int(v[1]) % 600), (0, 0),
                                    lambda x, y: world.SNOW, (world.SNOW, world.ICE), 0.0)
    for k in ("thunder", "rain_start", "rain_patter", "shooting_star", "owl_flap", "herb_pick"):
        assert k in audio.EVENT_SOUND, k
        audio.play_event(k)
    audio.night_ambience(2.0, {"phase": "night", "night": True, "sky": "storm"})
    print("check_frost_sparkle_and_sounds: PASSED")


def check_coop_clock_carries_the_sky():
    import json
    c = SIM.clock_info()
    back = json.loads(json.dumps(c))
    for k in ("sky", "bolt", "star", "sky_dark", "sun_x"):
        assert k in back, k
    print("check_coop_clock_carries_the_sky: PASSED")


if __name__ == "__main__":
    check_golden_hour_sweeps_west_to_east()
    check_night_weather()
    check_storm_lightning_flash()
    check_shooting_stars_and_fragments()
    check_luck_gives_extra_loot()
    check_herbs_bloom_at_night_and_are_picked()
    check_owls()
    check_frost_sparkle_and_sounds()
    check_coop_clock_carries_the_sky()
    print("\nALL NIGHT SKY CHECKS PASSED")

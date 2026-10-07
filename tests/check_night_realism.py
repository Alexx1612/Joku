"""
Night realism pass + the Light of RDV: golden / blue hour, moon phases, dawn mist, window
glow, sleeping day animals, town folk going indoors, eye adaptation, night ambience, the
Lamplighter event and its reward ring (more vision, scares monsters), and mobs never
spawning on top of a player.

Run with: .venv\\Scripts\\python.exe tests\\check_night_realism.py
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
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_real_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_real_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_real_ach_")

from game import realm_sim as rs, ui, lighting, eyes, audio, items as I
from game import night as night_mod
from game.realm_sim import RealmSim
from game.entities import Player, Enemy
from game.constants import TILE

random.seed(7)
SIM = RealmSim()


def _player(pid="r1"):
    p = Player("warrior", "Wick", pid=pid)
    p.pos = SIM.spawn_point()
    p.hp = p.hp_max = 10 ** 6
    return p


def check_golden_blue_hour_and_moon():
    SIM.blood_moon_active = False
    SIM.day_time = 100
    g = SIM.sky_grade()
    assert g["tint"] == [1.0, 1.0, 1.0] and g["sun"] == 0
    SIM.day_time = rs.DUSK_START - 20
    g = SIM.sky_grade()
    assert g["sun"] > 0.3 and g["sun_side"] == "west" and g["tint"][2] < g["tint"][0], g  # warm
    SIM.day_time = rs.NIGHT_START + 5
    g = SIM.sky_grade()
    assert g["tint"][2] > g["tint"][0], g  # blue hour: cool
    SIM.day_time = rs.DAWN_END - 5
    assert SIM.sky_grade()["mist"] > 0.8 and SIM.sky_grade()["sun_side"] == "east"
    # moon phases: the full moon lights the night, the new moon leaves it darker
    SIM.day_time = 420
    SIM.night_count = 4
    full = SIM.sky_grade()
    SIM.night_count = 0
    new = SIM.sky_grade()
    assert full["moon_phase"] == 4 and new["moon_phase"] == 0 and full["moon"] > 0 > new["moon"]
    lighting.set_grade(full)
    a_full = sum(lighting.ambient_color(0.0, 0.5, False))
    lighting.set_grade(new)
    a_new = sum(lighting.ambient_color(0.0, 0.5, False))
    lighting.set_grade({})
    assert a_full > a_new, (a_full, a_new)
    c = SIM.clock_info()
    assert "moon_phase" in c and c.get("house_lights"), "windows glow at night"
    # draws without crashing
    for t in (100, rs.DUSK_START - 20, rs.NIGHT_START + 5, 420, rs.DAWN_END - 5):
        SIM.day_time = t
        clock = SIM.clock_info()
        ui.draw_sky_grade(screen, clock, SIM.light_level)
        ui.draw_dawn_mist(screen, clock)
        ui.draw_day_night_clock(screen, SIM.light_level, False, clock=clock)
    print("check_golden_blue_hour_and_moon: PASSED")


def check_full_moon_raises_blood_moon_chance():
    assert rs.FULL_MOON_BLOOD_MULT > 1
    print("check_full_moon_raises_blood_moon_chance: PASSED")


def check_house_window_lights():
    pts = SIM.house_light_points()
    assert pts
    SIM.day_time = 420
    hx, hy = pts[0]
    near = SIM.light_sources_near(pygame.Vector2(hx, hy), 4)
    assert any(abs(l[0] - hx) < 1 and abs(l[1] - hy) < 1 for l in near), "a window light at night"
    SIM.day_time = 100
    near = SIM.light_sources_near(pygame.Vector2(hx, hy), 4)
    assert not any(abs(l[0] - hx) < 1 and abs(l[1] - hy) < 1 for l in near), "no window light by day"
    print("check_house_window_lights: PASSED")


def check_day_animals_sleep_and_folk_go_inside():
    p = _player()
    SIM.enemies = []
    kind = rs.DIURNAL_WILDLIFE[0]
    a = Enemy(kind, p.pos + pygame.Vector2(600, 0))
    SIM.enemies.append(a)
    SIM.day_time = 420
    SIM.begin_tick()
    SIM.update(1 / 20, {p.pid: p})
    assert getattr(a, "_asleep", False) and a.net_state()["zz"], kind
    a.draw(screen, lambda v: (int(v.x - a.pos.x + 300), int(v.y - a.pos.y + 300)))
    folk = [n for n in SIM.npcs if hasattr(n, "day_home")]
    assert folk and any(n.home != n.day_home for n in folk), "town folk head indoors"
    SIM.day_time = 100
    SIM.begin_tick()
    SIM.update(1 / 20, {p.pid: p})
    assert not a._asleep
    assert all(n.home == n.day_home for n in folk), "and come back out by day"
    print(f"check_day_animals_sleep_and_folk_go_inside: PASSED ({len(folk)} folk)")


def check_eye_adaptation():
    e = eyes.EyeAdaptation()
    assert e.update(0.1, False, False) == 1.0
    lvl = e.update(0.1, True, False)
    assert lvl < 0.7, lvl
    for _ in range(300):
        lvl = e.update(0.1, True, False)
    assert lvl == 1.0
    for _ in range(40):
        e.update(0.1, True, True)
    assert e.update(0.1, True, False) < 0.8, "dazzled after stepping out of a bright light"
    print("check_eye_adaptation: PASSED")


def check_ambience_sounds():
    for ev in night_mod.EVENTS:  # every night event has its announcement sound
        assert f"night_{ev}" in audio.EVENT_SOUND, ev
    for k in ("crickets", "owl", "howl", "dawn_chorus"):
        assert k in audio.EVENT_SOUND, k
        audio.play_event(k)
    audio.night_ambience(5.0, {"phase": "night", "night": True, "blood": True})
    audio.night_ambience(0.1, {"phase": "dawn", "night": False})
    print("check_ambience_sounds: PASSED")


def check_rdv_ring():
    r = I.make_rdv_ring()
    assert r.slot == "ring" and r.aura == "rdv" and r.is_ut and r.name == "Light of RDV"
    back = I.Item.from_json(r.to_json()) if hasattr(I.Item, "from_json") else None
    if back is not None:
        assert back.aura == "rdv"
    assert I.RDV_VISION > 1.2
    p = _player()
    p.ring = r
    SIM.day_time = 420
    SIM.enemies = []
    gob = Enemy("goblin", p.pos + pygame.Vector2(120, 0))
    gob.aggro = True
    SIM.enemies.append(gob)
    d0 = gob.pos.distance_to(p.pos)
    assert SIM._rdv_scared(gob, [p]) and not gob.aggro
    for _ in range(20):
        SIM._rdv_scared(gob, [p])
    assert gob.pos.distance_to(p.pos) >= d0, "it backs away"
    p.ring = None
    assert not SIM._rdv_scared(gob, [p])
    print("check_rdv_ring: PASSED")


def check_lamplighter_event():
    def start():
        random.seed(11)
        SIM.enemies, SIM.bullets = [], []
        p = _player("lw")
        p.backpack = []
        SIM.night.ward = None
        SIM.night._start_lamplighter()
        w = SIM.night.ward
        p.pos = pygame.Vector2(w["npc"].pos) + pygame.Vector2(60, 0)
        SIM.night._tick_lamplighter(0.05, [p])
        return p, w

    p, w = start()
    assert any(n.npc_id == "lamplighter" for n in SIM.npcs) and p.pid in w["helpers"]
    assert w["npc"].net_state().get("hpf") is not None
    w["wave_cd"] = 0
    SIM.night._tick_lamplighter(0.05, [p])
    assert any(getattr(e, "ward_target", False) for e in SIM.enemies), "the dark sends a wave"
    SIM.night._finish_lamplighter([p])
    got = [it for it in list(p.backpack) + list(getattr(p, "backpack2", [])) if it and it.aura == "rdv"]
    assert got, "protect him until dawn: the Light of RDV"
    assert not any(n.npc_id == "lamplighter" for n in SIM.npcs)
    # if he dies, nobody gets a ring
    p, w = start()
    w["hp"] = 1
    SIM.enemies = [Enemy("goblin", pygame.Vector2(w["npc"].pos))]
    SIM.night._tick_lamplighter(0.5, [p])
    assert w["hp"] <= 0
    SIM.night._finish_lamplighter([p])
    assert not [it for it in p.backpack if it and it.aura == "rdv"]
    assert "lamplighter" in night_mod.EVENTS
    print("check_lamplighter_event: PASSED")


def check_mobs_never_spawn_on_top_of_you():
    p = _player()
    SIM.day_time = 420
    closest = 10 ** 9
    for _ in range(60):
        pos = SIM._find_spawn_pos_near(p.pos, 6 * TILE, 24 * TILE, avoid_players=[p])
        if pos is not None:
            closest = min(closest, pygame.Vector2(pos).distance_to(p.pos))
    assert closest >= rs.MIN_SPAWN_DIST_FROM_PLAYER - 1, closest
    print(f"check_mobs_never_spawn_on_top_of_you: PASSED (closest {closest:.0f}px)")


if __name__ == "__main__":
    check_golden_blue_hour_and_moon()
    check_full_moon_raises_blood_moon_chance()
    check_house_window_lights()
    check_day_animals_sleep_and_folk_go_inside()
    check_eye_adaptation()
    check_ambience_sounds()
    check_rdv_ring()
    check_lamplighter_event()
    check_mobs_never_spawn_on_top_of_you()
    print("\nALL NIGHT REALISM CHECKS PASSED")

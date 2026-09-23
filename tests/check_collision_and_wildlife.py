"""
Regression check for ambient-wildlife collision/behavior: unshootable bullets,
shoot-near-it-and-it-flees, walk-into-it-and-it-gets-pushed-and-glides, and
peaceful-mob dialogue (both the flavor-line CONTENT and the sound family it's
tagged with). Covers normal cases and a few edge cases (totem must never be
pushed or speak; normal combat mobs must be completely unaffected).

Run with: .venv\\Scripts\\python.exe tests\\check_collision_and_wildlife.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import realm_sim
from game.entities import Enemy, Bullet, Player, WILDLIFE_FLAVOR_LINES, MOB_FLAVOR_LINES
from game.audio import sound_family

WILDLIFE_KINDS = ("forest_hare", "cave_moth", "songbird", "deer", "desert_lizard", "marsh_heron")


def check_unshootable():
    for kind in WILDLIFE_KINDS:
        e = Enemy(kind, (0, 0))
        assert e.unshootable, f"{kind} should be unshootable"
    combat = Enemy("goblin", (0, 0))
    assert not combat.unshootable
    totem = Enemy("totem", (0, 0))
    assert not totem.unshootable, "totem must stay shootable (kill_totems secret quest)"
    sim = realm_sim.RealmSim.__new__(realm_sim.RealmSim)
    sim.damage_popups = []
    sim.events = []
    sim.vfx_events = []
    sim.sound_events = []
    sim.obstacles = []
    wild = Enemy("deer", (100, 100)); wild.pos = pygame.Vector2(100, 100)
    sim.enemies = [wild]
    killer = Player("wizard", "K", pid="p1")
    b = Bullet((100, 100), (1, 0), 999999, "p1", (255, 0, 0), 0, 10, 1.0)
    b.pos = pygame.Vector2(100, 100)
    sim.bullets = [b]
    sim._resolve_bullet_hits({"p1": killer})
    assert wild.hp == wild.hp_max and wild.alive, "bullets must pass through unshootable wildlife"
    print("check_unshootable: PASSED")


def check_flee():
    sim = realm_sim.RealmSim.__new__(realm_sim.RealmSim)
    wild = Enemy("songbird", (200, 200)); wild.pos = pygame.Vector2(200, 200)
    sim.enemies = [wild]
    b = Bullet((210, 200), (1, 0), 10, "p1", (255, 0, 0), 0, 5, 1.0)
    b.pos = pygame.Vector2(210, 200)
    sim.bullets = [b]
    sim._trigger_wildlife_flee()
    assert wild.flee_time == realm_sim.FLEE_DURATION
    start = pygame.Vector2(wild.pos)
    for _ in range(30):
        wild.update(1 / 30, pygame.Vector2(1000, 1000), [], tile_map=None)
    assert wild.pos.distance_to(start) > 5
    assert wild.pos.distance_to(b.pos) > start.distance_to(b.pos)
    print("check_flee: PASSED")


def check_push_and_glide():
    deer = Enemy("deer", (100, 100)); deer.pos = pygame.Vector2(100, 100)
    p = Player("wizard", "Bumper", pid="p1"); p.pos = pygame.Vector2(105, 100)
    deer.contact_cd = 0.0
    push_dir = deer.pos - p.pos
    if push_dir.length_squared() < 1:
        push_dir = pygame.Vector2(1, 0)
    deer._push_vec = push_dir.normalize() * realm_sim.PUSH_SPEED
    deer._push_total = realm_sim.PUSH_DURATION
    deer.push_time = realm_sim.PUSH_DURATION
    start = pygame.Vector2(deer.pos)
    for _ in range(30):
        deer.update(1 / 30, pygame.Vector2(9999, 9999), [], tile_map=None)
    assert deer.pos.distance_to(start) > 5, "a pushed mob should actually move"
    assert deer.pos.distance_to(p.pos) > start.distance_to(p.pos), "should glide AWAY from the bump"
    assert deer.push_time == 0.0, "push should fully decay, not linger forever"

    # edge case: a repeated bump (re-triggering push mid-glide) must not
    # compound into runaway velocity - re-arming just resets the same fixed shove
    deer.push_time = realm_sim.PUSH_DURATION
    deer._push_vec = push_dir.normalize() * realm_sim.PUSH_SPEED
    deer._push_total = realm_sim.PUSH_DURATION
    deer.update(1 / 30, pygame.Vector2(9999, 9999), [], tile_map=None)
    assert deer._push_vec.length() == realm_sim.PUSH_SPEED, "re-triggering push must not stack speed"

    # totem (neutral but speed=0) must never be pushable
    totem = Enemy("totem", (0, 0))
    assert totem.speed == 0
    print("check_push_and_glide: PASSED")


def check_wildlife_dialogue():
    for kind in WILDLIFE_KINDS:
        fam = sound_family(kind)
        assert fam == "beast", f"{kind} should map to the beast sound family, got {fam}"

    random.seed(7)
    deer = Enemy("deer", (0, 0)); deer.pos = pygame.Vector2(0, 0)
    deer.speech_age = 999
    said = set()
    far = pygame.Vector2(99999, 99999)
    for _ in range(20000):
        deer.update(1 / 30, far, [], tile_map=None)
        if deer._speech_pending:
            said.add(deer.speech)
            deer._speech_pending = False
    assert said, "peaceful wildlife never spoke - idle ambience speech is broken"
    assert said.issubset(set(WILDLIFE_FLAVOR_LINES)), "wildlife must only say peaceful lines, never combat ones"

    # a real combat mob must still use the normal (non-wildlife) flavor lines
    random.seed(3)
    goblin = Enemy("goblin", (0, 0)); goblin.pos = pygame.Vector2(0, 0)
    goblin.aggro = True
    goblin.speech_age = 999
    goblin._said_first_line = True
    said_g = set()
    for _ in range(20000):
        goblin.update(1 / 30, far, [], tile_map=None)
        if goblin._speech_pending:
            said_g.add(goblin.speech)
            goblin._speech_pending = False
    assert said_g, "an aggro'd combat mob never spoke"
    assert said_g.issubset(set(MOB_FLAVOR_LINES[sound_family("goblin")]))
    assert not said_g & set(WILDLIFE_FLAVOR_LINES), "a combat mob must never say peaceful wildlife lines"

    # edge case: the stationary totem decoration (also neutral) must NEVER speak
    totem = Enemy("totem", (0, 0)); totem.pos = pygame.Vector2(0, 0)
    totem.speech_age = 999
    for _ in range(20000):
        totem.update(1 / 30, far, [], tile_map=None)
        assert not totem._speech_pending, "the stationary totem decoration must never speak"
    print("check_wildlife_dialogue: PASSED")


if __name__ == "__main__":
    check_unshootable()
    check_flee()
    check_push_and_glide()
    check_wildlife_dialogue()
    print("PASSED: collision/wildlife/dialogue checks all green.")

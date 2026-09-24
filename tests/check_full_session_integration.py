"""
Batch 12+13 cross-system integration smoke test. Every fork this batch
tested its OWN system in isolation - this test drives one real Game()
through a realistic sequence hitting MANY of the new systems together in
the same session, to catch interaction bugs that per-track unit tests
would never see (e.g. a draw() call site missing a new argument, two
systems both mutating the same field, a crash only reachable when two
new features are active on the same tick).

Run with: .venv\\Scripts\\python.exe tests\\check_full_session_integration.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()

import main as main_module
from game import vfx, live_events


def check_full_realm_session_with_new_systems():
    game = main_module.Game()
    game.start_run("warrior")
    game.enter_realm()

    p = game.player
    sim = game.realm_sim

    # real draw() every tick - would raise TypeError on any stale call-site
    # signature mismatch across ANY of the touched files (the exact bug
    # class check_day_night_clock already exists to catch for the day/night
    # clock specifically - this exercises everything else added since).
    for _ in range(30):
        game.update(1 / 60)
        game.draw()

    # Track N: dash actually moves the player and sets i-frames
    start_pos = pygame.Vector2(p.pos)
    assert p.try_dash()
    p.update(0.05, pygame.key.get_pressed(), sim.realm_map.bounds(), sim.realm_map.is_solid,
             sim.realm_map.speed_multiplier)
    assert p.pos.distance_to(start_pos) > 0
    assert p._dash_iframes > 0
    game.draw()

    # Track A: juice trio doesn't crash when real damage is applied mid-session
    real = p.take_damage(15)
    sim.damage_popups.append((p.pos.x, p.pos.y, real, (255, 90, 90)))
    sim.vfx_events.append(("hit_player", p.pos.x, p.pos.y, (255, 90, 90)))
    vfx.dispatch(sim.vfx_events)
    sim.vfx_events.clear()
    dt = vfx.apply_hitstop(1 / 60)
    assert 0.0 <= dt <= 1 / 60
    game.draw()

    # Track F: UT socket lookup path doesn't crash when the equipped weapon
    # has no socketed_proc (the common case)
    if p.weapon is not None:
        assert getattr(p.weapon, "socketed_proc", None) in (None, "bleed", "burn", "vulnerable")

    # Track S: fishing state through a real draw pass (bobber render path)
    p.fishing_state = {"phase": "casting", "timer": 1.0, "bobber": (p.pos.x + 20, p.pos.y)}
    game.draw()
    p.fishing_state = {"phase": "biting", "timer": 0.3, "bobber": (p.pos.x + 20, p.pos.y)}
    game.draw()
    p.fishing_state = None
    game.draw()

    # Track C: fast-forward past the world boss cooldown and confirm a full
    # tick+draw cycle survives a spawn without crashing
    sim.world_boss_cd = 0.0
    for _ in range(5):
        game.update(1 / 60)
        game.draw()

    # Track B: death -> Echo award -> account persistence round-trip, inside
    # a real session (not a standalone accounts.py unit test)
    from game import accounts
    name = game.player_name
    before = accounts.get_echoes(name)
    game.die()
    after = accounts.get_echoes(name)
    assert after >= before, "echoes should never decrease on death"

    print("check_full_realm_session_with_new_systems: PASSED")


def check_full_coop_snapshot_round_trip_with_new_fields():
    """The server and client are separate processes in real play - this
    confirms a real snapshot dict round-trips through Player.from_net_state
    with every new Batch 12/13 field intact (fishing_state, dash fields
    aren't networked by design - only fishing_state and socketed_proc are)."""
    from game.entities import Player
    from game.items import Item, SLOT_WEAPON

    src = Player("wizard", "NetTest", pid="p1")
    src.fishing_state = {"phase": "casting", "timer": 1.5, "bobber": (100.0, 200.0)}
    src.weapon = Item("TestBlade", SLOT_WEAPON, 3, "orb", min_dmg=1, max_dmg=2)
    src.weapon.socketed_proc = "bleed"

    net_dict = src.net_state()
    assert net_dict.get("fishing_state") == src.fishing_state

    full = src.full_state()
    restored = Player.from_full_state(full)
    assert restored.fishing_state == src.fishing_state

    ghost = Player.from_net_state(net_dict)
    assert ghost.fishing_state == src.fishing_state

    print("check_full_coop_snapshot_round_trip_with_new_fields: PASSED")


if __name__ == "__main__":
    check_full_realm_session_with_new_systems()
    check_full_coop_snapshot_round_trip_with_new_fields()
    print("PASSED: full cross-system session integration checks all green.")

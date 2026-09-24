"""
Regression check for Batch 14 Track B1 (island mini-bosses, first 5 islands).

Five named boss-tier mobs (cinder_colossus, choir_sovereign, rubble_warlord,
coral_leviathan, ashreach_revenant) now lead the flare/song wave for island
indices 0-4 (see realm_sim.ISLAND_MINI_BOSS) instead of the generic theme
anchor. This confirms: each renders as a real, distinct, boss-scaled
sprite; the wave-spawn for these 5 islands actually includes the boss; the
boss is meaningfully tougher than a regular guardian; and defeating the
whole wave (boss + escort, not just an escort mob) triggers the per-island
reward.

Run with: .venv\\Scripts\\python.exe tests\\check_island_mini_bosses_b1.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

from game import sprites, realm_sim
from game.entities import ENEMY_KINDS as ENEMY_DEFS, Player

B1_BOSS_KINDS = ["cinder_colossus", "choir_sovereign", "rubble_warlord",
                 "coral_leviathan", "ashreach_revenant"]

BASE_KINDS = [
    "bat", "ghost", "skeleton", "imp", "goblin", "scorpion", "yeti",
    "troll", "harpy", "salamander", "panther", "ghoul", "frost_wraith",
    "cave_lurker",
]

ALL_EXISTING_ENEMY_KINDS = [k for k in ENEMY_DEFS.keys() if k not in B1_BOSS_KINDS]


def _pixels(surf):
    return pygame.image.tostring(surf, "RGBA")


def check_all_bosses_render_valid_boss_scaled_surfaces():
    for kind in B1_BOSS_KINDS:
        assert kind in sprites.BOSS_KINDS, f"{kind}: not registered in BOSS_KINDS (won't get boss sprite scale)"
        surf = sprites.enemy_sprite(kind)
        assert isinstance(surf, pygame.Surface), f"{kind}: not a Surface"
        w, h = surf.get_size()
        assert w > 0 and h > 0, f"{kind}: empty surface {w}x{h}"
        assert any(surf.get_at((x, y))[3] > 0 for x in range(w) for y in range(h)), \
            f"{kind}: fully transparent, nothing actually drawn"
    print("check_all_bosses_render_valid_boss_scaled_surfaces: OK")


def check_bosses_distinct_from_each_other_and_from_every_existing_kind():
    rendered = {k: _pixels(sprites.enemy_sprite(k)) for k in B1_BOSS_KINDS}
    for i, a in enumerate(B1_BOSS_KINDS):
        for b in B1_BOSS_KINDS[i + 1:]:
            assert rendered[a] != rendered[b], f"{a} and {b} render pixel-identical"
    existing_pixels = {k: _pixels(sprites.enemy_sprite(k)) for k in ALL_EXISTING_ENEMY_KINDS}
    for boss in B1_BOSS_KINDS:
        bp = rendered[boss]
        for k, kp in existing_pixels.items():
            assert bp != kp, f"{boss} renders pixel-identical to existing kind {k}"
    print("check_bosses_distinct_from_each_other_and_from_every_existing_kind: OK")


def check_boss_stats_are_real_boss_tier():
    ANCHOR_HP = {"cinder_warden": ENEMY_DEFS["cinder_warden"]["hp"],
                 "choir_warden": ENEMY_DEFS["choir_warden"]["hp"]}
    max_anchor_hp = max(ANCHOR_HP.values())
    for kind in B1_BOSS_KINDS:
        d = ENEMY_DEFS[kind]
        assert d["rank"] == "boss", f"{kind}: rank should be 'boss', got {d['rank']!r}"
        assert d["hp"] >= max_anchor_hp * 2, (
            f"{kind}: hp {d['hp']} isn't meaningfully tougher than the toughest "
            f"anchor guardian's hp {max_anchor_hp}"
        )
        assert d["aggro_range"] >= 99999 and d["leash_range"] >= 99999, \
            f"{kind}: a real boss should never leash, like the existing dungeon bosses"
    print("check_boss_stats_are_real_boss_tier: OK")


def check_wave_spawn_includes_the_mini_boss_for_islands_0_to_4():
    sim = realm_sim.RealmSim(bonus=False)
    assert len(sim.islands) == 10, f"expected 10 islands, got {len(sim.islands)}"
    for idx in range(5):
        isl = sim.islands[idx]
        isl["cooldown"] = 0.0
        isl["alive_guardians"] = 0
    before_count = len(sim.enemies)
    sim._tick_island_events(0.0)
    new_enemies = sim.enemies[before_count:]
    spawned_kinds_by_island = {}
    for e in new_enemies:
        spawned_kinds_by_island.setdefault(e.island_idx, []).append(e.kind)
    for idx in range(5):
        expected_boss = realm_sim.ISLAND_MINI_BOSS[idx]
        kinds = spawned_kinds_by_island.get(idx, [])
        assert expected_boss in kinds, (
            f"island {idx}: expected mini-boss {expected_boss!r} in spawned wave {kinds}"
        )
        assert len(kinds) == 1 + realm_sim.ISLAND_ESCORT_SIZE, (
            f"island {idx}: expected a boss + {realm_sim.ISLAND_ESCORT_SIZE}-mob escort "
            f"({1 + realm_sim.ISLAND_ESCORT_SIZE} total), got {len(kinds)}: {kinds}"
        )
    print("check_wave_spawn_includes_the_mini_boss_for_islands_0_to_4: OK")


def check_defeating_only_escort_does_not_reward_but_defeating_boss_too_does():
    sim = realm_sim.RealmSim(bonus=False)
    isl = sim.islands[0]
    isl["cooldown"] = 0.0
    isl["alive_guardians"] = 0
    before_count = len(sim.enemies)
    sim._tick_island_events(0.0)
    # Every island defaults to a zero initial cooldown (a deliberate earlier-batch
    # fix so guardians are already present on first entry), so this single tick
    # call spawns waves on ALL islands at once - scope strictly to island 0's own
    # wave, not just "not the boss" (which would also catch other islands' mobs).
    wave = [e for e in sim.enemies[before_count:] if e.island_idx == 0]
    boss = next(e for e in wave if e.kind == realm_sim.ISLAND_MINI_BOSS[0])
    escorts = [e for e in wave if e is not boss]

    killer = Player("wizard", "Tester", pid="p0")
    events_before = len(sim.events)
    for e in escorts:
        sim._progress_island_event(e, killer)
    assert isl["alive_guardians"] == 1, "boss should still be alive after only escorts die"
    assert len(sim.events) == events_before, "no reward/completion event should fire yet"

    sim._progress_island_event(boss, killer)
    assert isl["alive_guardians"] == 0, "boss's death should finally zero out alive_guardians"
    assert any("calmed" in msg for _, msg, _ in sim.events), (
        "defeating the boss (completing the wave) should trigger the completion announcement"
    )
    print("check_defeating_only_escort_does_not_reward_but_defeating_boss_too_does: OK")


if __name__ == "__main__":
    check_all_bosses_render_valid_boss_scaled_surfaces()
    check_bosses_distinct_from_each_other_and_from_every_existing_kind()
    check_boss_stats_are_real_boss_tier()
    check_wave_spawn_includes_the_mini_boss_for_islands_0_to_4()
    check_defeating_only_escort_does_not_reward_but_defeating_boss_too_does()
    print("ALL CHECKS PASSED")

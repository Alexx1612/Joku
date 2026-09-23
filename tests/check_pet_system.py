"""
Regression check for the multi-ability pet system (heal + mana + attack all
able to fire in the same tick, feeding/leveling, rarity caps, net_state/
save-load round trips). Covers normal cases and edge cases (feeding an egg
must be rejected; feeding past the rarity cap must never overflow).

Run with: .venv\\Scripts\\python.exe tests\\check_pet_system.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game.entities import Player, Pet, PET_ABILITY_KEYS
from game.items import PET_RARITY_MAX_LEVEL, PET_RARITY_START_LEVEL, make_egg, Item, SLOT_WEAPON, pet_ability_stats


def check_hatch_and_simultaneous_abilities():
    owner = Player("wizard", "Tester", pid="p1")
    owner.pos = pygame.Vector2(0, 0)
    pet = Pet("hatchling", owner.pos)  # family="heal", rarity="common"
    assert set(pet.abilities.keys()) == set(PET_ABILITY_KEYS)
    assert pet.abilities["heal"]["level"] == PET_RARITY_START_LEVEL["common"]
    assert pet.abilities["magic"]["level"] == 1 and pet.abilities["attack"]["level"] == 1

    owner.pet = pet
    owner.hp_max, owner.hp = 100, 40
    owner.mp_max, owner.mp = 100, 10
    for st in pet.abilities.values():
        st["cd"] = 0.0

    class FakeEnemy:
        def __init__(self, pos):
            self.pos = pygame.Vector2(pos)

    bullets_out = []
    events = pet.update(1 / 30, owner, [FakeEnemy((30, 0))], bullets_out)
    kinds = {e[0] for e in events}
    assert "heal" in kinds and "mana" in kinds, "heal and mana should both fire in the same tick"
    assert len(bullets_out) == 1, "attack should also fire in that same tick"
    print("check_hatch_and_simultaneous_abilities: PASSED")


def check_feeding_and_caps():
    owner = Player("wizard", "Feeder", pid="p2")
    owner.pet = Pet("hatchling", owner.pos)  # common -> max level 10
    owner.backpack = [Item("Junk", SLOT_WEAPON, 5, "sword", min_dmg=1, max_dmg=2)]
    assert owner.feed_pet(0) is True
    assert len(owner.backpack) == 0

    owner.backpack = [Item("Junk", SLOT_WEAPON, 11, "sword", min_dmg=1, max_dmg=2) for _ in range(200)]
    while owner.backpack:
        owner.feed_pet(0)
    max_level = PET_RARITY_MAX_LEVEL["common"]
    for k, st in owner.pet.abilities.items():
        assert st["level"] <= max_level, f"{k} exceeded its rarity max level"
        if st["level"] == max_level:
            assert st["xp"] == 0.0, "xp must be pinned to 0 once maxed, not overflowing"

    # edge case: eggs must never be feedable (they're hatched, not fed)
    owner.backpack = [make_egg("hatchling")]
    assert owner.feed_pet(0) is False

    # edge case: feeding with no pet must not crash
    owner2 = Player("wizard", "NoPet", pid="p3")
    owner2.backpack = [Item("Junk", SLOT_WEAPON, 5, "sword", min_dmg=1, max_dmg=2)]
    assert owner2.feed_pet(0) is False

    # edge case: an out-of-range backpack index must not crash
    assert owner.feed_pet(999) is False
    print("check_feeding_and_caps: PASSED")


def check_level_scaling():
    m1, c1 = pet_ability_stats("heal", 1)
    m10, c10 = pet_ability_stats("heal", 10)
    assert m10 > m1, "higher level should heal for more"
    assert c10 < c1, "higher level should have a shorter cooldown"
    assert c10 > 0.4, "cooldown must stay well above zero even at high level"
    print("check_level_scaling: PASSED")


def check_persistence_round_trips():
    pet = Pet("griffin_cub", (5, 5))
    pet.abilities["heal"]["level"] = 7
    pet.abilities["heal"]["xp"] = 12.5
    pet.abilities["magic"]["level"] = 3
    restored = Pet.from_net_state(pet.net_state())
    assert restored.abilities["heal"]["level"] == 7
    assert restored.abilities["heal"]["xp"] == 12.5
    assert restored.abilities["magic"]["level"] == 3
    assert restored.kind == "griffin_cub"

    owner = Player("archer", "Saver", pid="p4")
    owner.pet = pet
    restored_owner = Player.from_full_state(owner.full_state())
    assert restored_owner.pet is not None
    assert restored_owner.pet.abilities["heal"]["level"] == 7
    print("check_persistence_round_trips: PASSED")


if __name__ == "__main__":
    check_hatch_and_simultaneous_abilities()
    check_feeding_and_caps()
    check_level_scaling()
    check_persistence_round_trips()
    print("PASSED: pet system checks all green.")

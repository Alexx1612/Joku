"""
Pets follow their owner in the hub zones (Nexus/Bazaar/Vault room), in both
single-player and co-op. Only RealmSim.tick_pets used to move a pet, so in a
hub it stayed frozen wherever the player left the Realm - usually off-screen,
which read as "pets aren't drawn in the Nexus".
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((100, 100))

from game import achievements, items, characters, accounts
achievements._DIR = tempfile.mkdtemp(prefix="rr_hubpet_ach_")
items.VAULT_DIR = tempfile.mkdtemp(prefix="rr_hubpet_vault_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_hubpet_char_")
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_hubpet_acc_")

import main
import server
from game.entities import Player, Pet

FAR = pygame.Vector2(5000, 5000)


def check_singleplayer_nexus_pet_follows():
    game = main.Game()
    game.state = main.STATE_NEXUS
    game.player = Player("wizard", "HubPet", pid="sp")
    game.player.pos = game.nexus_map.center_world_pos()
    game.player.pet = Pet("hatchling", FAR)
    game.player.pet.pos = pygame.Vector2(FAR)
    for _ in range(90):
        game.update(1 / 30)
    d = game.player.pet.pos.distance_to(game.player.pos)
    assert d < 60, f"SP Nexus pet should catch up with its owner, still {d:.0f}px away"
    game.draw()  # and drawing it there doesn't crash
    print("check_singleplayer_nexus_pet_follows: PASSED")


class FakeSock:
    def sendall(self, data):
        pass


def check_coop_hub_pet_follows():
    state = server.ServerState()
    for zone in (server.ZONE_NEXUS, server.ZONE_BAZAAR):
        p = Player("wizard", name="CoopPet" + zone, pid="c" + zone)
        p.pos = server._nexus_spawn_pos(state)
        p.pet = Pet("wisp", FAR)
        p.pet.pos = pygame.Vector2(FAR)
        s = server.Session(p.pid, FakeSock(), p)
        s.zone = zone
        if zone == server.ZONE_BAZAAR:
            p.pos = state.bazaar_map.center_world_pos()
        state.sessions[s.pid] = s
    for _ in range(30):
        server.step(state, 0.1)
    for s in state.sessions.values():
        d = s.player.pet.pos.distance_to(s.player.pos)
        assert d < 60, f"co-op {s.zone} pet should follow its owner, still {d:.0f}px away"
        # and the snapshot the client draws from carries the updated pet position
        pet_state = s.player.full_state()["pet"]
        assert abs(pet_state["x"] - s.player.pet.pos.x) < 1
    print("check_coop_hub_pet_follows: PASSED")


if __name__ == "__main__":
    check_singleplayer_nexus_pet_follows()
    check_coop_hub_pet_follows()
    print("PASSED: hub pet checks all green.")

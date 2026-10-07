"""
The in-game Dictionary (game/codex.py + game/codex_extra.py) covers everything: every monster
kind, every NPC, and every system the "v0.2 final final" session added (night, weather, stars,
herbs, the calendar, danger, quest markers, gems, shards, the Anvil, ...). Fails if a new mob or
system ships without an entry.

Run with: .venv\\Scripts\\python.exe tests\\check_dictionary_complete.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((1366, 820))

from game import codex, gems, npcs, sprites
from game.entities import ENEMY_KINDS, NIGHT_MOB_KINDS

REQUIRED = [
    "help:day_night", "help:darkness", "help:safe_houses", "help:night_rules", "help:night_events",
    "help:blood_moon", "help:moon", "help:weather", "help:shooting_stars", "help:night_herbs", "help:night_life",
    "help:golden_hour", "help:calendar", "help:danger", "help:quest_markers", "help:lamplighter",
    "help:precise_combat", "help:chat_commands",
    "help:tiers", "help:anvil", "help:gems", "help:stonework", "help:gem_veins", "help:divine", "help:keys",
    "help:weapon_shards", "help:bag2",
    "item:light_of_rdv", "item:moonpetal", "item:ghostbloom", "item:star_fragment", "item:forge_ingot",
    "item:mad_god_key",
] + [f"item:gem:{k}" for k in gems.KINDS]

SEARCHES = ["blood moon", "lightning", "shooting star", "moonpetal", "owl", "calendar", "danger", "lethal",
            "quest marker", "ruby", "resonant", "anvil", "luminosity", "safe house", "lamplighter", "rdv",
            "heroic", "weapon shard", "bag 2", "/help"]


def check_every_mob_and_npc():
    for kind in ENEMY_KINDS:
        e = codex.entry(f"enemy:{kind}")
        assert e is not None and e["text"], kind
    for kind in NIGHT_MOB_KINDS:
        assert "NIGHT ONLY" in codex.entry(f"enemy:{kind}")["text"], kind
    for k in ("moonpetal", "ghostbloom"):
        assert "pick" in codex.entry(f"enemy:{k}")["text"]
    for npc_id in npcs.NPCS:
        assert codex.entry(f"npc:{npc_id}") is not None, npc_id
    print(f"check_every_mob_and_npc: PASSED ({len(ENEMY_KINDS)} mobs, {len(npcs.NPCS)} NPCs)")


def check_new_systems_have_entries():
    cats = {c for c, _l in codex.CATEGORIES}
    for eid in REQUIRED:
        e = codex.entry(eid)
        assert e is not None, eid
        assert e["cat"] in cats and len(e["text"]) > 60, eid
    for q in SEARCHES:
        assert codex.search(q), q
    for e in codex.entries():
        sp = e.get("sprite")
        if sp and sp.get("src") == "item":
            assert sprites.item_icon(sp.get("tint") or (255, 255, 255), sp["key"]) is not None, e["id"]
    print(f"check_new_systems_have_entries: PASSED ({len(REQUIRED)} entries, {len(SEARCHES)} searches)")


if __name__ == "__main__":
    check_every_mob_and_npc()
    check_new_systems_have_entries()
    print("\nALL DICTIONARY COMPLETENESS CHECKS PASSED")

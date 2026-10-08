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


def check_every_entry_is_tagged():
    """One type tag per entry (codex.entry_tag), creatures wear creature tags, every help:
    page is a TIP or a MECHANIC, and the chips filter (OR between chips, AND with search)."""
    from game.entities import ENEMY_KINDS
    es = codex.entries()
    assert all(e.get("tag") in codex.TAGS for e in es)
    assert all(codex.entry_tag(e) == e["tag"] for e in es)
    for label, abbr, col, icon in codex.TAGS.values():
        assert label and abbr and icon and len(col) == 3  # colour is never the only cue
    for e in es:
        if e["id"].startswith("enemy:"):
            assert e["tag"] in codex.CREATURE_TAGS, (e["id"], e["tag"])
        if e["id"].startswith("help:"):
            assert e["tag"] in codex.NOTE_TAGS, (e["id"], e["tag"])
        if e["id"].startswith("npc:") and e["cat"] == "npcs":
            assert e["tag"] == "npc", e["id"]
        if e["id"].startswith("pet:"):
            assert e["tag"] == "pet"
    ids = {e["id"] for e in es}
    assert codex.TIP_IDS <= ids, codex.TIP_IDS - ids
    assert codex.entry("enemy:red_harvester")["tag"] == "boss"
    assert codex.entry("enemy:shade_stalker")["tag"] == "night_mob"
    assert codex.entry("enemy:goblin")["tag"] == "creature"
    herb = next(k for k, d in ENEMY_KINDS.items() if d.get("herb"))
    assert codex.entry(f"enemy:{herb}")["tag"] == "herb"
    assert codex.entry("help:stonework")["tag"] == "tip" and codex.entry("help:blood_moon")["tag"] == "mechanic"
    # every tag is used by something
    assert {e["tag"] for e in es} == set(codex.TAGS), set(codex.TAGS) - {e["tag"] for e in es}
    # filtering: chips OR together, AND with the search; chips span every category
    tips = codex.filter_entries("", "mobs", {"tip"})
    assert tips and all(e["tag"] == "tip" for e in tips) and len({e["cat"] for e in tips}) > 1
    both = codex.filter_entries("", None, {"boss", "night_mob"})
    assert {e["tag"] for e in both} == {"boss", "night_mob"}
    red = codex.filter_entries("harvester", None, {"boss", "night_mob"})
    assert red and all(e["tag"] in ("boss", "night_mob") and "harvester" in e["search"] for e in red)
    assert len(red) < len(both) and "help:blood_moon" not in [e["id"] for e in red]
    # world content first, then the tips & mechanics (each category, and any search)
    for cat, _l in codex.CATEGORIES:
        lst = codex.filter_entries("", cat)
        notes = [codex.is_note(e) for e in lst]
        assert notes == sorted(notes), cat
    # the window: chip clicks filter, the "Tips & mechanics" sub-heading sits after the world rows
    from game import journal, settings
    import tempfile
    settings.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(prefix="rr_dict_set_"), "settings.json")
    j = journal.Journal()
    j.open_dictionary()
    j._pick_category("pets")
    rows = j._rows()
    h = [k for k, _e in rows].index("header")
    assert all(not codex.is_note(e) for _k, e in rows[:h]) and all(codex.is_note(e) for _k, e in rows[h + 1:])
    r = j._dict_rects()
    chip = dict((t, rc) for t, rc in j._chip_rects(r))
    j._click(chip["tip"].center, {})
    assert j.tags == {"tip"} and settings.get("dict_tags") == ["tip"]
    assert all(e["tag"] == "tip" for e in j._list())
    assert journal.Journal().tags == {"tip"}, "the chips are remembered"
    j._click(chip[None].center, {})
    assert not j.tags and settings.get("dict_tags") == []
    # the whole window fits at 1366x820 (chips, categories, list, detail)
    from game import constants as C
    win = r["win"]
    assert pygame.Rect(0, 0, C.SCREEN_W, C.SCREEN_H).contains(win)
    assert all(win.contains(rc) for _t, rc in r["chips"])
    assert win.contains(j._cat_rect(r, len(codex.CATEGORIES) - 1)) and win.contains(r["mid"])
    print(f"check_every_entry_is_tagged: PASSED ({len(es)} entries, {len(codex.TAGS)} tags)")


if __name__ == "__main__":
    check_every_mob_and_npc()
    check_new_systems_have_entries()
    check_every_entry_is_tagged()
    print("\nALL DICTIONARY COMPLETENESS CHECKS PASSED")

"""
Gameplay snapshots into screenshots/<YYYY-MM-DD>/ (headless), so there's a dated record of
what the game looked like and what that day's work added. Each shot is listed with a
one-line caption in the folder's NOTES.md (appended to if the folder already exists).

Run with: python tools/take_snapshots.py ["what was done today"]
"""
import datetime
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["RR_NO_MUSIC"] = "1"

from game import accounts, characters, achievements
accounts.ACCOUNTS_DIR = tempfile.mkdtemp()
characters.CHAR_DIR = tempfile.mkdtemp()
achievements._DIR = tempfile.mkdtemp()

import pygame
import main
from game import minimap, runes, items as I, realm_sim as rs
from game.realm_sim import RealmSim
from game.entities import Enemy

DATE = datetime.date.today().isoformat()
OUT = os.path.join(ROOT, "screenshots", DATE)


def _game():
    random.seed(5)
    g = main.Game()
    g.player_name = "Snap"
    g.start_run("wizard")
    g.realm_sim = RealmSim()
    g.realm_minimap = minimap.MinimapState()
    g.state = main.STATE_REALM
    g.quest_log_expanded = False
    area = next(a for a in g.realm_sim.areas if a["key"] == "tavern_town")
    g.player.pos = pygame.Vector2(area["rect"].centerx * 32, area["rect"].centery * 32 + 140)
    return g


def _shot(g, name, caption, t=None, moon=0, ring=None, settle=3, notes=None):
    sim = g.realm_sim
    if t is not None:
        sim.day_time = t
    sim.night_count = moon
    g.player.ring = ring
    for _ in range(settle):
        g.update(1 / 60)
    if t is not None:
        sim.day_time = t
    if hasattr(g, "_eyes"):
        g._eyes.level, g._eyes._was_night = 1.0, sim.is_night
    g.draw()
    pygame.image.save(g.screen, os.path.join(OUT, name + ".png"))
    notes.append(f"- `{name}.png` - {caption}")


def main_():
    os.makedirs(OUT, exist_ok=True)
    notes = []
    g = _game()
    sim = g.realm_sim
    sim.blood_moon_active = False
    sim.enemies = []
    _shot(g, "day_town", "a normal day in the tavern town", t=100, notes=notes)
    _shot(g, "golden_hour", "golden hour before dusk: warm grade, low-sun glow from the west", t=270, notes=notes)
    _shot(g, "blue_hour", "blue hour just after sunset", t=335, notes=notes)
    _shot(g, "night_full_moon", "night under a full moon (brighter), lit windows, lamp light + wall shadows",
          t=420, moon=4, notes=notes)
    _shot(g, "night_new_moon", "the same spot under a new moon (darkest)", t=420, moon=0, notes=notes)
    _shot(g, "night_light_of_rdv", "wearing the Light of RDV ring: x1.6 light radius", t=420,
          ring=I.make_rdv_ring(), notes=notes)
    _shot(g, "dawn_mist", "sunrise: dawn mist + golden glow from the east", t=572, moon=2, notes=notes)
    # dock tabs
    g.player.backpack2 = [I.make_rdv_ring()]
    g.player.rune_slots = [runes.make_rune() for _ in range(6)] + [None] * 6
    for mode, cap in (("shards", "the dock's Shards tab (top 4 sockets active)"), ("bag2", "the dock's Bag 2 tab")):
        g.right_panel_mode = mode
        _shot(g, f"dock_{mode}", cap, t=100, notes=notes)
    g.right_panel_mode = "inventory"
    # the Lamplighter, with a sleeping songbird next to him
    random.seed(3)
    sim.enemies = []
    sim.day_time = 420
    sim.night._start_lamplighter()
    w = sim.night.ward
    g.player.pos = pygame.Vector2(w["npc"].pos) + pygame.Vector2(70, 30)
    w["hp"] = 260
    w["npc"].hp_frac = 260 / 420
    bird = Enemy(rs.DIURNAL_WILDLIFE[0], g.player.pos + pygame.Vector2(-90, 60))
    sim.enemies = [bird]
    _shot(g, "lamplighter_event", "the Lamplighter event: protect Old Wick (HP bar) until dawn; a day bird asleep (z z)",
          t=420, moon=4, notes=notes)
    _shot(g, "lamplighter_rdv", "the Lamplighter event while wearing the Light of RDV", t=420, moon=4,
          ring=I.make_rdv_ring(), notes=notes)

    path = os.path.join(OUT, "NOTES.md")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write(f"# Gameplay snapshots - {DATE}\n\n")
        if len(sys.argv) > 1:
            f.write(f"## What was done\n{sys.argv[1]}\n\n")
        f.write(f"## Shots (taken {datetime.datetime.now():%Y-%m-%d %H:%M}, tools/take_snapshots.py)\n")
        f.write("\n".join(notes) + "\n\n")
    print(f"{len(notes)} shots -> {OUT}")


if __name__ == "__main__":
    main_()

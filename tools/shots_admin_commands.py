"""Screenshots of the admin / testing commands (game/admin.py) into screenshots/<date>/admin_commands/."""
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

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "screenshots", datetime.date.today().isoformat(),
                                                          "admin_commands")
os.makedirs(OUT, exist_ok=True)
random.seed(4)
notes = []
g = main.Game()
g.player_name = "Admin"
g.start_run("wizard")
g.enter_realm()


def type_cmd(text):
    g.chat_buffer = text
    g._submit_chat()


def shot(name, caption, frames=3):
    for _ in range(frames):
        g.update(1 / 60)
    g.draw()
    pygame.image.save(g.screen, os.path.join(OUT, name + ".png"))
    notes.append(f"- `{name}.png` - {caption}")


g.realm_sim.events.clear()
type_cmd("/help")
shot("help_overview", "/help - every command, grouped by category (scroll, Esc closes)")
type_cmd("/help items")
shot("help_items", "/help items - one category with usage + description")
type_cmd("/help give")
shot("help_give", "/help give - details and examples for one command")
g.cmd_panel = None
type_cmd("/maxstats")
type_cmd("/tier 13")
type_cmd("/give perfect ruby x3")
type_cmd("/give light of rdv")
shot("give_and_feed", "/maxstats, /tier 13, /give perfect ruby x3, /give light of rdv - short results go to the feed")
type_cmd("/stats")
shot("stats_panel", "/stats - your character, gear, flags and buffs")
g.cmd_panel = None
type_cmd("/time night")
type_cmd("/spawn goblin 5")
type_cmd("/spawn shade_stalker 2 moonlit")
type_cmd("/hitboxes on")
shot("spawn_hitboxes_night", "/time night, /spawn goblin 5, /spawn shade_stalker 2 moonlit, /hitboxes on", frames=6)
type_cmd("/hitboxes off")
type_cmd("/spawn list")
shot("spawn_list", "/spawn list - every mob kind (rank, night-only, neutral)")
g.cmd_panel = None

with open(os.path.join(OUT, "NOTES.md"), "w", encoding="utf-8") as f:
    f.write(f"# Admin / testing commands - {datetime.date.today().isoformat()}\n\n"
            "Chat commands for testing (game/admin.py); co-op servers need --admin. Taken with "
            "tools/shots_admin_commands.py.\n\n" + "\n".join(notes) + "\n")
print(len(notes), "shots ->", OUT)

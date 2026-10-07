"""Gem forging screenshots -> screenshots/<date>/gem_forging/ (+ NOTES.md). Headless."""
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
from game import minimap, gems as G, vfx, dialogue, ui, items as I
from game.realm_sim import RealmSim
from game.entities import Bullet, Enemy

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "screenshots", datetime.date.today().isoformat(),
                                                         "gem_forging")
os.makedirs(OUT, exist_ok=True)
notes = []


def save(g, name, caption):
    pygame.image.save(g.screen, os.path.join(OUT, name + ".png"))
    notes.append(f"- `{name}.png` - {caption}")


def weapon(tier=11):
    r = next(r for r in I.WEAPONS["wizard"] if r[2] == tier)
    return I.Item(r[0], "weapon", tier, r[1], min_dmg=r[3][0], max_dmg=r[3][1])


random.seed(4)
g = main.Game()
g.player_name = "Gemma"
g.start_run("wizard")
g.realm_sim = RealmSim()
g.realm_minimap = minimap.MinimapState()
g.state = main.STATE_REALM
g.quest_log_expanded = False
sim = g.realm_sim
sim.day_time = 120
sim.blood_moon_active = False
area = next(a for a in sim.areas if a["key"] == "tavern_town")
g.player.pos = pygame.Vector2(area["rect"].centerx * 32 - 200, area["rect"].centery * 32 + 140)
for _ in range(3):
    g.update(1 / 60)
sim.day_time = 120

# 1) every element's shot in flight, the player wearing a Resonant ruby weapon
g.player.weapon = weapon()
g.player.weapon.gems = [["ruby", "perfect"]] * 3
sim.enemies = []
sim.bullets = []
for i, k in enumerate(G.KINDS):
    b = Bullet(g.player.pos + pygame.Vector2(70 + (i % 2) * 40, -150 + i * 46), (380, -40 + i * 12), 10, g.player.pid,
               G.color_of(k), 0, 5, 9.0, shape="orb")
    b.gem = k
    sim.bullets.append(b)
g.draw()
save(g, "bullets_all_elements", "a shot from each stone in flight (top to bottom: ruby, sapphire, topaz, emerald, "
                                "amethyst, onyx, diamond) + the Resonant-ruby weapon aura on the player")

# 2) on-hit bursts per element, a frame or two after impact
sim.bullets = []
evs = [("gem_hit", g.player.pos.x - 330 + (i % 4) * 90, g.player.pos.y + 90 + (i // 4) * 100, G.color_of(k), k)
       for i, k in enumerate(G.KINDS)]
vfx.dispatch(evs)
vfx.update(0.06)
g.draw()
save(g, "on_hit_bursts", "each element's on-hit burst (embers, ice shards, sparks, venom cloud, arcane pull, smoke, prism)")
for _ in range(30):
    vfx.update(1 / 30)

# 3) Resonant on-kill effects
evs = [("gem_burst", g.player.pos.x + 140, g.player.pos.y - 110, G.color_of("ruby"), "ruby"),
       ("gem_burst", g.player.pos.x + 330, g.player.pos.y - 110, G.color_of("sapphire"), "sapphire"),
       ("gem_burst", g.player.pos.x + 140, g.player.pos.y + 90, G.color_of("emerald"), "emerald"),
       ("gem_burst", g.player.pos.x + 330, g.player.pos.y + 90, G.color_of("onyx"), "onyx",
        g.player.pos.x, g.player.pos.y)]
vfx.dispatch(evs)
vfx.update(0.12)
g.draw()
save(g, "resonant_kills", "on-kill effects: Resonant ruby fire burst, sapphire frost shatter, emerald venom spread, "
                          "onyx soul feast flowing back to you")
for _ in range(40):
    vfx.update(1 / 30)

# 4) real combat: a Resonant topaz weapon firing at a pack of goblins
g.player.weapon.gems = [["topaz", "flawless"]] * 3
sim.enemies = [Enemy("goblin", g.player.pos + pygame.Vector2(200 + (i % 3) * 40, -40 + (i // 3) * 50)) for i in range(6)]
for e in sim.enemies:
    e.hp = e.hp_max = 10 ** 4
for k in range(7):
    sim.player_fire(g.player, (sim.enemies[1].pos - g.player.pos).normalize())
    for _ in range(9):
        for b in sim.bullets:
            b.update(1 / 60)
        sim._resolve_bullet_hits({g.player.pid: g.player})
    vfx.dispatch(sim.vfx_events)
    sim.vfx_events = []
    vfx.update(1 / 30)
g.draw()
save(g, "combat_topaz", "a 3-Topaz (Resonant) weapon in a fight: gold shots with lightning tails, arcs jumping between goblins")
sim.enemies = []
sim.bullets = []
for _ in range(40):
    vfx.update(1 / 30)

# 5) the inventory: stones of every kind and grade + gemmed weapons, with a weapon tooltip
w2 = weapon(7)
w2.gems = [["sapphire", "flawless"], ["sapphire", "regular"]]
w3 = weapon(3)
w3.gems = [["emerald", "chipped"]]
g.player.weapon.gems = [["diamond", "perfect"], ["amethyst", "flawless"], ["onyx", "regular"]]
g.player.backpack = [w2, w3, G.make_gem("ruby", "perfect"), G.make_gem("topaz", "flawless"),
                     G.make_gem("emerald", "regular"), G.make_gem("amethyst", "flawed"),
                     G.make_gem("onyx", "chipped"), G.make_gem("diamond", "regular")]
g.draw()
rects = ui.backpack_slot_rects(g.player) if hasattr(ui, "backpack_slot_rects") else None
pos = (560, 560)
ui._tooltip(g.screen, pos, w2)
save(g, "inventory_gems", "the backpack: two gemmed weapons (glow + socket pips) and one stone of each kind/grade; "
                          "tooltip lists the sockets and the Attuned bonus")

# 6) a gem vein, being mined
v = min(sim.gem_veins, key=lambda v: v["pos"].distance_to(g.player.pos))
g.player.pos = pygame.Vector2(v["pos"]) + pygame.Vector2(40, 24)
g.player.backpack = []
g.camera_snap = True
for _ in range(3):
    g.update(1 / 60)
sim.start_mining(g.player)
for _ in range(14):
    sim._tick_mining(0.05, {g.player.pid: g.player})
vfx.dispatch(sim.vfx_events)
sim.vfx_events = []
vfx.update(0.05)
g.draw()
save(g, "gem_vein_mining", f"a {v['biome']} gem vein ({', '.join(v['kinds'])}) being mined - progress bar, chips flying")

# 7) the Anvil's Stonework menu (Nexus)
g.state = main.STATE_NEXUS
anvil = next(n for n in g.nexus_npcs if dialogue.NPCS[n.npc_id].get("anvil"))
g.player.pos = pygame.Vector2(anvil.pos) + pygame.Vector2(50, 20)
g.player.weapon = weapon()
g.player.weapon.gems = [["ruby", "flawless"]]
g.player.backpack = [G.make_gem("ruby", "regular"), G.make_gem("sapphire", "flawed")] + \
    [G.make_gem("topaz", "chipped") for _ in range(3)]
for _ in range(3):
    g.update(1 / 60)
conv = dialogue.start_conversation(g.player, npc=anvil)
g.dialogue = conv
i = next(i for i, o in enumerate(conv.view()["options"]) if o.startswith("Stonework"))
conv.choose(i)
conv.sfx = []
g.draw()
save(g, "anvil_stonework_menu", "Brother Hammerstein's Stonework menu: set a stone, combine 3 Chipped Topaz, pry one out")
i = next(i for i, o in enumerate(conv.view()["options"]) if o.startswith("Set Ruby"))
conv.choose(i)
g._play_dialogue_sfx(conv)
vfx.update(0.08)
g.draw()
save(g, "anvil_set_stone", "setting a second Ruby: hammer sparks in the stone's colour, the weapon is now Attuned")

with open(os.path.join(OUT, "NOTES.md"), "w", encoding="utf-8") as f:
    f.write(f"# Gem forging - {datetime.date.today().isoformat()}\n\n"
            "Stones (Ruby/Sapphire/Topaz/Emerald/Amethyst/Onyx/Diamond, Chipped..Perfect) forged into weapons at "
            "Brother Hammerstein's Anvil; element trails, on-hit and on-kill effects, gem veins (docs/unity-rebuild/37).\n\n"
            f"Taken {datetime.datetime.now():%Y-%m-%d %H:%M} with tools/shots_gem_forging.py\n\n" + "\n".join(notes) + "\n")
print(len(notes), "shots ->", OUT)

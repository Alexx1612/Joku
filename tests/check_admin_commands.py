"""
Admin / testing chat commands (game/admin.py): every registered command runs with valid
arguments in single-player AND through the co-op server's "admin" action (only with --admin -
refused without it), the client-side ones run on a co-op client, /help lists everything, and
spot checks that the commands really do what they say (xp/level, fuzzy /give, time / Blood Moon /
weather / night events, spawn / killall, tp, dungeons).

Run with: .venv\\Scripts\\python.exe tests\\check_admin_commands.py
"""
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["RR_NO_MUSIC"] = "1"

import pygame
pygame.init()

from game import accounts, characters, achievements, settings
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_admin_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_admin_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_admin_ach_")

import main
from game import admin, items as I, realm_sim as rs, minimap, ui, runes, gems
from game.entities import ENEMY_KINDS, Player
from game.constants import TILE

random.seed(3)
SHOT_DIR = os.environ.get("RR_SHOT_DIR")

FIRST_PET = next(iter(I.PET_KINDS))
A_QUEST = "mossbeard_mushrooms"
A_THEME = next(k for k, th in rs.DUNGEON_THEMES.items() if not k.startswith("heroic_") and not th.get("mg_room")
               and k != "forge")

# every admin command with valid sample arguments (order matters a little: zone changes, death last)
SAMPLES = [
    ("help", ""), ("help", "2"), ("help", "items"), ("help", "give"), ("help", "nothing_like_this"),
    ("stats", ""), ("pos", ""), ("seed", ""), ("seed", "7"), ("danger", ""), ("forecast", ""), ("forecast", "blood 2"), ("forecast", "calm"), ("forecast", "reroll"),
    ("xp", "500"), ("level", "10"), ("maxstats", ""), ("stat", "att 50"), ("stat", "hp 900"),
    ("heal", ""), ("god", ""), ("god", "off"), ("speed", "3"), ("speed", "1"), ("noclip", ""), ("noclip", "off"),
    ("echoes", "10"), ("potions", ""), ("potions", "reset"), ("buffs", ""), ("buffs", "clear"),
    ("give", "doomstaff"), ("give", "perfect ruby x3"), ("give", "list ruby"), ("give", "staff 11"),
    ("give", "potion of attack 5"), ("give", "light of rdv"), ("give", "star fragment"),
    ("gem", "all perfect"), ("gem", "ruby flawless 2"), ("shard", "all"), ("shard", "bleed rare"),
    ("ingots", "3"), ("key", ""), ("dshard", A_THEME), ("heroicshard", ""), ("egg", "list"), ("egg", FIRST_PET),
    ("pet", FIRST_PET), ("pet", "none"), ("tier", "7"), ("tier", "divine"), ("clearbag", ""), ("clearbag", "all"),
    ("time", ""), ("time", "night"), ("time", "100"), ("day", ""), ("night", ""), ("skip", ""),
    ("bloodmoon", ""), ("bloodmoon", "off"), ("weather", "storm"), ("nightevent", "lamplighter"), ("moon", "4"),
    ("star", "fall"), ("lightning", ""), ("tp", "list"), ("tp", "200 200"), ("tp", "tavern town"), ("tp", "spawn"),
    ("island", ""), ("island", "1"), ("goto", "realm"), ("liveevent", "list"), ("liveevent", "double"),
    ("liveevent", "off"), ("liveevent", "auto"), ("reveal", ""),
    ("spawn", "goblin 3"), ("spawn", "shade_stalker 2 moonlit"), ("spawn", "list"), ("boss", ""), ("killall", ""),
    ("spawn", "goblin 2"), ("clearmobs", ""),
    ("act", ""), ("act", "2"), ("quest", "list"), ("quest", f"give {A_QUEST}"), ("quest", "done all"),
    ("quest", "reset"), ("achievement", "list"), ("achievement", "first_blood"),
    ("fps", ""), ("fps", ""), ("hitboxes", ""), ("hitboxes", "off"),
    ("dungeon", "list"), ("dungeon", f"{A_THEME} hard"), ("goto", "nexus"), ("mgroom", ""), ("goto", "realm"),
    ("goto", "vault"), ("goto", "bazaar"), ("goto", "realm"),
    ("kill", ""),
]


def _bad(res):
    lines = list(res) if res is not None else []
    return [t for t, c in lines if "failed:" in t or t.startswith("Usage:") or t.startswith("No item matches")]


def _sp_game():
    g = main.Game()
    g.player_name = "AdminSP"
    g.start_run("wizard")
    g.enter_realm()
    for _ in range(2):
        g.update(1 / 60)
    return g


def _tick(g, n=3):
    for _ in range(n):
        g.update(1 / 60)


def check_every_command_has_a_sample_and_help():
    names = {c.name for c in admin.COMMANDS.values() if c.admin}
    sampled = {n for n, _a in SAMPLES}
    assert names <= sampled, f"untested commands: {sorted(names - sampled)}"
    for c in admin.COMMANDS.values():
        assert c.usage and c.desc and c.category in dict(admin.CATEGORIES), c.name
    panel = admin.help_panel()
    text = " ".join(t for t, _c in panel)
    for c in admin.COMMANDS.values():
        assert f"/{c.name}" in text, f"/help doesn't list /{c.name}"
    for i, (key, _l) in enumerate(admin.CATEGORIES):
        assert len(admin.help_panel(str(i + 1))) >= 2 and len(admin.help_panel(key)) >= 2, key
    print(f"check_every_command_has_a_sample_and_help: PASSED ({len(names)} admin commands, "
          f"{len(admin.COMMANDS)} total)")


def check_single_player_runs_everything():
    g = _sp_game()
    ctx = admin.SPCtx(g)
    for name, args in SAMPLES:
        if name == "kill":
            g.state = main.STATE_REALM if g.realm_sim is not None else g.state
        res = admin.run(ctx, f"{name} {args}".strip())
        assert res is not None, name
        assert not _bad(res), (name, args, _bad(res))
        g._show_cmd_result(res, name)  # feed or panel - must not crash either way
        if g.state in (main.STATE_REALM, main.STATE_BONUS):
            _tick(g, 2)
        if g.cmd_panel is not None:
            g.draw()
            g.cmd_panel = None
    assert not g.player.alive, "/kill kills"
    print(f"check_single_player_runs_everything: PASSED ({len(SAMPLES)} command lines)")


def check_effects():
    g = _sp_game()
    ctx = admin.SPCtx(g)
    p = g.player
    run = lambda t: admin.run(ctx, t)
    # xp / level
    run("xp 200")
    assert p.level > 1
    run("level 15")
    assert p.level == 15
    # /give fuzzy search
    p.backpack.clear()
    run("give doomstaf")
    assert p.backpack and p.backpack[-1].name == "Doomstaff", [i.name for i in p.backpack]
    run("give perfect ruby x3")
    assert sum(1 for i in p.backpack + p.backpack2 if getattr(i, "gem_kind", None) == "ruby") == 3
    assert admin.find_items("rdv")[0][0] == "Light of RDV"
    assert admin.find_items("sword", tier=7), "tier filter finds a T7 sword"
    run("tier 11")
    assert p.weapon.tier == 11 and p.armor.tier == 11
    # god mode
    run("god on")
    hp = p.hp
    p.take_damage(10 ** 6)
    assert p.hp == hp
    run("god off")
    # speed / noclip
    base = p.speed()
    run("speed 3")
    assert abs(p.speed() - base * 3) < 1e-6
    run("speed 1")
    # time / Blood Moon / weather / night event
    sim = g.realm_sim
    run("time day")
    _tick(g)
    assert sim.phase() == "day"
    run("bloodmoon")
    _tick(g, 4)
    assert sim.is_night and sim.blood_moon_active and sim.night.event == "blood_moon"
    run("bloodmoon off")
    _tick(g, 4)
    assert sim.is_night and not sim.blood_moon_active
    run("weather rain")
    _tick(g)
    assert sim.sky.weather == "rain"
    run("time day")
    _tick(g, 3)
    run("weather storm")
    _tick(g, 4)
    assert sim.is_night and sim.sky.weather == "storm"
    run("nightevent market")
    _tick(g, 4)
    assert sim.night.event == "market" and any(n.npc_id == "ghost_merchant" for n in sim.npcs)
    # spawn / killall
    sim.enemies = []
    run("spawn goblin 4")
    assert sum(1 for e in sim.enemies if e.kind == "goblin") == 4
    kills = p.kills
    run("killall")
    assert not [e for e in sim.enemies if e.alive and not e.neutral] and p.kills >= kills + 4
    # tp
    run("tp 300 310")
    assert int(p.pos.x // TILE) in range(296, 305) and int(p.pos.y // TILE) in range(306, 315)
    run("tp tavern town")
    area = next(a for a in sim.areas if a["key"] == "tavern_town")
    assert area["rect"].inflate(30, 30).collidepoint(int(p.pos.x // TILE), int(p.pos.y // TILE))
    # dungeons
    res = run(f"dungeon {A_THEME} hard")
    assert g.state == main.STATE_BONUS and g.bonus_sim.difficulty["name"] == "Hard", res
    run("goto nexus")
    assert g.state == main.STATE_NEXUS
    run("mgroom")
    assert g.state == main.STATE_BONUS and g.bonus_sim.theme_key == I.MAD_GOD_ROOM_THEME
    run("goto realm")
    assert g.state == main.STATE_REALM
    # reveal + hitboxes draw
    run("reveal")
    run("hitboxes on")
    g.draw()
    if SHOT_DIR:
        pygame.image.save(g.screen, os.path.join(SHOT_DIR, "admin_hitboxes.png"))
    run("hitboxes off")
    # chat path: typing it in the chat box
    g.chat_buffer = "/help"
    g._submit_chat()
    assert g.cmd_panel is not None and "help" in g.cmd_panel["title"]
    g.draw()
    if SHOT_DIR:
        pygame.image.save(g.screen, os.path.join(SHOT_DIR, "admin_help.png"))
    ev = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0)
    used, close = ui.handle_cmd_panel_event(g.cmd_panel, ev)
    assert used and close
    # unknown commands still say so, normal commands still work
    g.feed = []
    g._handle_chat_command("definitelynotacommand")
    assert any("Unknown command" in m[0] for m in g.feed)
    print("check_effects: PASSED")


class FakeSock:
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        for ln in data.decode("utf-8").splitlines():
            if ln.strip():
                self.sent.append(json.loads(ln))


def check_coop_server_admin_gate_and_commands():
    import server
    state = server.ServerState()
    p = Player("warrior", name="AdminCoop", pid="a1")
    p.story = __import__("game.story", fromlist=["StoryProgress"]).StoryProgress(0)
    sock = FakeSock()
    s = server.Session("a1", sock, p)
    state.sessions[s.pid] = s
    s.zone = server.ZONE_REALM
    p.pos = state.realm_sim.spawn_point()
    # refused without --admin
    state.admin = False
    server._apply_action(state, s, {"action": "admin", "text": "xp 500"})
    assert p.level == 1 and "off on this server" in sock.sent[-1]["lines"][0][0]
    # allowed with it
    state.admin = True
    n_ok = 0
    for name, args in SAMPLES:
        cmd = admin.resolve(name)
        if cmd.side == "client":
            continue
        sock.sent.clear()
        if s.zone == server.ZONE_DEAD:
            break
        server._apply_action(state, s, {"action": "admin", "text": f"{name} {args}".strip()})
        assert sock.sent and sock.sent[-1]["type"] == "admin_result", (name, sock.sent)
        lines = sock.sent[-1]["lines"]
        assert not [t for t, _c in lines if "failed:" in t], (name, args, lines)
        n_ok += 1
        server.step(state, 1 / 20)
    assert p.level == 20, p.level  # /maxstats
    assert s.zone == server.ZONE_DEAD, "/kill -> the server's permadeath path"
    print(f"check_coop_server_admin_gate_and_commands: PASSED ({n_ok} server-side command lines)")


def check_coop_client_side_commands():
    class Stub:
        def __init__(self):
            self.you = Player("archer", name="Cli", pid="c1")
            self.zone = "nexus"
            from game import world
            self.nexus_map = world.TileMap(world.make_nexus())
            self.tilemap = None
            self.nexus_minimap = minimap.MinimapState()

        def _current_minimap(self):
            return self.nexus_minimap

    c = Stub()
    ctx = admin.ClientCtx(c)
    for name in ("help", "reveal", "pos", "hitboxes", "fps", "fps"):
        res = admin.run(ctx, name)
        assert res is not None and not _bad(res), (name, res)
    assert c.debug_hitboxes
    assert admin.runs_on_client("reveal") and not admin.runs_on_client("give")
    assert admin.is_admin_command("give") and not admin.is_admin_command("trade")
    print("check_coop_client_side_commands: PASSED")


def check_every_command_has_a_manual_page():
    """/help <command> explains what it does with examples; /help all is the whole manual."""
    from game import admin_manual
    for name, cmd in admin.COMMANDS.items():
        what, examples = admin_manual.MANUAL.get(name, ("", []))
        assert len(what) > 20 and examples, f"/{name} needs a manual entry with examples (game/admin_manual.py)"
        for ex, does in examples:
            assert ex.startswith("/") and does, (name, ex)
        page = [t for t, _c in admin.help_panel(name)]
        assert any(t.startswith("What it does:") for t in page) and "Examples:" in page, name
    full = [t for t, _c in admin.help_panel("all")]
    assert sum(1 for t in full if t.strip().startswith("e.g.")) >= len(admin.COMMANDS)
    for alias in ("man", "helpp", "manual"):
        assert admin.resolve(alias).name == "help"
    print(f"check_every_command_has_a_manual_page: PASSED ({len(admin.COMMANDS)} commands)")


if __name__ == "__main__":
    check_every_command_has_a_manual_page()
    check_every_command_has_a_sample_and_help()
    check_single_player_runs_everything()
    check_effects()
    check_coop_server_admin_gate_and_commands()
    check_coop_client_side_commands()
    print("\nALL ADMIN COMMAND CHECKS PASSED")

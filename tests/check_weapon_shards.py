"""
Weapon Shards (game/runes.py): the Shards tab's 4 ACTIVE sockets add effects to every
shot of the equipped weapon.

- every effect does what it says on hit (bleed/burn/vulnerable/frostbite/chain/keen/
  leech/splinter/seeker/impact/executioner/echo)
- only the 4 ACTIVE sockets count; same-effect copies stack weakly
- old socketed_proc / UT procs still work alongside
- drops from elites/bosses, the Anvil fuses 3 -> next rarity
- items + slots survive a save round-trip; co-op move_item is authoritative

Run with: .venv\\Scripts\\python.exe tests\\check_weapon_shards.py
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("RR_EVENT_ROTATION", "off")  # a "double loot" live event would double the drop rates

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import runes, forge, items as I, sprites, codex
from game.realm_sim import RealmSim
from game.entities import Player, Enemy

SIM = RealmSim(bonus=True, theme="cave", difficulty_name="Easy")
SIM.realm_map.is_solid = lambda *a: False  # the random dungeon layout must not block the test spots


def _hero(*shards):
    p = Player("wizard", "Rune", pid="r")
    p.weapon.min_dmg = p.weapon.max_dmg = 20
    for i, (rar, eff) in enumerate(shards):
        p.rune_slots[i] = runes.make_rune(rar, eff)
    return p


def _hit(p, enemy_hp=10 ** 6, extra=()):
    SIM.enemies = []
    e = Enemy("goblin", pygame.Vector2(500, 500))
    e.hp = e.hp_max = enemy_hp
    others = [Enemy("goblin", pygame.Vector2(560 + 20 * i, 500)) for i in range(extra)] if extra else []
    for o in others:
        o.hp = o.hp_max = 10 ** 6
    SIM.enemies = [e] + others
    p.pos = pygame.Vector2(450, 500)
    b = SIM.player_fire(p, pygame.Vector2(1, 0))[0]
    b.pos = pygame.Vector2(e.pos)
    b.prev_pos = pygame.Vector2(e.pos) - pygame.Vector2(2, 0)
    SIM.bullets = [b]
    SIM.begin_tick()
    SIM._resolve_bullet_hits({p.pid: p})
    return e, others, b


def check_items_and_icons():
    shard = runes.make_rune("epic", "chain")
    assert shard.slot == "rune" and shard.rune_effect == "chain" and shard.color == runes.RARITY_COLORS["epic"]
    assert not shard.display_name.startswith("[T")
    back = I.Item.from_json(json.loads(json.dumps(shard.to_json())))
    assert back.rune_effect == "chain" and back.rune_rarity == "epic"
    icons = {pygame.image.tobytes(sprites.item_icon(runes.RARITY_COLORS["rare"], f"rune_{e}"), "RGBA")
             for e in runes.EFFECT_KEYS}
    assert len(icons) == len(runes.EFFECT_KEYS), "every effect has its own icon"
    assert codex.entry("help:weapon_shards")
    print("check_items_and_icons: PASSED")


def check_active_sockets_and_stacking():
    p = _hero(("common", "keen"), ("epic", "keen"), ("rare", "bleed"), ("rare", "burn"))
    p.rune_slots[4] = runes.make_rune("mythic", "chain")  # storage - doesn't count
    fx = p.active_rune_effects()
    assert set(fx) == {"keen", "bleed", "burn"}
    assert abs(fx["keen"] - (runes.RARITY_MULT["epic"] + runes.RUNE_STACK_BONUS)) < 1e-9
    print("check_active_sockets_and_stacking: PASSED")


def check_effects_on_hit():
    random.seed(4)
    e, _o, _b = _hit(_hero(("rare", "bleed"), ("rare", "burn"), ("rare", "vulnerable"), ("rare", "frostbite")))
    assert e.bleed_time > 0 and e.burn_time > 0 and e.vulnerable_time > 0 and e.slow_time > 0
    assert e.vulnerable_mult > 1.0 and 0 < e.slow_amount <= 0.6
    # chain: arcs to nearby enemies
    e, others, _b = _hit(_hero(("epic", "chain")), extra=3)
    assert sum(1 for o in others if o.hp < o.hp_max) >= 2
    assert any(v[0] == "rune_chain" for v in SIM.vfx_events)
    # keen: crits double the shot
    p = _hero(("mythic", "keen"))
    random.seed(9)
    crits = [SIM.player_fire(p, pygame.Vector2(1, 0))[0].crit for _ in range(300)]
    assert 0.15 < sum(crits) / 300 < 0.4, sum(crits)
    # leech heals the shooter
    p = _hero(("mythic", "leech"))
    p.hp = 10
    _hit(p)
    assert p.hp > 10
    # splinter spawns shards; seeker steers
    _e, _o, _b = _hit(_hero(("epic", "splinter")))
    assert sum(1 for b in SIM.bullets if b.owner == "r") >= 2
    p = _hero(("rare", "seeker"))
    b = SIM.player_fire(p, pygame.Vector2(1, 0))[0]
    assert getattr(b, "seek", 0) > 0
    # impact pushes, executioner adds damage under 30%
    e, _o, _b = _hit(_hero(("mythic", "impact")))
    assert e.pos.x > 500
    p = _hero(("mythic", "executioner"))
    e_low, _o, b = _hit(p, enemy_hp=10 ** 6)
    plain_dmg = e_low.hp_max - e_low.hp
    SIM.enemies = []
    low = Enemy("goblin", pygame.Vector2(500, 500))
    low.hp_max = 10 ** 6
    low.hp = int(low.hp_max * 0.2)
    SIM.enemies = [low]
    b2 = SIM.player_fire(p, pygame.Vector2(1, 0))[0]
    b2.pos = pygame.Vector2(low.pos)
    SIM.bullets = [b2]
    before = low.hp
    SIM._resolve_bullet_hits({p.pid: p})
    assert before - low.hp > plain_dmg, (before - low.hp, plain_dmg)
    # echo: every Nth hit repeats
    p = _hero(("mythic", "echo"))
    n = runes.magnitude("echo", runes.RARITY_MULT["mythic"])
    for _ in range(n):
        _hit(p)
    assert any(v[0] == "rune_echo" for v in SIM.vfx_events)
    print("check_effects_on_hit: PASSED")


def check_old_procs_still_work():
    p = Player("wizard", "Socket", pid="s")
    p.weapon.socketed_proc = "burn"
    p.rune_slots[0] = runes.make_rune("rare", "frostbite")
    b = SIM.player_fire(p, pygame.Vector2(1, 0))[0]
    assert b.status_effect == "burn" and "frostbite" in b.rune_fx
    print("check_old_procs_still_work: PASSED")


def check_drops_and_fusion():
    random.seed(2)
    n = 0
    for _ in range(600):
        n += sum(1 for _b, it in I.roll_loot("wizard", "boss", 1.0) if it.slot == "rune")
    assert 0.15 * 600 < n < 0.4 * 600, n
    elite = sum(1 for _ in range(3000) for _b, it in I.roll_loot("wizard", "elite", 0.5) if it.slot == "rune")
    assert 0.02 * 3000 < elite < 0.07 * 3000, elite
    assert not any(it.slot == "rune" for _ in range(2000) for _b, it in I.roll_loot("wizard", "trash", 0.5))
    p = Player("wizard", "Fuser", pid="f")
    p.backpack = [runes.make_rune("rare", "echo"), runes.make_rune("rare", "burn"), runes.make_rune("rare", "keen")]
    opt = next(o for o in forge.forge_options(p) if o["kind"] == "fuse")
    ok, _msg, res = forge.apply_forge(p, opt)
    assert ok and res.rune_rarity == "epic" and res.rune_effect == "echo" and p.backpack == [res]
    assert runes.fuse_result([runes.make_rune("mythic")] * 3) is None, "mythic is the top"
    print("check_drops_and_fusion: PASSED")


def check_move_rules_save_and_coop():
    p = Player("wizard", "Mover", pid="m")
    shard = runes.make_rune("rare", "chain")
    sword = I._random_tiered("wizard", 5, 5)
    p.backpack = [shard, sword]
    assert not p.move_item(("backpack", 1), ("rune", 0)), "only shards go in shard slots"
    assert p.move_item(("backpack", 0), ("rune", 0)) and p.rune_slots[0] is shard
    assert not p.move_item(("rune", 0), ("equip", "weapon")), "a shard isn't a weapon"
    assert p.move_item(("backpack", 0), ("bag2", 0)) and p.backpack2 == [sword]
    assert not p.move_item(("bag2", 0), ("rune", 3))
    assert p.move_item(("rune", 0), ("rune", 5)) and p.rune_slots[5] is shard and p.rune_slots[0] is None
    state = p.full_state()
    back = Player.from_full_state(json.loads(json.dumps(state)))
    assert back.rune_slots[5].rune_effect == "chain" and back.backpack2[0].name == sword.name
    old = dict(state)
    old.pop("rune_slots")
    old.pop("backpack2")
    legacy = Player.from_full_state(old)
    assert legacy.backpack2 == [] and legacy.rune_slots == [None] * 12, "old saves load"
    import server

    class FakeSock:
        def sendall(self, data):
            pass

    st = server.ServerState()
    s = server.Session("m", FakeSock(), p)
    st.sessions[s.pid] = s
    s.zone = server.ZONE_NEXUS
    server._apply_action(st, s, {"action": "move_item", "from": ["rune", 5], "to": ["rune", 1]})
    assert p.rune_slots[1] is shard
    server._apply_action(st, s, {"action": "move_item", "from": ["bag2", 0], "to": ["rune", 2]})
    assert p.rune_slots[2] is None and p.backpack2 == [sword], "the server enforces the rules"
    server._apply_action(st, s, {"action": "move_item", "from": ["bogus"], "to": None})  # never crashes
    print("check_move_rules_save_and_coop: PASSED")


if __name__ == "__main__":
    check_items_and_icons()
    check_active_sockets_and_stacking()
    check_effects_on_hit()
    check_old_procs_still_work()
    check_drops_and_fusion()
    check_move_rules_save_and_coop()
    print("PASSED: weapon shard checks all green.")

"""
Gem forging (game/gems.py): stones set into weapons at Brother Hammerstein's Anvil -
sockets per tier, set / combine / pry, what each element does on hit and on a kill,
Attuned / Resonant sets, the visuals (icons, bullet trails, aura, veins - cached and
crash-free), drops, gem veins (mining + regrowth), save round-trip and the co-op
Anvil conversation.

Run with: .venv\\Scripts\\python.exe tests\\check_gem_forging.py
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((1366, 820))

from game import accounts, characters, achievements
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_gem_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_gem_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_gem_ach_")

from game import gems as G, gem_art, sprites, items as I, dialogue, vfx, audio, ui
from game import realm_sim as rs
from game.realm_sim import RealmSim
from game.entities import Player, Enemy, Bullet
from game.constants import TILE

random.seed(3)
SIM = RealmSim()


def _weapon(tier, cls="wizard"):
    r = next(r for r in I.WEAPONS[cls] if r[2] == tier)
    return I.Item(r[0], "weapon", tier, r[1], min_dmg=r[3][0], max_dmg=r[3][1])


def _player(tier=10, cls="wizard"):
    p = Player(cls, "Gemma", pid="g1")
    p.weapon = _weapon(tier, cls)
    p.pos = SIM.spawn_point()
    p.hp = p.hp_max = 10 ** 5
    return p


def check_sockets_per_tier():
    assert G.socket_count(_weapon(3)) == 1 and G.socket_count(_weapon(7)) == 2 and G.socket_count(_weapon(11)) == 3
    ut = I.Item("Some UT", "weapon", 0, "staff", is_ut=True, min_dmg=10, max_dmg=20)
    assert G.socket_count(ut) == 2
    assert G.socket_count(I.Item("Ring", "ring", 5, "ring")) == 0
    print("check_sockets_per_tier: PASSED")


def check_anvil_set_combine_pry():
    p = _player(11)
    p.backpack = [G.make_gem("ruby", "flawed") for _ in range(3)] + [G.make_gem("topaz", "flawless")]
    opts = G.stonework_options(p, 10)
    kinds = {o["kind"] for o in opts}
    assert {"set", "combine"} <= kinds, opts
    assert not any(o["kind"] == "set" and o["gem"].gem_grade == "flawless" for o in opts), "flawless needs an ingot"
    p.backpack.append(I.make_forge_ingot())
    o = next(o for o in G.stonework_options(p, 10) if o["kind"] == "set" and o["gem"].gem_kind == "topaz")
    ok, msg, col = G.apply_stonework(p, o)
    assert ok and G.stones_in(p.weapon) == [("topaz", "flawless")] and not any(I_.slot == "material" for I_ in p.backpack)
    o = next(o for o in G.stonework_options(p, 10) if o["kind"] == "combine")
    ok, _m, _c = G.apply_stonework(p, o)
    assert ok and [g.name for g in p.backpack if G.is_gem(g)] == ["Ruby"], [g.name for g in p.backpack]
    o = next(o for o in G.stonework_options(p, 10) if o["kind"] == "pry")
    ok, _m, _c = G.apply_stonework(p, o)
    assert ok and not G.stones_in(p.weapon)
    # fill every socket: no more "set" options
    p.weapon.gems = [["ruby", "regular"]] * 3
    assert not any(o["kind"] == "set" for o in G.stonework_options(p, 10))
    # through the Forge window's catalog (the chat only opens it now)
    from game import forge_menu
    p.weapon.gems = []
    p.backpack = [G.make_gem("sapphire", "regular")]
    o = next(o for o in forge_menu.catalog(p)["stonework"] if o["kind"] == "set")
    res = forge_menu.apply(p, o)
    assert res["ok"] and G.stones_in(p.weapon) == [("sapphire", "regular")] and res["sfx"] == "gem_set"
    print("check_anvil_set_combine_pry: PASSED")


def check_fx_stacking_attuned_resonant():
    w = _weapon(11)
    w.gems = [["ruby", "regular"]]
    assert abs(G.weapon_fx(w)["burn"] - 1.0) < 1e-6
    w.gems = [["ruby", "regular"], ["ruby", "regular"]]
    assert abs(G.weapon_fx(w)["burn"] - 2.0 * G.ATTUNED_MULT) < 1e-6
    w.gems = [["ruby", "regular"]] * 3
    fx = G.weapon_fx(w)
    assert "res_ruby" in fx and abs(fx["burn"] - 3 * G.RESONANT_MULT) < 1e-6
    w.gems = [["amethyst", "perfect"]] * 3
    assert G.weapon_fx(w)["gem_pierce"] == 5
    w.gems = [["sapphire", "flawed"], ["sapphire", "flawed"]]
    assert "gem_shatter" in G.weapon_fx(w)
    m = G.merge_fx({"burn": 1.0}, {"burn": 2.0, "venom": 1.0})
    assert abs(m["burn"] - 2.5) < 1e-6 and m["venom"] == 1.0
    assert any("Resonant" in l for l in G.describe_weapon(type("W", (), {"slot": "weapon", "tier": 11, "is_ut": False,
                                                                           "divine": False,
                                                                           "gems": [["ruby", "regular"]] * 3})()))
    print("check_fx_stacking_attuned_resonant: PASSED")


def _shoot(p, target):
    d = (target.pos - p.pos).normalize()
    SIM.bullets = []
    made = SIM.player_fire(p, d)
    for _ in range(40):
        for b in SIM.bullets:
            b.update(1 / 60)
        SIM._resolve_bullet_hits({p.pid: p})
        if not any(b in SIM.bullets for b in made):
            break
    return made


def check_effects_on_hit_and_kill():
    p = _player(11)
    SIM.enemies = []
    for kind, check in (("ruby", lambda e: e.burn_time > 0), ("sapphire", lambda e: getattr(e, "slow_time", 0) > 0),
                        ("emerald", lambda e: e.bleed_time > 0 and getattr(e, "_venom", 0))):
        p.weapon.gems = [[kind, "regular"]]
        e = Enemy("goblin", p.pos + pygame.Vector2(80, 0))
        e.hp = e.hp_max = 10 ** 5
        SIM.enemies = [e]
        made = _shoot(p, e)
        assert made[0].gem == kind and made[0].color == G.color_of(kind)
        assert check(e), kind
        assert made[0].net_state()["gem"] == kind
    # Resonant ruby: a kill explodes and burns / hurts foes nearby
    p.weapon.gems = [["ruby", "perfect"]] * 3
    victim = Enemy("goblin", p.pos + pygame.Vector2(80, 0))
    victim.hp = 1
    by = Enemy("goblin", victim.pos + pygame.Vector2(30, 0))
    by.hp = by.hp_max = 10 ** 5
    SIM.enemies = [victim, by]
    SIM.vfx_events = []
    _shoot(p, victim)
    assert not victim.alive and by.burn_time > 0 and by.hp < by.hp_max
    assert any(ev[0] == "gem_burst" and ev[4] == "ruby" for ev in SIM.vfx_events)
    # Emerald: the poison spreads when the poisoned foe dies
    p.weapon.gems = [["emerald", "regular"]]
    victim = Enemy("goblin", p.pos + pygame.Vector2(80, 0))
    victim.hp = victim.hp_max = 10 ** 5
    by = Enemy("goblin", victim.pos + pygame.Vector2(40, 0))
    by.hp = by.hp_max = 10 ** 5
    SIM.enemies = [victim, by]
    _shoot(p, victim)
    victim.hp = 1
    SIM._rune_damage(victim, 5, p.pid, {p.pid: p}, (0, 0, 0))
    assert not victim.alive and by.bleed_time > 0 and getattr(by, "_venom", 0)
    # Onyx Resonant: kills heal
    p.weapon.gems = [["onyx", "regular"]] * 3
    p.hp = p.hp_max // 2
    victim = Enemy("goblin", p.pos + pygame.Vector2(80, 0))
    victim.hp = 1
    SIM.enemies = [victim]
    hp0 = p.hp
    _shoot(p, victim)
    assert p.hp > hp0
    # Amethyst adds pierce
    p.weapon.gems = [["amethyst", "regular"]] * 2
    b = SIM.player_fire(p, pygame.Vector2(1, 0))[0]
    assert b.pierce >= 2
    print("check_effects_on_hit_and_kill: PASSED")


def check_visuals_render_and_cache():
    surf = pygame.Surface((400, 300))
    cam = lambda v: (int(v[0]) % 400, int(v[1]) % 300)
    for k in G.KINDS:
        for g in G.GRADES:
            it = G.make_gem(k, g)
            a = sprites.icon_of(it)
            assert a is sprites.icon_of(it), "gem icons are cached"
        w = _weapon(11)
        w.gems = [[k, "flawless"], [k, "regular"]]
        i1 = sprites.icon_of(w)
        assert i1 is sprites.icon_of(w) and i1 is not sprites.item_icon(w.color, w.shape)
        b = Bullet((100, 100), (300, 40), 10, "g1", G.color_of(k), 0, 5, 1.0)
        b.gem = k
        b.draw(surf, cam)
        p = _player(11)
        p.weapon = w
        p.draw(surf, cam)
        vfx.dispatch([("gem_hit", 50, 50, G.color_of(k), k), ("gem_burst", 50, 50, G.color_of(k), k, 80, 80),
                      ("gem_forge", 60, 60, G.color_of(k)), ("gem_mine", 60, 60, G.color_of(k))])
    vfx.update(0.1)
    vfx.draw(surf, cam)
    gem_art.draw_veins(surf, cam, [((50, 50), ["ruby", "topaz"], 2), ((150, 50), ["onyx"], 0)], mining=((50, 50), 0.5))
    ui._tooltip(surf, (100, 100), w)
    for key in ("gem_set", "gem_combine", "gem_pry", "gem_mine"):
        assert key in audio.EVENT_SOUND
        audio.play_event(key)
    print("check_visuals_render_and_cache: PASSED")


def check_drops_and_veins():
    G._DROP_RNG.seed(1)
    got = [G.maybe_drop("boss", "island") for _ in range(400)]
    got = [g for g in got if g]
    assert 70 < len(got) < 180, len(got)
    assert min(G.GRADES.index(g.gem_grade) for g in got) >= 2, "island bosses roll Regular or better"
    assert not any(G.maybe_drop("trash") for _ in range(200))
    drops = [d for _ in range(300) for d in I.roll_loot("wizard", "boss", 1.0)]
    assert any(G.is_gem(it) for _b, it in drops), "bosses drop stones through roll_loot"
    assert len(SIM.gem_veins) >= 10, len(SIM.gem_veins)
    assert {v["biome"] for v in SIM.gem_veins} <= set(G.VEIN_BIOMES)
    p = _player()
    p.backpack = []
    v = SIM.gem_veins[0]
    p.pos = pygame.Vector2(v["pos"]) + pygame.Vector2(20, 0)
    assert SIM.start_mining(p) and SIM.mining_frac(p.pid) == 0.0
    for _ in range(int(G.VEIN_MINE_TIME / 0.05) + 3):
        SIM._tick_mining(0.05, {p.pid: p})
    assert any(G.is_gem(it) for it in p.backpack) and v["charges"] == G.VEIN_CHARGES - 1
    # walking away cancels
    assert SIM.start_mining(p)
    p.pos += pygame.Vector2(400, 0)
    SIM._tick_mining(0.05, {p.pid: p})
    assert SIM.mining_frac(p.pid) is None
    # mine it dry, then it grows back the morning after the next night
    p.pos = pygame.Vector2(v["pos"]) + pygame.Vector2(20, 0)
    while v["charges"] > 0:
        SIM.start_mining(p)
        for _ in range(int(G.VEIN_MINE_TIME / 0.05) + 3):
            SIM._tick_mining(0.05, {p.pid: p})
    assert not SIM.start_mining(p), "a dry vein can't be mined"
    SIM.day_time = 100
    SIM._tick_mining(0.05, {p.pid: p})
    assert v["charges"] == 0, "not before the next night"
    SIM.night_count = getattr(SIM, "night_count", 0) + 1
    SIM._tick_mining(0.05, {p.pid: p})
    assert v["charges"] == G.VEIN_CHARGES
    print(f"check_drops_and_veins: PASSED ({len(SIM.gem_veins)} veins)")


def check_save_round_trip_and_coop():
    p = _player(11)
    p.weapon.gems = [["diamond", "perfect"], ["onyx", "flawed"]]
    p.backpack = [G.make_gem("emerald", "chipped")]
    q = Player.from_full_state(p.full_state())
    assert G.stones_in(q.weapon) == [("diamond", "perfect"), ("onyx", "flawed")]
    assert q.backpack[0].gem_kind == "emerald" and q.backpack[0].name == "Chipped Emerald"
    r = Player.from_net_state(p.net_state())
    assert G.lead_kind(r.weapon) == "diamond", "co-op peers see the stones (aura)"
    old = p.weapon.to_json()
    old.pop("gems")
    assert I.Item.from_json(old).gems == [], "old saves load with no stones"
    # co-op: the server owns the Anvil conversation - stonework runs through it unchanged
    import server
    assert hasattr(server, "_send_dialogue")
    print("check_save_round_trip_and_coop: PASSED")


if __name__ == "__main__":
    check_sockets_per_tier()
    check_anvil_set_combine_pry()
    check_fx_stacking_attuned_resonant()
    check_effects_on_hit_and_kill()
    check_visuals_render_and_cache()
    check_drops_and_veins()
    check_save_round_trip_and_coop()
    print("\nALL GEM FORGING CHECKS PASSED")

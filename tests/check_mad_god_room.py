"""
The Mad God's Room (V0.2 final endgame): the Mad God, then two evolutions.

- the Room Key: a rare drop from Heroic bosses and calmed big islands only; used in
  the Realm it opens a "Godly" portal; level 20 + a T12+ item to get in (single
  player and co-op)
- forms: killing the Mad God raises "Unhinged" on the spot (invulnerable during the
  transform, the room's name and music change, a transform vfx + roar), which
  raises "Absolutely Livid"; only the last form's death ends the room
- every form has its own sprite and move set (with phase-2 moves); the last form
  enrages after MG_LIVID_ENRAGE_AFTER seconds
- loot climbs per form (mg_room_1..3): the last form always drops a Divine item

Run with: .venv\\Scripts\\python.exe tests\\check_mad_god_room.py
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
screen = pygame.display.set_mode((400, 300))

from game import accounts, characters, achievements
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_mgr_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_mgr_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_mgr_ach_")

from game import realm_sim as rs, items as I, gates, story, music, sprites, codex
from game import enemy_attacks as EA
from game.realm_sim import RealmSim, MAD_GOD_ROOM, MG_ROOM_FORMS
from game.entities import Player, ENEMY_KINDS

SHOT_DIR = os.environ.get("RR_SHOT_DIR")


def _hero(name="Champ", tier=12):
    p = Player("warrior", name, pid=name)
    while p.level < 20:
        p.gain_xp(10 ** 5)
    p.story = story.StoryProgress(story.FINAL_ACT)
    r = next(r for r in I.WEAPONS["warrior"] if r[2] == tier)
    p.weapon = I.Item(r[0], I.SLOT_WEAPON, tier, r[1], min_dmg=r[3][0], max_dmg=r[3][1])
    return p


def _kill(sim, enemy, killer):
    enemy.hp = 0
    enemy.alive = False
    sim._reward(enemy, killer)


def _bag_items(sim, pid):
    return [it for bag in sim.ground_items for it in getattr(bag, "items", [])
            if getattr(bag, "owner_pid", None) in (None, pid)]


def check_forms_are_real_bosses():
    for kind in MG_ROOM_FORMS:
        d = ENEMY_KINDS[kind]
        assert d["rank"] == "boss" and d.get("scale") and kind in sprites.BOSS_KINDS, kind
        moves = EA.moves_for(kind)
        assert len({m["name"] for m in moves}) >= 5 or kind == "mad_god", (kind, [m["name"] for m in moves])
        assert any(m.get("phase", 1) == 2 for m in moves), kind
        assert codex.entry(f"enemy:{kind}"), kind
    hp = [ENEMY_KINDS[k]["hp"] for k in MG_ROOM_FORMS]
    assert hp[0] < hp[1] < hp[2], hp
    a, b, c = (pygame.image.tobytes(sprites.enemy_sprite(k), "RGBA") for k in MG_ROOM_FORMS)
    assert len({a, b, c}) == 3, "each form looks different"
    assert codex.entry(f"area:dungeon:{MAD_GOD_ROOM}")
    for key in ("mad_god_room", "mad_god_room_unhinged", "mad_god_room_livid"):
        assert f"dungeon_{key}" in music.TRACKS
    print("check_forms_are_real_bosses: PASSED")


def check_key_sources_and_gate():
    key = I.make_mad_god_key()
    assert key.slot == I.SLOT_SHARD and key.shard_theme == MAD_GOD_ROOM and key.shape == "key"
    assert rs.shard_difficulty(MAD_GOD_ROOM) == "Godly"
    old = rs.MG_KEY_FROM_HEROIC, rs.MG_KEY_FROM_ISLAND
    rs.MG_KEY_FROM_HEROIC = rs.MG_KEY_FROM_ISLAND = 1.0
    try:
        p = _hero("KeyHunter")
        normal = RealmSim(bonus=True, theme="cave", difficulty_name="Hard", story_act=6)
        p.pos = normal.boss.pos + pygame.Vector2(0, 40)
        normal.begin_tick()
        normal.update(0.01, {p.pid: p})
        normal.ground_items = []
        _kill(normal, normal.boss, p)
        assert not any(it.shard_theme == MAD_GOD_ROOM for it in _bag_items(normal, p.pid)), "never from normal"
        hero = RealmSim(bonus=True, theme="heroic_cave", difficulty_name="Heroic", story_act=6)
        p.pos = hero.boss.pos + pygame.Vector2(0, 40)
        hero.begin_tick()
        hero.update(0.01, {p.pid: p})
        hero.ground_items = []
        _kill(hero, hero.boss, p)
        assert any(it.shard_theme == MAD_GOD_ROOM for it in _bag_items(hero, p.pid)), "Heroic bosses can drop it"
    finally:
        rs.MG_KEY_FROM_HEROIC, rs.MG_KEY_FROM_ISLAND = old
    # the gate: level 20 AND a T12+ item
    low = Player("warrior", "Low", pid="low")
    assert gates.can_enter(low, MAD_GOD_ROOM)[0] is False
    assert gates.can_enter(_hero("NoGear", tier=11), MAD_GOD_ROOM)[0] is False
    ok, msg = gates.can_enter(_hero("Geared", tier=12), MAD_GOD_ROOM)
    assert ok and not msg
    print("check_key_sources_and_gate: PASSED")


def check_three_forms_back_to_back():
    random.seed(9)
    sim = RealmSim(bonus=True, theme=MAD_GOD_ROOM, difficulty_name="Godly", story_act=story.FINAL_ACT)
    assert sim.is_mg_room and sim.boss.kind == "mad_god" and sim.phase2_quest is None and sim.secret_quest is None
    assert sim.boss.hp_max == int(ENEMY_KINDS["mad_god"]["hp"] * 3.0 * story.act_scale(story.FINAL_ACT))
    p = _hero("Slayer")
    p.pos = sim.boss.pos + pygame.Vector2(0, 90)
    sim.begin_tick()
    sim.update(0.01, {p.pid: p})
    seen_music = [sim.music_key]
    for i, kind in enumerate(MG_ROOM_FORMS):
        boss = sim.boss
        assert boss.kind == kind and boss.loot_source == f"mg_room_{i + 1}", (boss.kind, boss.loot_source)
        sim.ground_items = []
        sim.begin_tick()
        _kill(sim, boss, p)
        items = _bag_items(sim, p.pid)
        if i < 2:
            nxt = sim.boss
            assert nxt is not None and nxt.kind == MG_ROOM_FORMS[i + 1], "the next form rises on the spot"
            assert nxt.pos.distance_to(boss.pos) < 1 and nxt._phase_invuln > 0
            assert nxt.take_damage(10 ** 6) is False, "invulnerable during the transform"
            assert any(ev[0] == "mg_transform" for ev in sim.vfx_events)
            assert any(ev[0] == "sfx" and ev[1] == "mg_transform" for ev in sim.sound_events)
            assert sim.theme_name == rs.mg_room_title(nxt.kind) and sim.theme_name != "The Mad God's Room"
            assert not any(pt.kind == "realm_exit" for pt in sim.portals), "the room isn't over yet"
            assert any(it.tier in (12, 13) and not it.divine for it in items), [it.display_name for it in items]
            seen_music.append(sim.music_key)
            if SHOT_DIR:
                import main
                g = main.Game()
                g.player_name = "Shot"
                g.start_run("warrior")
                g.bonus_sim = sim
                from game import minimap
                g.bonus_minimap = minimap.MinimapState()
                g.player.pos = nxt.pos + pygame.Vector2(0, 120)
                g.state = main.STATE_BONUS
                nxt._phase_invuln = 0
                for _ in range(3):
                    g.update(1 / 60)
                g.draw()
                pygame.image.save(g.screen, os.path.join(SHOT_DIR, f"mg_room_{nxt.kind}.png"))
        else:
            assert sim.boss is None and any(pt.kind == "realm_exit" for pt in sim.portals)
            assert any(it.divine for it in items), "the last form always drops a Divine item"
            assert any(it.tier == 13 for it in items)
    assert len(set(seen_music)) == 3 and all(f"dungeon_{k}" in music.TRACKS for k in seen_music), seen_music
    for k in seen_music:
        assert music.dungeon_zone_for_key(k) == f"dungeon_{k}"
    assert music.dungeon_zone_for_label("The Mad God's Room: Absolutely Livid") == "dungeon_mad_god_room_livid"
    print("check_three_forms_back_to_back: PASSED")


def check_livid_enrages():
    sim = RealmSim(bonus=True, theme=MAD_GOD_ROOM, difficulty_name="Godly", story_act=story.FINAL_ACT)
    p = _hero("Timer")
    _kill(sim, sim.boss, p)
    _kill(sim, sim.boss, p)
    livid = sim.boss
    assert livid.kind == "mad_god_livid"
    before = livid.fire_rate_mult
    sim._tick_mg_room(rs.MG_LIVID_ENRAGE_AFTER - 1)
    assert livid.fire_rate_mult == before
    sim._tick_mg_room(2.0)
    assert livid.fire_rate_mult < before and sim._mg_enraged
    sim._tick_mg_room(50.0)
    assert livid.fire_rate_mult == before * 0.6, "enrages once"
    print("check_livid_enrages: PASSED")


def check_coop_room():
    import server
    from game.entities import Portal

    class FakeSock:
        def sendall(self, data):
            pass

    state = server.ServerState()
    p = Player("warrior", name="CoopGod", pid="m1")
    p.story = story.StoryProgress(story.FINAL_ACT)
    s = server.Session("m1", FakeSock(), p)
    state.sessions[s.pid] = s
    s.zone = server.ZONE_REALM
    pt = Portal(pygame.Vector2(0, 0), theme=MAD_GOD_ROOM, kind="dungeon_shard", difficulty="Godly")
    s.portal_prompt = (MAD_GOD_ROOM, "dungeon_shard", "Godly", id(pt), None)
    server._apply_action(state, s, {"action": "enter_portal"})
    assert s.zone == server.ZONE_REALM and s.story_feed, "a level-1 is refused"
    hero = _hero("CoopGod")
    s.player = hero
    s.portal_prompt = (MAD_GOD_ROOM, "dungeon_shard", "Godly", id(pt), None)
    server._apply_action(state, s, {"action": "enter_portal"})
    assert s.zone == server.ZONE_BONUS
    sim = state.bonus_sims[s.bonus_sim_id]
    assert sim.is_mg_room
    sim.begin_tick()
    _kill(sim, sim.boss, hero)
    snap = server._snapshot_for(state, s)
    assert snap["theme_name"] == "The Mad God's Room: Unhinged"
    assert any(v[0] == "mg_transform" for v in snap["vfx"]) and any(sd[1] == "mg_transform" for sd in snap["sound"])
    print("check_coop_room: PASSED")


if __name__ == "__main__":
    check_forms_are_real_bosses()
    check_key_sources_and_gate()
    check_three_forms_back_to_back()
    check_livid_enrages()
    check_coop_room()
    print("PASSED: Mad God's Room checks all green.")

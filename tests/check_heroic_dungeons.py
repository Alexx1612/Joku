"""
Heroic dungeons (V0.2 final): every dungeon has a much harder Heroic version,
unlocked by that dungeon's Heroic trial side quest.

- 7 Heroic themes (all but the story Forge): elite-only rooms, more rooms, the
  never-rolled "Heroic" difficulty (3.6x HP), faster/denser fire, own music
  track, crimson tint, codex entries
- the trial: offered by the dungeon's local, relics drop only inside that
  dungeon (boss: 1, Hard: 2), turning in unlocks the theme + hands out a first
  Heroic Shard + counts for Act III
- Heroic Shards: always open at "Heroic"; re-drop from Hard clears of unlocked
  themes and from Heroic bosses; Heroic kills roll the "heroic" loot source and
  count for Act IV
- the level gate (16+) in single-player and co-op

Run with: .venv\\Scripts\\python.exe tests\\check_heroic_dungeons.py
"""
import json
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
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_heroic_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_heroic_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_heroic_ach_")

from game import realm_sim as rs, sidequests as sq, npcs, dialogue, story, gates, music, codex, vfx
from game.realm_sim import RealmSim, DUNGEON_THEMES
from game.entities import Player, ENEMY_KINDS

SHOT_DIR = os.environ.get("RR_SHOT_DIR")


def _player(name, level=20, act=story.ACT_GEAR):
    p = Player("wizard", name, pid=name)
    while p.level < level:
        p.gain_xp(10 ** 5)
    p.level = level  # one big XP chunk overshoots - the gates only read the level
    p.story = story.StoryProgress(act)
    p.sidequests = sq.SideQuestProgress()
    return p


def _kill(sim, enemy, killer):
    enemy.hp = 0
    enemy.alive = False
    sim._reward(enemy, killer)


def _bag_items(sim, pid=None):
    return [it for bag in sim.ground_items for it in getattr(bag, "items", [])
            if pid is None or getattr(bag, "owner_pid", None) in (None, pid)]


def check_heroic_themes():
    heroics = [k for k, t in DUNGEON_THEMES.items() if t.get("heroic")]
    assert sorted(heroics) == sorted("heroic_" + b for b in rs.HEROIC_BASES), heroics
    assert "heroic_forge" not in DUNGEON_THEMES
    for k in heroics:
        t = DUNGEON_THEMES[k]
        base = DUNGEON_THEMES[t["base"]]
        assert t["label"] == base["label"] + " (Heroic)" and t["bosses"] == base["bosses"]
        assert all(ENEMY_KINDS[m]["rank"] == "elite" for m in t["kinds"]), (k, t["kinds"])
        assert music.dungeon_zone_for_key(k) == f"dungeon_{k}" and music.dungeon_zone_for_label(t["label"]) == f"dungeon_{k}"
        assert codex.entry(f"area:dungeon:{k}") and "Heroic" in codex.entry(f"area:dungeon:{k}")["text"]
    titles = [music.TRACKS[f"dungeon_{k}"]["title"] for k in heroics]
    assert len(set(titles)) == len(titles)
    for _ in range(200):
        assert rs.shard_difficulty("cave") in ("Easy", "Medium", "Hard")
    assert rs.shard_difficulty("heroic_cave") == "Heroic"
    print("check_heroic_themes: PASSED")


def check_heroic_instance_is_much_harder():
    random.seed(5)
    normal = RealmSim(bonus=True, theme="jungle_ruins", difficulty_name="Hard", story_act=3)
    random.seed(5)
    hero = RealmSim(bonus=True, theme="heroic_jungle_ruins", difficulty_name="Heroic", story_act=3)
    assert hero.is_heroic and hero.base_theme == "jungle_ruins" and hero.loot_source == "heroic"
    assert hero.difficulty["name"] == "Heroic" and hero.difficulty["enemy_scale"] >= 3.5
    kind = hero.boss.kind
    assert hero.boss.hp_max == int(ENEMY_KINDS[kind]["hp"] * 3.6 * story.act_scale(3)), hero.boss.hp_max
    assert len(hero.rooms) > len(normal.rooms), (len(hero.rooms), len(normal.rooms))
    assert all(e.rank in ("elite", "boss") for e in hero.enemies if e.kind != "totem"), \
        sorted({(e.kind, e.rank) for e in hero.enemies})
    p = _player("Tank")
    p.pos = hero.spawn_point()
    hero.begin_tick()
    hero.update(0.01, {p.pid: p})
    assert all(getattr(e, "_heroic", False) and e.bullet_speed_mult == rs.HEROIC_BULLET_SPEED for e in hero.enemies)
    # its bullets really are faster than the same move's in a normal dungeon
    from game import enemy_attacks as EA
    from game.entities import Enemy
    m = next(x for x in hero.boss._attacks if x["fn"] == "fan")
    plain = Enemy(kind, pygame.Vector2(hero.boss.pos))
    shots = []
    for e in (hero.boss, plain):
        out = []
        EA.execute(e, m, EA.AttackCtx(pygame.Vector2(1, 0), pygame.Vector2(100, 0), pygame.Vector2(100, 0),
                                      None, None, out))
        shots.append(out[0].vel.length())
    assert shots[0] > shots[1] * 1.2, shots
    if SHOT_DIR:
        screen2 = pygame.Surface((400, 300))
        screen2.fill((70, 90, 70))
        vfx.draw_heroic_tint(screen2)
        pygame.image.save(screen2, os.path.join(SHOT_DIR, "heroic_tint.png"))
    print("check_heroic_instance_is_much_harder: PASSED")


def check_trial_quest_unlocks_the_heroic_dungeon():
    theme = "cave"
    qid, giver, relic, label = sq.HEROIC_TRIALS[theme]
    assert len(sq.QUESTS) == 37 and all(sq.HEROIC_TRIALS[t][0] in sq.QUESTS for t in sq.HEROIC_TRIALS)
    p = _player("Trialist")
    assert not sq.heroic_unlocked(p.sidequests, theme)
    conv = dialogue.start_conversation(p, npc=npcs.NPC(giver, pygame.Vector2(0, 0)))
    labels = conv.view()["options"]
    idx = next(i for i, o in enumerate(labels) if o.startswith("Heroic trial"))
    conv.choose(idx)
    conv.choose(0)  # "I'll do it!"
    assert qid in p.sidequests.active
    # relics only drop inside THAT dungeon: none from the open Realm, none from another theme
    assert sq.quest_drops(p.sidequests, p, "cave_lurker", "cave", "elite") == []
    assert sq.quest_drops(p.sidequests, p, "void_reaper", None, "boss", theme="frozen_crypt", is_boss=True) == []
    # a Hard clear's boss drops 2, an Easy one 1
    hard = RealmSim(bonus=True, theme=theme, difficulty_name="Hard", story_act=3)
    p.pos = hard.boss.pos + pygame.Vector2(0, 40)
    hard.begin_tick()
    hard.update(0.01, {p.pid: p})
    hard.ground_items = []
    _kill(hard, hard.boss, p)
    got = [it for it in _bag_items(hard, p.pid) if it.quest_key == relic]
    assert len(got) == 2, len(got)
    p.backpack.extend(got)
    easy = RealmSim(bonus=True, theme=theme, difficulty_name="Easy", story_act=3)
    p.pos = easy.boss.pos + pygame.Vector2(0, 40)
    easy.begin_tick()
    easy.update(0.01, {p.pid: p})
    easy.ground_items = []
    _kill(easy, easy.boss, p)
    got = [it for it in _bag_items(easy, p.pid) if it.quest_key == relic]
    assert len(got) == 1
    p.backpack.extend(got)
    assert p.sidequests.ready(qid, p)
    # turn in -> unlocked, relics taken, a Heroic Shard handed over, Act III credit
    conv = dialogue.start_conversation(p, npc=npcs.NPC(giver, pygame.Vector2(0, 0)))
    conv.choose(0)  # "I've done what you asked."
    assert sq.heroic_unlocked(p.sidequests, theme)
    assert not any(it.quest_key == relic for it in p.backpack)
    shards = [it for it in p.backpack if it.slot == "shard" and it.shard_theme == "heroic_cave"]
    assert len(shards) == sq.TRIAL_HEROIC_SHARDS and "Heroic" in shards[0].name
    assert p.story.done.get("gear_heroic_unlock") == [theme], p.story.done
    # the unlock survives a save round-trip
    back = sq.SideQuestProgress.from_json(json.loads(json.dumps(p.sidequests.to_json())))
    assert sq.heroic_unlocked(back, theme) and not sq.heroic_unlocked(back, "ember_den")
    print("check_trial_quest_unlocks_the_heroic_dungeon: PASSED")


def check_heroic_shard_drops_and_heroic_loot():
    p = _player("Farmer", act=story.ACT_DEEP)
    p.sidequests.done.append(sq.HEROIC_TRIALS["ember_den"][0])
    old = rs.HEROIC_SHARD_FROM_HARD, rs.HEROIC_SHARD_FROM_HEROIC
    rs.HEROIC_SHARD_FROM_HARD = rs.HEROIC_SHARD_FROM_HEROIC = 1.0
    try:
        # an unlocked theme's Hard clear re-drops a Heroic Shard; a locked theme never does
        for theme, want in (("ember_den", 1), ("sunken_grotto", 0)):
            sim = RealmSim(bonus=True, theme=theme, difficulty_name="Hard", story_act=4)
            p.pos = sim.boss.pos + pygame.Vector2(0, 40)
            sim.begin_tick()
            sim.update(0.01, {p.pid: p})
            sim.ground_items = []
            _kill(sim, sim.boss, p)
            n = sum(1 for it in _bag_items(sim, p.pid) if it.shard_theme == "heroic_" + theme)
            assert n == want, (theme, n)
        # a Heroic boss: re-drops its shard, rolls the heroic source (a T11+ guaranteed, mythic odds),
        # and counts for Act IV
        sim = RealmSim(bonus=True, theme="heroic_ember_den", difficulty_name="Heroic", story_act=4)
        p.pos = sim.boss.pos + pygame.Vector2(0, 40)
        sim.begin_tick()
        sim.update(0.01, {p.pid: p})
        sim.ground_items = []
        _kill(sim, sim.boss, p)
        items = _bag_items(sim, p.pid)
        assert any(it.shard_theme == "heroic_ember_den" for it in items)
        assert any(it.tier >= 11 and not it.is_ut and it.slot in ("weapon", "armor", "ring", "ability")
                   for it in items), [it.display_name for it in items]
        assert not any(it.quest_key for it in items), "no trial relics from the Heroic version"
        assert len(p.story.done.get("heroic_dungeons", [])) == 1, p.story.done  # every Heroic clear counts
    finally:
        rs.HEROIC_SHARD_FROM_HARD, rs.HEROIC_SHARD_FROM_HEROIC = old
    print("check_heroic_shard_drops_and_heroic_loot: PASSED")


def check_level_gate_single_player_and_coop():
    assert gates.can_enter(_player("Kid", level=15), "heroic_cave")[0] is False
    assert gates.can_enter(_player("Vet", level=16), "heroic_cave")[0] is True
    assert gates.can_enter(_player("Kid2", level=5), "cave")[0] is True  # normal dungeons stay open
    import main
    g = main.Game()
    g.player_name = "GateSP"
    g.start_run("wizard")
    g.player.story = story.StoryProgress(story.ACT_DEEP)
    g.state = main.STATE_REALM
    g.enter_bonus_room(theme="heroic_cave", difficulty="Heroic")
    assert g.state == main.STATE_REALM and g.bonus_sim is None, "a level-1 hero bounces off"
    while g.player.level < gates.HEROIC_LEVEL:
        g.player.gain_xp(10 ** 5)
    g.enter_bonus_room(theme="heroic_cave", difficulty="Heroic")
    assert g.state == main.STATE_BONUS and g.bonus_sim.is_heroic
    for _ in range(3):
        g.update(1 / 60)
    g.draw()
    if SHOT_DIR:
        pygame.image.save(g.screen, os.path.join(SHOT_DIR, "heroic_dungeon_sp.png"))
    # co-op: the server refuses (and tells the player), then lets a level-16 in
    import server
    from game.entities import Portal

    class FakeSock:
        def sendall(self, data):
            pass

    state = server.ServerState()
    p = Player("wizard", name="GateCoop", pid="g1")
    p.story = story.StoryProgress(story.ACT_DEEP)
    s = server.Session("g1", FakeSock(), p)
    state.sessions[s.pid] = s
    s.zone = server.ZONE_REALM
    pt = Portal(pygame.Vector2(0, 0), theme="heroic_cave", kind="dungeon_shard", difficulty="Heroic")
    s.portal_prompt = ("heroic_cave", "dungeon_shard", "Heroic", id(pt), None)
    server._apply_action(state, s, {"action": "enter_portal"})
    assert s.zone == server.ZONE_REALM and any("level" in m for m, _c in s.story_feed)
    while p.level < gates.HEROIC_LEVEL:
        p.gain_xp(10 ** 5)
    s.portal_prompt = ("heroic_cave", "dungeon_shard", "Heroic", id(pt), None)
    server._apply_action(state, s, {"action": "enter_portal"})
    assert s.zone == server.ZONE_BONUS and state.bonus_sims[s.bonus_sim_id].is_heroic
    print("check_level_gate_single_player_and_coop: PASSED")


def check_heroic_boss_sprites():
    """Heroic bosses get their own look (obsidian/crimson recolour, glowing rim, spiked crown),
    the same size as the normal sprite; normal mobs keep theirs (they get the aura only)."""
    from game import sprites
    from game.entities import Enemy
    bosses = sorted({b for t in DUNGEON_THEMES.values() if t.get("heroic") for b in t["bosses"]})
    for kind in bosses + [f"{k}_phase2" for k in bosses]:
        for scale in (1.0, 2.0):
            a, b = sprites.enemy_sprite(kind, scale), sprites.heroic_sprite(kind, scale)
            assert a.get_size() == b.get_size(), (kind, a.get_size(), b.get_size())
            assert pygame.image.tobytes(a, "RGBA") != pygame.image.tobytes(b, "RGBA"), kind
        assert sprites.heroic_sprite(kind, 2.0) is sprites.heroic_sprite(kind, 2.0), "cached"
    # the draw path picks it for a Heroic boss only
    surf = pygame.Surface((400, 300), pygame.SRCALPHA)
    cam = lambda p: (int(p[0]), int(p[1]))
    calls = []
    real = sprites.heroic_sprite
    sprites.heroic_sprite = lambda k, sc=1.0: calls.append(k) or real(k, sc)
    try:
        boss = Enemy("frost_monarch", pygame.Vector2(200, 150))
        mob = Enemy("yeti", pygame.Vector2(100, 150))
        for e in (boss, mob):
            e._heroic = True
            e.draw(surf, cam)
        plain = Enemy("frost_monarch", pygame.Vector2(200, 150))
        plain.draw(surf, cam)
    finally:
        sprites.heroic_sprite = real
    assert calls == ["frost_monarch"], calls
    if SHOT_DIR:
        sheet = pygame.Surface((160 * len(bosses), 330))
        sheet.fill((70, 90, 70))
        for i, k in enumerate(bosses):
            sheet.blit(sprites.enemy_sprite(k, 2.0), (i * 160 + 4, 4))
            sheet.blit(sprites.heroic_sprite(k, 2.0), (i * 160 + 4, 168))
        pygame.image.save(sheet, os.path.join(SHOT_DIR, "heroic_boss_sprites.png"))
    print(f"check_heroic_boss_sprites: PASSED ({len(bosses) * 2} boss kinds)")


if __name__ == "__main__":
    check_heroic_themes()
    check_heroic_instance_is_much_harder()
    check_trial_quest_unlocks_the_heroic_dungeon()
    check_heroic_shard_drops_and_heroic_loot()
    check_level_gate_single_player_and_coop()
    check_heroic_boss_sprites()
    print("PASSED: heroic dungeon checks all green.")

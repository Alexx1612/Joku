"""
Regression checks for the story / critical-path system (game/story.py and its
hooks in realm_sim.py, main.py, server.py, coop_client.py): act transitions,
account-wide act checkpoints vs per-character objective progress (and what
permadeath resets), the island idx fix, Landmark Guardians, story credit via
the real RealmSim._reward path, act difficulty scaling, the Forge / Mad God
finale, the co-op snapshot's quest_log, and the single-player HUD drawing.

Set RR_SHOT_DIR to also save screenshots of the quest log, banner, Father
Given talking, the Forge and the credits.

Run with: .venv\\Scripts\\python.exe tests\\check_story.py
"""
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((100, 100))

from game import accounts, characters, achievements, story, world
from game import realm_sim as rs
from game.realm_sim import RealmSim, FORGE_DIFFICULTY, ISLAND_NAMES, ISLAND_MINI_BOSS
from game.entities import Player, Enemy, ENEMY_KINDS

accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_story_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_story_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_story_ach_")
SHOT_DIR = os.environ.get("RR_SHOT_DIR")

_REALM = None


def _realm():
    global _REALM
    if _REALM is None:
        _REALM = RealmSim()
    return _REALM


def _player(name, act=0, pid=None):
    p = Player("wizard", name=name, pid=pid or name)
    p.story = story.StoryProgress(act)
    return p


def _kill(sim, enemy, killer):
    enemy.hp = 0
    enemy.alive = False
    sim._reward(enemy, killer)


def _shot(surf, name):
    if SHOT_DIR:
        os.makedirs(SHOT_DIR, exist_ok=True)
        pygame.image.save(surf, os.path.join(SHOT_DIR, name))


def check_transitions_through_every_act():
    sp = story.StoryProgress()
    assert sp.act == 0 and sp.wants("talk") and not sp.wants("island", 3)
    sp.on_event("talk")
    sp.on_event("talk")  # a repeat never double-counts
    assert sp.act == 0
    sp.on_event("zone", "bazaar")  # wrong key ignored
    assert sp.act == 0
    sp.on_event("zone", "realm")
    assert sp.act == 1 and sp.just_completed == [0] and sp.done == {}
    for b in story.OUTER_BIOMES:
        assert sp.wants("guardian", b)
        sp.on_event("guardian", b)
    assert not sp.wants("guardian", "cave") or sp.act != 1
    assert sp.act == 2
    n = story.ISLANDS_NEEDED
    for idx in [0] + list(range(n - 1)):  # a repeated island doesn't count twice
        sp.on_event("island", idx)
    assert sp.act == 2 and sp.quest_log()["objectives"][0]["have"] == n - 1
    sp.on_event("island", 9)
    assert sp.act == 3
    sp.on_event("guardian", "forest")  # outer biome doesn't count for Act III
    inner = ["cave"] + list(story.INNER_BIOMES[:story.INNER_GUARDIANS_NEEDED])  # repeat cave: no double count
    for b in inner:
        sp.on_event("guardian", b)
    log = sp.quest_log()
    assert log["objectives"][0]["have"] == story.INNER_GUARDIANS_NEEDED and log["objectives"][1]["have"] == 0
    for _ in range(story.DUNGEONS_NEEDED):
        sp.on_event("dungeon")
    assert sp.act == 4
    assert sp.quest_log()["title"] == story.ACTS[4]["title"]
    msgs = sp.on_event("mad_god")
    assert sp.finished and sp.act == story.FINAL_ACT and sp.just_completed == [0, 1, 2, 3, 4]
    assert any(story.ACTS[4]["done"] in m for m, _c in msgs)
    assert sp.quest_log()["title"] == story.FREE_PLAY_TITLE and sp.on_event("talk") == []
    assert story.act_scale(0) == 1.0 and story.act_scale(3) > story.act_scale(1)
    heard = set()
    first = story.given_line(story.StoryProgress(2), heard)
    assert story.ACTS[2]["intro"] in first and story.given_line(story.StoryProgress(2), heard) == story.ACTS[2]["hint"]
    print("check_transitions_through_every_act: PASSED")


def check_account_act_persistence():
    accounts.touch_account("OldTimer")  # an old account has no story_act key
    assert accounts.get_story_act("OldTimer") == 0
    assert accounts.set_story_act("OldTimer", 2) == 2
    assert accounts.set_story_act("OldTimer", 1) == 2  # never lowered
    assert accounts.get_story_act("OldTimer") == 2
    assert accounts.get_story_act("NobodyYet") == 0
    print("check_account_act_persistence: PASSED")


def check_character_progress_and_permadeath():
    accounts.set_story_act("Hero", 1)
    p = _player("Hero", act=1)
    p.story.on_event("guardian", "forest")
    characters.save_character("Hero", p)
    saved = characters.load_character("Hero")
    back = Player.from_full_state(dict(saved, pid="x", name="Hero"))
    back.story = story.StoryProgress.from_json(saved.get("story"), accounts.get_story_act("Hero"))
    assert back.story.act == 1 and back.story.done == {"guardian_forest": ["forest"]}
    # an old save with no "story" key loads fine and starts the account's act
    legacy = dict(saved)
    legacy.pop("story")
    old = Player.from_full_state(dict(legacy, pid="y", name="Hero"))
    assert old.story.act == 0
    assert story.StoryProgress.from_json(legacy.get("story"), 1).act == 1
    # a save behind the account checkpoint is raised to it
    assert story.StoryProgress.from_json({"act": 0, "done": {"talk_given": [0]}}, 2).to_json() == {"act": 2, "done": {}}
    # permadeath: the character (and its in-act progress) is gone, the act checkpoint stays
    characters.delete_character("Hero")
    assert characters.load_character("Hero") is None
    fresh = story.StoryProgress.from_json(None, accounts.get_story_act("Hero"))
    assert fresh.act == 1 and fresh.done == {}
    print("check_character_progress_and_permadeath: PASSED")


def check_island_idx_survives_a_skipped_placement():
    real = world.coastline_radius
    # the island centre is placed at coast + water gap + island radius (Batch 15 big islands)
    gap = rs.ISLAND_WATER_GAP + world.ISLAND_RADIUS
    n = len(ISLAND_NAMES)

    def fake(angle, info=None):
        i = round(angle * n / (2 * math.pi)) % n
        # every odd island lands on the map centre -> all but the first are skipped as "too close"
        return -gap if i % 2 == 1 else real(angle, info)

    world.coastline_radius = fake
    try:
        sim = RealmSim()
    finally:
        world.coastline_radius = real
    idxs = [isl["idx"] for isl in sim.islands]
    assert len(sim.islands) < n, idxs  # the forced skip really happened
    assert idxs != list(range(len(idxs))), idxs
    for slot, isl in enumerate(sim.islands):
        assert isl["slot"] == slot
        assert ISLAND_NAMES.index(isl["label"]) == isl["idx"]
    # a later island's guardians report back to the right island
    isl = sim.islands[-1]
    sim._tick_island_events(0.0)
    wave = [e for e in sim.enemies if getattr(e, "island_idx", None) == isl["slot"]]
    assert wave and wave[0].kind == ISLAND_MINI_BOSS[isl["idx"]]
    killer = _player("IslandKid", act=2)
    sim._story_players = [killer]
    for e in wave:
        _kill(sim, e, killer)
    assert isl["alive_guardians"] == 0 and killer.story.done["islands"] == [isl["idx"]]
    print("check_island_idx_survives_a_skipped_placement: PASSED")


def check_landmark_guardian():
    sim = _realm()
    lm_idx, lm = next((i, l) for i, l in enumerate(sim.landmarks) if l["biome"] == "forest")
    sim.enemies = []
    tourist = _player("Tourist", act=2)  # Act II doesn't need landmarks
    tourist.pos = pygame.Vector2(lm["pos"])
    sim.begin_tick()
    sim.update(0.01, {tourist.pid: tourist})
    assert not any(getattr(e, "story_guardian", None) for e in sim.enemies)
    hero = _player("Ranger", act=1)
    hero.pos = pygame.Vector2(lm["pos"])
    players = {hero.pid: hero}
    for _ in range(3):  # standing there several ticks still wakes exactly one
        sim.begin_tick()
        sim.update(0.01, players)
    guardians = [e for e in sim.enemies if getattr(e, "story_guardian", None) == "forest"]
    assert len(guardians) == 1, len(guardians)
    g = guardians[0]
    base = ENEMY_KINDS[story.GUARDIAN_KIND["forest"]]["hp"]
    assert g.hp_max == int(base * rs.LANDMARK_GUARDIAN_HP_SCALE * story.act_scale(1)), (g.hp_max, base)
    _kill(sim, g, hero)
    assert hero.story.done.get("guardian_forest") == ["forest"]
    sim.enemies = [e for e in sim.enemies if e.alive]
    sim.begin_tick()
    sim.update(0.01, players)  # already done for this player - no respawn
    assert not any(getattr(e, "story_guardian", None) for e in sim.enemies)
    # a second player who still needs it can wake it again
    other = _player("Latecomer", act=1)
    other.pos = pygame.Vector2(lm["pos"])
    sim.begin_tick()
    sim.update(0.01, {other.pid: other})
    assert sum(1 for e in sim.enemies if getattr(e, "story_guardian", None) == "forest") == 1
    assert sim._landmark_guardians[lm_idx].alive
    sim.enemies = []
    # an INNER Landmark Guardian always drops a Dungeon Shard (Act III's dungeons
    # shouldn't hinge on the 8% elite roll)
    inner = next((l for l in sim.landmarks if l["biome"] in story.INNER_BIOMES), None)
    if inner is not None:
        delver = _player("Delver", act=3)
        delver.pos = pygame.Vector2(inner["pos"])
        sim.ground_items = []
        sim.begin_tick()
        sim.update(0.01, {delver.pid: delver})
        ig = next(e for e in sim.enemies if getattr(e, "story_guardian", None) == inner["biome"])
        _kill(sim, ig, delver)
        dropped = [it for bag in sim.ground_items for it in getattr(bag, "items", [])]
        assert any(it.slot == "shard" for it in dropped), [it.name for it in dropped]
        sim.enemies = []
    print("check_landmark_guardian: PASSED")


def check_dungeon_clear_and_act_scale():
    easy = RealmSim(bonus=True, theme="cave", difficulty_name="Easy", story_act=0)
    hard_story = RealmSim(bonus=True, theme="cave", difficulty_name="Easy", story_act=3)
    base = ENEMY_KINDS["void_reaper"]["hp"]
    assert easy.boss.hp_max == int(base * 1.15)
    assert hard_story.boss.hp_max == int(base * 1.15 * story.act_scale(3))
    diver = _player("Diver", act=3)
    diver.pos = hard_story.boss.pos + pygame.Vector2(0, 40)
    hard_story.begin_tick()
    hard_story.update(0.01, {diver.pid: diver})
    _kill(hard_story, hard_story.boss, diver)
    assert len(diver.story.done.get("dungeons", [])) == 1
    # the realm refreshes its scale from the furthest-along player present
    sim = _realm()
    far = _player("FarAlong", act=4)
    far.pos = sim.spawn_point()
    sim.begin_tick()
    sim.update(0.01, {far.pid: far})
    assert sim.story_scale == story.act_scale(4)
    print("check_dungeon_clear_and_act_scale: PASSED")


def check_forge_finale():
    fsim = RealmSim(bonus=True, theme="forge", difficulty_name=FORGE_DIFFICULTY, story_act=4)
    assert fsim.boss.kind == "mad_god" and fsim.phase2_quest is None and fsim.secret_quest is None
    champ = _player("Champ", act=4)
    champ.pos = fsim.boss.pos + pygame.Vector2(0, 60)
    fsim.begin_tick()
    fsim.update(0.01, {champ.pid: champ})
    _kill(fsim, fsim.boss, champ)
    assert fsim.boss is not None and fsim.boss.kind == "mad_god_phase2" and not champ.story.finished
    assert fsim.boss.hp_max > ENEMY_KINDS["mad_god"]["hp"]
    _kill(fsim, fsim.boss, champ)
    assert champ.story.finished and champ.story.just_completed == [4]
    assert any(pt.kind == "realm_exit" for pt in fsim.portals)
    print("check_forge_finale: PASSED")


def check_mad_god_threat():
    """The finale must actually threaten a lvl-20 player standing still in its
    line of fire - it originally dealt ~3 hp/s to a Warrior (the ring alone
    rarely reached anyone, and ~60 deF shrugged off what did). The aimed
    volley + nova are armor-piercing, so a high-deF class must not be immune."""
    import random as _r
    # averaged over 3 forge layouts: a single seed can leave only a couple of open
    # line-of-sight spots, which made the number swing with where the test stood
    for cls in ("warrior", "wizard"):
        rates = []
        for seed in (3, 4, 5):
            _r.seed(seed)
            fsim = RealmSim(bonus=True, theme="forge", difficulty_name=FORGE_DIFFICULTY, story_act=4)
            p = Player(cls, name="Tank" + cls, pid="Tank" + cls)
            p.story = story.StoryProgress(4)
            while p.level < 20:
                p.gain_xp(10 ** 6)
            boss = fsim.boss
            boss.hp = boss.hp_max = 10 ** 9
            spots = [boss.pos + pygame.Vector2(170, 0).rotate(a) for a in range(0, 360, 10)]
            spots = [v for v in spots if not fsim.is_solid(v.x, v.y)
                     and fsim.has_line_of_sight(boss.pos.x, boss.pos.y, v.x, v.y)]
            p.pos = pygame.Vector2(spots[len(spots) // 2])
            taken, secs = 0.0, 15.0
            for _ in range(int(secs * 30)):
                p.hp, p.alive = 10 ** 7, True
                fsim.begin_tick()
                fsim.update(1 / 30, {p.pid: p})
                taken += 10 ** 7 - p.hp
            rates.append(taken / secs)
        dps = sum(rates) / len(rates)
        assert dps > 20, f"Mad God too soft vs a still lvl-20 {cls}: {dps:.1f} hp/s ({rates})"
        print(f"  mad_god phase 1 vs still lvl-20 {cls}: {dps:.1f} hp/s (seeds 3-5)")
    print("check_mad_god_threat: PASSED")


class FakeSock:
    def __init__(self):
        self.msgs = []

    def sendall(self, data):
        for line in data.decode("utf-8").splitlines():
            self.msgs.append(json.loads(line))


def check_coop_snapshot_and_talk():
    import server
    state = server.ServerState()
    p = Player("wizard", name="CoopStory", pid="c1")
    p.story = server._fresh_story("CoopStory")
    p.pos = pygame.Vector2(state.nexus_bot.pos)
    s = server.Session("c1", FakeSock(), p)
    state.sessions[s.pid] = s
    snap = server._snapshot_for(state, s)
    assert snap["quest_log"]["title"] == story.ACTS[0]["title"]
    server._apply_action(state, s, {"action": "wish"})  # F next to Father Given = talk
    assert p.story.done.get("talk_given")
    assert story.ACTS[0]["intro"] in state.nexus_bot.speech
    snap = server._snapshot_for(state, s)
    assert snap["story_feed"] and not server._snapshot_for(state, s)["story_feed"]  # rides one snapshot
    # walk onto the Realm portal tile and take it
    grid = state.nexus_map.grid
    tx, ty = next((x, y) for y, row in enumerate(grid) for x, t in enumerate(row) if t == world.PORTAL)
    p.pos = pygame.Vector2(tx * 32 + 16, ty * 32 + 16)
    state.pending_actions.append(("c1", {"action": "goto_realm"}))
    server.step(state, 0.03)
    assert s.zone == server.ZONE_REALM and p.story.act == 1
    assert accounts.get_story_act("CoopStory") == 1
    snap = server._snapshot_for(state, s)
    assert snap["quest_log"]["act"] == 1 and snap["story_banners"] == [story.ACTS[0]["title"]]
    # a respawned character resumes at the account's act
    s.zone = server.ZONE_DEAD
    server._apply_action(state, s, {"action": "respawn", "cls": "wizard"})
    assert s.player.story.act == 1 and s.player.story.done == {}
    # finale: talking opens a private Forge; leaving it goes back to the Nexus
    s.player.story = story.StoryProgress(4)
    s.player.pos = pygame.Vector2(state.nexus_bot.pos)
    server._apply_action(state, s, {"action": "wish"})
    assert s.zone == server.ZONE_BONUS and state.bonus_sims[s.bonus_sim_id].boss.kind == "mad_god"
    s.portal_prompt = ("generic", "realm_exit", None, -1, None)
    server._apply_action(state, s, {"action": "enter_portal"})
    assert s.zone == server.ZONE_NEXUS
    print("check_coop_snapshot_and_talk: PASSED")


def check_singleplayer_draws():
    import main
    g = main.Game()
    g.player_name = "SPStory"
    g.start_run("wizard")
    assert g.player.story.act == accounts.get_story_act("SPStory") == 0
    g.player.pos = pygame.Vector2(g.nexus_bot.pos) + pygame.Vector2(44, 0)  # beside him, off the portal tile
    g._context_action()  # talk to Father Given
    assert g.player.story.done.get("talk_given") and story.ACTS[0]["intro"] in g.nexus_bot.speech
    g.update(1 / 60)
    g.draw()
    _shot(g.screen, "story_given_talking.png")
    # Realm with the quest log expanded, reusing the already-built realm
    g.realm_sim = _realm()
    g.realm_sim.enemies = []
    from game import minimap
    g.realm_minimap = minimap.MinimapState()
    g.player.pos = g.realm_sim.spawn_point()
    g.state = main.STATE_REALM
    g._story_event("zone", "realm")
    assert g.player.story.act == 1 and accounts.get_story_act("SPStory") == 1
    assert g.story_banner is not None
    g.story_banner[1] = 3.0
    g.update(1 / 60)
    g.draw()
    _shot(g.screen, "story_realm_quest_log_banner.png")
    g.quest_log_expanded = False
    g.story_banner = None
    g.draw()
    _shot(g.screen, "story_quest_log_collapsed.png")
    # the Forge + Mad God, and the finale completing into the credits
    g.quest_log_expanded = True
    g.player.story = story.StoryProgress(4)
    g.state = main.STATE_NEXUS
    g.player.pos = pygame.Vector2(g.nexus_bot.pos) + pygame.Vector2(44, 0)  # beside him, off the portal tile
    g._context_action()
    assert g.state == main.STATE_BONUS and g.bonus_sim.theme_key == "forge"
    g.player.pos = g.bonus_sim.boss.pos + pygame.Vector2(0, 150)
    g.player.hp = g.player.hp_max = 99999
    for _ in range(3):
        g.update(1 / 60)
    g.draw()
    _shot(g.screen, "story_forge_mad_god.png")
    boss = g.bonus_sim.boss
    _kill(g.bonus_sim, boss, g.player)
    _kill(g.bonus_sim, g.bonus_sim.boss, g.player)
    g._drain_story_completions()
    assert g.player.story.finished and accounts.get_story_act("SPStory") == story.FINAL_ACT
    assert g.credits_t is not None
    g.credits_t = 6.0
    g.draw()
    _shot(g.screen, "story_credits.png")
    g.handle_events()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    g.handle_events()
    assert g.credits_t is None  # skippable
    g.leave_bonus_room()
    assert g.state == main.STATE_NEXUS  # the Forge returns to the Nexus, not a missing realm
    print("check_singleplayer_draws: PASSED")


def check_coop_client_quest_log():
    import coop_client

    class FakeLink:
        error = None
        welcome_pid = "p0"

        def __init__(self):
            self.sent = []
            self.story = ([["Quest: Talk to Father Given in the Nexus (F) - done!", [240, 220, 140]]],
                          [story.ACTS[-1]["title"]])

        def send(self, obj):
            self.sent.append(obj)

        def get_snapshot(self):
            return None

        def pop_vault_items(self):
            return None, None

        def pop_pending_map(self):
            return None

        pop_bag_state = pop_wish_result = pop_socket_result = pop_pending_map

        def pop_whispers(self):
            return []

        pop_trade_notices = pop_pet_results = pop_echo_shop_states = pop_whispers

        def pop_dialogue(self):
            return None

        def pop_story(self):
            v, self.story = self.story, ([], [])
            return v

    client = coop_client.CoopClient("127.0.0.1", 0, "CoopLog")
    client.link = FakeLink()
    client.state = coop_client.STATE_PLAY
    me = Player("wizard", name="CoopLog", pid="p0")
    sp = story.StoryProgress(1)
    snap = {"zone": "nexus", "you": me.full_state(), "players": [], "chats": [], "trade": None,
            "quest_log": sp.quest_log()}
    client._apply_snapshot(snap)
    assert client.quest_log["act"] == 1
    assert any("Father Given" in m[0] for m in client.feed)
    assert client.story_banner is not None and client.credits_t == 0.0  # the finale banner rolls credits
    client.update(0.016)
    client.draw()
    client._play_key(pygame.K_j)
    assert not client.quest_log_expanded
    client.draw()
    print("check_coop_client_quest_log: PASSED")


if __name__ == "__main__":
    check_transitions_through_every_act()
    check_account_act_persistence()
    check_character_progress_and_permadeath()
    check_island_idx_survives_a_skipped_placement()
    check_landmark_guardian()
    check_dungeon_clear_and_act_scale()
    check_forge_finale()
    check_mad_god_threat()
    check_coop_snapshot_and_talk()
    check_singleplayer_draws()
    check_coop_client_quest_log()
    print("PASSED: story checks all green.")

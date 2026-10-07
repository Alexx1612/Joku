"""
Quest markers (game/quest_markers.py): Show / Hide marker in the Quest Log (button + T),
tracked ids saved with the character, target resolution per quest kind and per zone
(Realm, Nexus -> the Realm portal, Realm -> "press R", dungeon, hubs), minimap / full map /
in-world drawing with edge clamping, and the co-op client doing the same.

Run with: .venv\\Scripts\\python.exe tests\\check_quest_markers.py
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("RR_NO_MUSIC", "1")

import pygame
pygame.init()
screen = pygame.display.set_mode((1366, 820))

from game import accounts, characters, achievements
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_qm_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_qm_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_qm_ach_")

from game import quest_markers as QM, codex, minimap, world, journal, constants as C
from game.realm_sim import RealmSim
from game.entities import Player

SHOT_DIR = os.environ.get("RR_SHOT_DIR")
random.seed(9)
SIM = RealmSim()
AREAS = codex.realm_areas(SIM)


def _player():
    p = Player("wizard", name="Pin", pid="pin")
    for q in ("mossbeard_mushrooms", "bog_brew", "snack_time"):
        p.sidequests.active[q] = {"have": 0.0, "seen": []}
    return p


def _world(zone, pos, grid=None):
    return {"zone": zone, "player": pos, "grid": grid, "areas": AREAS, "live_npcs": {},
            "nexus_npcs": {"father_given": (100.0, 100.0), "hammerstein": (300.0, 120.0), "bitterwick": (60, 60)}}


def check_toggle_and_cap():
    t = []
    for q in ("a", "b", "c", "d"):
        t = QM.toggle(t, q)
    assert t == ["b", "c", "d"], t  # capped at 3, oldest dropped
    t = QM.toggle(t, "c")
    assert t == ["b", "d"]
    assert QM.color_for(t, "b") != QM.color_for(t, "d")
    print("check_toggle_and_cap: PASSED")


def check_persistence_round_trip():
    p = _player()
    p.tracked_quests = ["story", "side:bog_brew"]
    back = Player.from_full_state(p.full_state())
    assert back.tracked_quests == ["story", "side:bog_brew"]
    d = p.full_state()
    d.pop("tracked_quests")
    assert Player.from_full_state(d).tracked_quests == [], "old saves load with no markers"
    import server
    state = server.ServerState()

    class Sock:
        def sendall(self, *_a):
            pass
    s = server.Session("Pin", Sock(), p)
    server._apply_action(state, s, {"action": "track_quests", "ids": ["side:mossbeard_mushrooms"]})
    assert p.tracked_quests == ["side:mossbeard_mushrooms"]
    print("check_persistence_round_trip: PASSED")


def check_target_resolution():
    p = _player()
    story_log, side_log = p.story.quest_log(), p.sidequests.log(p)
    entries = {q: (title, tg) for q, title, tg in QM.quest_entries(story_log, side_log)}
    assert "story" in entries and "side:bog_brew" in entries
    assert not QM.can_locate("side:snack_time", story_log, side_log), "pets have no place"
    assert QM.can_locate("side:mossbeard_mushrooms", story_log, side_log)
    mb = next(n for n in AREAS["npcs"] if n["id"] == "mossbeard")
    mpos = (mb["x"] * C.TILE, mb["y"] * C.TILE)
    # an NPC in the Realm
    m = QM.resolve("side:mossbeard_mushrooms", *entries["side:mossbeard_mushrooms"],
                   _world("realm", (mpos[0] + 320, mpos[1])), (255, 0, 0))
    assert m["pos"] == mpos and m["dist_tiles"] == 10, m
    # a mob target: the nearest of its biome's regions
    m = QM.resolve("side:bog_brew", *entries["side:bog_brew"], _world("realm", mpos), (255, 0, 0))
    assert m["pos"] is not None and codex.tile_biome(SIM.realm_map.grid, int(m["pos"][0] // C.TILE),
                                                     int(m["pos"][1] // C.TILE)) is not None
    # the story's "talk to Father Given" from the Realm: no world spot, "press R"
    m = QM.resolve("story", *entries["story"], _world("realm", mpos), (255, 0, 0))
    assert m["pos"] is None and "press R" in m["note"], m
    # ... and from the Nexus: Father Given himself
    m = QM.resolve("story", *entries["story"], _world("nexus", (0.0, 0.0)), (255, 0, 0))
    assert m["pos"] == (100.0, 100.0)
    # a Realm target from the Nexus -> the Realm portal
    nexus = world.TileMap(world.make_nexus())
    m = QM.resolve("side:mossbeard_mushrooms", *entries["side:mossbeard_mushrooms"],
                   _world("nexus", (0.0, 0.0), nexus.grid), (255, 0, 0))
    tx, ty = int(m["pos"][0] // C.TILE), int(m["pos"][1] // C.TILE)
    assert nexus.grid[ty][tx] == world.PORTAL and "portal" in m["note"]
    # hubs point back at their portal, dungeons say "leave"
    bazaar = world.TileMap(world.make_bazaar())
    m = QM.resolve("side:bog_brew", *entries["side:bog_brew"], _world("hub", (0.0, 0.0), bazaar.grid), (1, 1, 1))
    assert m["pos"] is not None
    m = QM.resolve("side:bog_brew", *entries["side:bog_brew"], _world("dungeon", (0.0, 0.0)), (1, 1, 1))
    assert m["pos"] is None and "dungeon" in m["note"]
    # the Anvil and the shoreline
    m = QM.resolve("x", "Forge", {"kind": "area", "key": "anvil", "label": "Anvil"}, _world("nexus", (0, 0)), (1, 1, 1))
    assert m["pos"] == (300.0, 120.0)
    m = QM.resolve("x", "Fish", {"kind": "area", "key": "water", "label": "shore"},
                   _world("realm", SIM.spawn_point() / 1, SIM.realm_map.grid), (1, 1, 1))
    tx, ty = int(m["pos"][0] // C.TILE), int(m["pos"][1] // C.TILE)
    assert SIM.realm_map.grid[ty][tx] == world.WATER
    # a ready side quest points at its turn-in NPC
    q = dict(next(e for e in side_log if e["id"] == "mossbeard_mushrooms"), ready=True)
    assert QM.side_target(q)["key"] == "mossbeard"
    # a handed-in quest drops its marker
    assert QM.prune(["side:gone", "story"], story_log, side_log) == ["story"]
    print("check_target_resolution: PASSED")


def check_quest_log_toggle():
    p = _player()
    calls = []

    def on_track(qid):
        p.tracked_quests = QM.toggle(p.tracked_quests, qid)
        calls.append(qid)
    j = journal.Journal()
    j.open_quest_log()

    def ctx():
        return {"story": p.story.quest_log(), "side": p.sidequests.log(p), "side_done": [], "grid": None,
                "areas": AREAS, "player_tile": None, "tracked": list(p.tracked_quests), "on_track": on_track}
    items, _ = j._ql_layout(ctx())
    buttons = [it for it in items if it["kind"] == "marker"]
    off = [it for it in items if it["kind"] == "button_off"]
    assert any(b["qid"] == "side:bog_brew" for b in buttons) and off, "pets quest shows 'No location'"
    win, content = j._ql_rects()
    b = next(b for b in buttons if b["qid"] == "side:bog_brew")
    click = (content.x + b["x"] + 5, content.y + b["y"] - j.ql_scroll + 5)
    j._click(click, ctx())
    assert p.tracked_quests == ["side:bog_brew"]
    items, _ = j._ql_layout(ctx())
    assert next(it for it in items if it.get("qid") == "side:bog_brew" and it["kind"] == "marker")["text"] == "Hide marker"
    # select a quest line, T toggles it
    sel = next(it for it in items if it["kind"] == "select" and it["qid"] == "side:mossbeard_mushrooms")
    j._click((content.x + sel["x"] + 20, content.y + sel["y"] - j.ql_scroll + 6), ctx())
    assert j.ql_sel == "side:mossbeard_mushrooms"
    j.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_t, mod=0, unicode="t"), ctx())
    assert "side:mossbeard_mushrooms" in p.tracked_quests and calls[-1] == "side:mossbeard_mushrooms"
    screen.fill((0, 0, 0))
    j.draw(screen, ctx(), (0, 0))
    print("check_quest_log_toggle: PASSED")


def _colour_in(surf, rect, color):
    for y in range(rect.top, rect.bottom, 1):
        for x in range(rect.left, rect.right, 1):
            if surf.get_at((x, y))[:3] == color:
                return True
    return False


def check_map_drawing_and_edge_clamp():
    col = QM.COLORS[1]
    marks = [{"qid": "q", "title": "Far away", "color": col, "pos": (10 ** 6, 500.0), "note": "", "label": "x",
              "dist_tiles": 999}]
    surf = pygame.Surface((400, 300))
    surf.fill((0, 0, 0))
    rect = pygame.Rect(100, 100, 200, 100)
    QM.draw_on_map(surf, marks, rect, lambda wx, wy: (wx / 10, wy / 10))
    assert _colour_in(surf, rect, col), "an off-map target clamps to the map's edge"
    right = pygame.Rect(rect.right, 0, 400 - rect.right, 300)
    assert not _colour_in(surf, right, col), "and never draws outside it"
    # minimap + full map + world view, every zone a marker can be in
    mm = minimap.MinimapState()
    p = pygame.Vector2(SIM.spawn_point())
    near = {"qid": "n", "title": "Near", "color": QM.COLORS[0], "pos": (p.x + 64, p.y), "note": "", "label": "",
            "dist_tiles": 2}
    screen.fill((0, 0, 0))
    minimap.draw_corner(screen, SIM.realm_map, mm, p, quest_marks=[near] + marks)
    ox, oy = minimap.corner_origin()
    assert _colour_in(screen, pygame.Rect(ox, oy, minimap.CORNER_W, minimap.CORNER_H), QM.COLORS[1])
    mm.reveal_all(SIM.realm_map) if hasattr(mm, "reveal_all") else None
    minimap.draw_full_map(screen, SIM.realm_map, mm, p, quest_marks=[near] + marks)
    screen.fill((0, 0, 0))
    cam = lambda v: (int(v[0] - p.x + 500), int(v[1] - p.y + 400))
    font = pygame.font.SysFont("consolas", 14)
    QM.draw_world(screen, [near] + marks, cam, (p.x, p.y), pygame.Rect(0, 0, 1060, 820), font)
    assert _colour_in(screen, pygame.Rect(1000, 0, 60, 820), QM.COLORS[1]), "edge arrow on the right"
    y = QM.draw_tracker(screen, [near, dict(marks[0], pos=None, note="in the Nexus - press R")], font, 10, 700)
    assert y > 700
    print("check_map_drawing_and_edge_clamp: PASSED")


def check_game_draws_markers():
    import main
    from game import minimap as mmod
    random.seed(4)
    g = main.Game()
    g.player_name = "PinGame"
    g.start_run("wizard")
    g.realm_sim = SIM
    g.realm_minimap = mmod.MinimapState()
    p = g.player
    p.sidequests.active["mossbeard_mushrooms"] = {"have": 0.0, "seen": []}
    g._toggle_quest_marker("side:mossbeard_mushrooms")
    g._toggle_quest_marker("story")
    assert p.tracked_quests == ["side:mossbeard_mushrooms", "story"]
    for state in (main.STATE_NEXUS, main.STATE_REALM):
        g.state = state
        if state == main.STATE_REALM:
            p.pos = pygame.Vector2(SIM.spawn_point())
        g.update(1 / 60)
        marks = g._quest_marks()
        assert len(marks) == 2
        g.draw()
        if SHOT_DIR:
            pygame.image.save(g.screen, os.path.join(SHOT_DIR, f"quest_markers_{state}.png"))
    g.realm_minimap.full_map_open = True
    g.draw()
    g.realm_minimap.full_map_open = False
    print("check_game_draws_markers: PASSED")


def check_coop_client_markers():
    import coop_client

    class FakeLink:
        error = None
        welcome_pid = "c0"

        def __init__(self):
            self.sent = []

        def send(self, obj):
            self.sent.append(obj)

    me = _player()
    me.pid = "c0"
    me.tracked_quests = ["side:bog_brew"]
    client = coop_client.CoopClient("127.0.0.1", 0, "Pin")
    client.link = FakeLink()
    client.state = coop_client.STATE_PLAY
    client.zone = "nexus"
    client.you = Player.from_full_state(me.full_state())
    client.tracked_quests = list(client.you.tracked_quests)
    client.quest_log = me.story.quest_log()
    client.sidequest_log = me.sidequests.log(me)
    client.realm_areas = AREAS
    client._toggle_quest_marker("side:mossbeard_mushrooms")
    assert client.link.sent[-1] == {"type": "action", "action": "track_quests",
                                    "ids": ["side:bog_brew", "side:mossbeard_mushrooms"]}
    marks = client._quest_marks()
    assert len(marks) == 2 and all(m["pos"] is not None for m in marks), "both -> the Realm portal from the Nexus"
    client.draw()
    print("check_coop_client_markers: PASSED")


if __name__ == "__main__":
    check_toggle_and_cap()
    check_persistence_round_trip()
    check_target_resolution()
    check_quest_log_toggle()
    check_map_drawing_and_edge_clamp()
    check_game_draws_markers()
    check_coop_client_markers()
    print("\nPASSED: quest marker checks all green.")

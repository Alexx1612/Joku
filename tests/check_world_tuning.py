"""
Doc 42 (your follow-up requests): the 1.25x view zoom, the 10x map zoom, closer aggro, a much
tougher night, the island danger scale (ranked by distance + shore -> centre), hamlets and island
outposts, one character for single-player and co-op, and the Blood Moon heartbeat.

Run with: python tests/check_world_tuning.py
"""
import json
import os
import socket
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((1366, 820))

from game import accounts, characters, achievements, items as I
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_wt_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_wt_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_wt_ach_")
I.VAULT_DIR = tempfile.mkdtemp(prefix="rr_wt_vault_")

from game import settings
settings.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(prefix="rr_wt_set_"), "settings.json")

from game import view_scale, minimap, danger, night as nm, lighting, ui, audio, world
from game import constants as C
from game.constants import TILE
from game.entities import Player, Enemy, ENEMY_KINDS
from game.realm_sim import RealmSim

audio.play_theme = lambda *a, **k: None
SIM = RealmSim()


def check_view_zoom():
    """World-only zoom: the world is drawn bigger, the HUD / dock / windows stay full size."""
    assert view_scale.zoom() == 1.0, "headless runs stay at 100%"
    os.environ["RR_ZOOM"] = "1.25"
    try:
        import main
        g = main.Game()
        assert g.screen.get_size() == (1366, 820), "the canvas is the full window - the HUD isn't squeezed"
        g.player_name = "Zoomer"
        g.start_run("wizard")
        g.realm_sim = RealmSim()
        g.realm_minimap = minimap.MinimapState()
        g.state = main.STATE_REALM
        g.player.pos = g.realm_sim.spawn_point()
        g.update(1 / 60)
        g.draw()
        assert (C.SCREEN_W, C.SCREEN_H) == (1366, 820), "the world pass restores the screen size"
        assert g.cam.zoom == 1.25
        # the camera speaks real screen pixels at the zoom: you're at the centre, and the mouse
        # 100 px to your right aims 80 world px to your right
        assert g.cam(g.player.pos) == (683, 410)
        aim = g.cam.inverse((783, 410)) - g.player.pos
        assert abs(aim.x - 80) < 1 and abs(aim.y) < 1, aim
        # the dock and the backpack are all on screen
        dock = ui.dock_frame_rect(g.player)
        assert pygame.Rect(0, 0, 1366, 820).contains(dock), dock
        # the world really is drawn bigger: the player sprite covers ~1.25x the pixels it did at 100%
        def player_px():
            g.draw()
            c = g.cam(g.player.pos)
            box = pygame.Rect(c[0] - 40, c[1] - 40, 80, 80)
            ref = g.screen.get_at((c[0] - 60, c[1] + 60))
            return sum(1 for x in range(box.x, box.right) for y in range(box.y, box.bottom)
                       if g.screen.get_at((x, y)) != ref)
        big = player_px()
        os.environ["RR_ZOOM"] = "1.0"
        g.update(1 / 60)
        small = player_px()
        assert big > small, (big, small)
        # the Options menu (a HUD window) is the same at any zoom
        g.help_open = True
        rows = g._menu_items()
        x, y, w, h, *_ = ui._help_panel_geometry(rows)
        assert pygame.Rect(0, 0, 1366, 820).contains(pygame.Rect(x, y, w, h))
    finally:
        os.environ.pop("RR_ZOOM", None)
        C.SCREEN_W, C.SCREEN_H = 1366, 820
    # the setting itself
    assert settings.get("zoom") == 1.25
    settings.change("zoom", 1.5)
    assert settings.get("zoom") == 1.5
    settings.change("zoom", 7)
    assert settings.get("zoom") == 1.25
    print("check_view_zoom: PASSED")


def check_map_zoom_10x():
    mm = minimap.MinimapState()
    for _ in range(40):
        mm.adjust_zoom(minimap.ZOOM_STEP)
        mm.adjust_corner_zoom(minimap.CORNER_ZOOM_STEP)
    assert mm.zoom == minimap.MAX_ZOOM == 10.0 and mm.corner_zoom == minimap.CORNER_MAX_ZOOM == 10.0
    notches = 0
    mm.zoom = 1.0
    while mm.zoom < 10.0:
        mm.adjust_zoom(minimap.ZOOM_STEP)
        notches += 1
    assert notches <= 14, notches  # multiplicative steps: 1x -> 10x in about a dozen notches
    print(f"check_map_zoom_10x: PASSED (1x -> 10x in {notches} notches)")


def check_aggro_and_a_harder_night():
    from game.entities import AGGRO_SCALE
    gob = Enemy("goblin", (0, 0))
    assert gob.aggro_range == ENEMY_KINDS["goblin"]["aggro_range"] * AGGRO_SCALE < 200
    boss = next(k for k, d in ENEMY_KINDS.items() if d["rank"] == "boss")
    assert Enemy(boss, (0, 0)).aggro_range == ENEMY_KINDS[boss]["aggro_range"], "bosses still chase anywhere"
    r, b = nm.NIGHT_RULES, nm.BLOOD_RULES
    assert r["hp"] >= 1.5 and r["dmg"] >= 1.4 and r["aggro"] <= 1.35, r
    assert b["hp"] > r["hp"] and b["dmg"] > r["dmg"]
    # worst case (dark, Blood Moon, the heart of the Realm) a goblin no longer spots you from half a screen
    worst = gob.aggro_range * b["aggro_dark"] * danger.mults(1.0)["aggro"]
    assert worst < C.SCREEN_W / 2, worst
    print(f"check_aggro_and_a_harder_night: PASSED (goblin day {gob.aggro_range:.0f}px, worst night {worst:.0f}px)")


def check_island_danger():
    assert len(danger.ISLAND_CENTERS) == len(SIM.islands) and danger.ISLAND_SPAWN is not None
    ranks = sorted(danger.island_rank(c) for c in danger.ISLAND_CENTERS)
    assert ranks[0] == 0.0 and ranks[-1] == 1.0
    near = min(danger.ISLAND_CENTERS, key=danger.island_rank)
    far = max(danger.ISLAND_CENTERS, key=danger.island_rank)
    R = world.ISLAND_RADIUS * TILE
    shore_near = danger.island_frac(near[0] + R * 0.8, near[1])
    centre_near = danger.island_frac(*near)
    centre_far = danger.island_frac(*far)
    if shore_near is None:
        shore_near = danger.island_frac(near[0], near[1] + R * 0.8) or 0.0
    assert shore_near < centre_near < centre_far == 1.0, (shore_near, centre_near, centre_far)
    assert danger.island_frac(SIM.realm_map.w * TILE / 2, SIM.realm_map.h * TILE / 2) is None  # the continent
    assert danger.island_mults(1.0)["hp"] > danger.island_mults(0.0)["hp"] * 2
    # real island mobs got scaled (and pay better)
    isl_mobs = [e for e in SIM.enemies if getattr(e, "island_danger", None) is not None]
    if not isl_mobs:
        SIM.update(1 / 30, {})
        isl_mobs = [e for e in SIM.enemies if getattr(e, "island_danger", None) is not None]
    assert isl_mobs and len({round(e.island_danger, 1) for e in isl_mobs}) >= 4
    from game.realm_sim import _danger_mults
    lo = min(isl_mobs, key=lambda e: e.island_danger)
    hi = max(isl_mobs, key=lambda e: e.island_danger)
    assert _danger_mults(hi)["xp"] > _danger_mults(lo)["xp"]
    # the HUD names it
    label = minimap._danger_label(SIM.realm_map, pygame.Vector2(*far))
    assert label and label[0].startswith("Isle:"), label
    print(f"check_island_danger: PASSED ({len(isl_mobs)} island mobs, danger {lo.island_danger:.2f}..{hi.island_danger:.2f})")


def check_hamlets_and_outposts():
    assert len(SIM.hamlets) >= 8, SIM.hamlets
    assert len(SIM.island_outposts) == len(SIM.islands)
    labels = [h["label"] for h in SIM.safe_houses]
    assert sum(1 for l in labels if l == "a hamlet house") >= 16
    assert sum(1 for l in labels if l.startswith("an outpost on")) == len(SIM.islands)
    assert sum(1 for l in labels if l.startswith("a shelter on")) >= len(SIM.islands) - 1
    grid = SIM.realm_map.grid
    new = ("a hamlet house", "an outpost on", "a shelter on", "a wayside shack")
    for h in SIM.safe_houses:
        assert all(grid[y][x] in world.DOOR_TILES for (x, y) in h["doors"]),             (h["label"], [(x, y, grid[y][x]) for (x, y) in h["doors"]])
        if h["label"].startswith(new):  # nothing (props, walls) got stamped over the new houses
            assert all(grid[y][x] == world.AREA_PLANK for (x, y) in h["interior"]), h["label"]
    for op in SIM.island_outposts:  # outposts are ON the islands
        assert (op["x"], op["y"]) in SIM.island_tiles
    print(f"check_hamlets_and_outposts: PASSED ({len(SIM.hamlets)} hamlets, {len(SIM.island_outposts)} outposts, "
          f"{len(SIM.safe_houses)} shelters)")


def check_one_character_everywhere():
    p = Player("wizard", "Traveller", pid="t")
    for _ in range(9):
        p.gain_xp(500)
    p.backpack = [I.make_forge_ingot()]
    good = characters.validate(p.full_state(), "Traveller")
    assert good and good["level"] == p.level and "pid" not in good
    assert characters.validate({"level": 999}, "X") is None
    bad = p.full_state()
    bad["level"] = 99
    assert characters.validate(bad, "Traveller") is None
    bad = p.full_state()
    bad["att"] = 9999
    assert characters.validate(bad, "Traveller") is None
    assert characters.validate("not a dict", "Traveller") is None
    fresh = Player("wizard", "Traveller", pid="f").full_state()
    assert characters.pick_for_join(None, good) is good
    assert characters.pick_for_join(fresh, good) is good
    assert characters.pick_for_join(good, fresh) is good, "the further-along copy wins"
    assert characters.pick_for_join(good, None) is good
    # a real join: the server adopts the character the client brought along
    import server
    state = server.ServerState()
    a, b = socket.socketpair()
    t = threading.Thread(target=server.handle_client, args=(a, ("test", 0), state), daemon=True)
    t.start()
    from game.netmsg import send_msg
    send_msg(b, {"type": "join", "name": "Traveller", "cls": "wizard", "character": p.full_state()})
    for _ in range(100):
        with state.lock:
            sess = next(iter(state.sessions.values()), None)
        if sess is not None:
            break
        pygame.time.wait(20)
    assert sess is not None and sess.player.level == p.level and any(it.shape == "ingot" for it in sess.player.backpack)
    b.close()
    t.join(timeout=3)
    assert characters.load_character("Traveller")["level"] == p.level, "saved on the server side on disconnect"
    # an impossible upload is ignored (a fresh character instead)
    state2 = server.ServerState()
    a2, b2 = socket.socketpair()
    t2 = threading.Thread(target=server.handle_client, args=(a2, ("test", 0), state2), daemon=True)
    t2.start()
    cheat = p.full_state()
    cheat["level"] = 500
    characters.delete_character("Cheater")
    send_msg(b2, {"type": "join", "name": "Cheater", "cls": "wizard", "character": cheat})
    for _ in range(100):
        with state2.lock:
            s2 = next(iter(state2.sessions.values()), None)
        if s2 is not None:
            break
        pygame.time.wait(20)
    assert s2 is not None and s2.player.level == 1
    b2.close()
    t2.join(timeout=3)
    # the co-op client mirrors the server's copy of you into your own save, and a death deletes it
    import coop_client
    client = coop_client.CoopClient("127.0.0.1", 0, "Mirror")
    client.state = coop_client.STATE_PLAY
    client.zone = "nexus"
    client.you = p
    characters.delete_character("Mirror")
    client._mirror_character(0.0, force=True)
    assert characters.load_character("Mirror")["level"] == p.level
    client.zone = "dead"
    client._mirror_character(0.0)
    assert characters.load_character("Mirror") is None, "permadeath is the same everywhere"
    print("check_one_character_everywhere: PASSED")


def check_blood_moon_heartbeat():
    peaks = [ui.heartbeat_shape(x / 100) for x in range(100)]
    lub, dub = peaks[5], peaks[27]
    assert lub > 0.95 and 0.5 < dub < lub and peaks[60] < 0.05, (lub, dub, peaks[60])
    lighting.GRADE["pulse"] = 0.0
    quiet = lighting.ambient_color(0.0, 0.5, True)
    lighting.GRADE["pulse"] = 1.0
    beat = lighting.ambient_color(0.0, 0.5, True)
    lighting.GRADE["pulse"] = 0.0
    assert beat[0] > quiet[0], (quiet, beat)  # each beat swells the red night
    assert lighting.ambient_color(0.0, 0.5, False) == lighting.ambient_color(0.0, 0.5, False)
    print(f"check_blood_moon_heartbeat: PASSED (quiet {quiet} -> beat {beat})")


def check_visited_places_and_map_pins():
    """Each quest lists where it already counted you (and, for a fixed set, where you haven't been
    yet); clicking the full map / the Quest Map / the Dictionary's map drops your own pins."""
    from game import story, sidequests, map_pins, journal
    sp = story.StoryProgress(story.ACT_TOUR)
    sp.on_event("area", "tavern_town")
    sp.on_event("landmark", "forest")
    objs = {o["text"]: o for o in sp.quest_log()["objectives"]}
    tour = next(o for t, o in objs.items() if t.startswith("Visit"))
    assert tour["seen"] == ["Tavern Town"] and "Tavern Town" not in tour["todo"] and len(tour["todo"]) >= 4
    lm = next(o for t, o in objs.items() if t.startswith("Spot the landmark"))
    assert len(lm["seen"]) == 1 and lm["todo"]
    sq = sidequests.SideQuestProgress()
    qid = next(q for q, d in sidequests.QUESTS.items() if d.get("key") == "island")
    sq.accept(qid)
    sq.on_event("reach", "island", 1, {"idx": 3, "label": "Isle Three"})
    sq.on_event("reach", "island", 1, {"idx": 3, "label": "Isle Three"})  # the same island counts once
    entry = next(e for e in sq.log() if e["id"] == qid)
    assert entry["seen"] == ["Isle Three"], entry["seen"]
    assert sidequests.SideQuestProgress.from_json(json.loads(json.dumps(sq.to_json()))).active[qid]["names"] == ["Isle Three"]
    # the Quest Log shows them
    jn = journal.Journal()
    items, _h = jn._ql_layout({"story": sp.quest_log(), "side": sq.log(), "side_done": []})
    texts = [i["text"] for i in items]
    assert any(t.startswith("Been there: Tavern Town") for t in texts)
    assert any(t.startswith("Not yet: ") for t in texts) and any(t.startswith("Done so far: Isle Three") for t in texts)
    # pins: add, remove by clicking the same spot, at most MAX_PINS, safe from bad data
    pins = []
    assert map_pins.toggle(pins, 1000, 1000) == "added" and pins[0][2] == "Pin 1"
    assert map_pins.toggle(pins, 1010, 990) == "removed" and not pins
    for k in range(map_pins.MAX_PINS + 2):
        map_pins.toggle(pins, k * 1000, 0)
    assert len(pins) == map_pins.MAX_PINS
    assert map_pins.clean([[1, 2, "x"], ["bad"], None, [3, 4, 5]]) == [[1.0, 2.0, "x"], [3.0, 4.0, "5"]]
    # single-player: the full map click, the Quest Map click, the Dictionary map click
    import main
    g = main.Game()
    g.player_name = "Pinner"
    g.start_run("wizard")
    g.realm_sim = SIM
    g.realm_minimap = minimap.MinimapState()
    g.state = main.STATE_REALM
    g.player.pos = SIM.spawn_point()
    g.realm_minimap.full_map_open = True
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(683 + 100, 410)))
    g.handle_events()
    assert len(g.player.map_pins) == 1
    wx, wy, _l = g.player.map_pins[0]
    px_per_tile = max(2, int(5 * g.realm_minimap.zoom))
    assert abs(wx - (g.player.pos.x + 100 / px_per_tile * TILE)) < TILE * 1.5, (wx, g.player.pos.x)
    marks = g._quest_marks()
    assert any(m["qid"].startswith("pin:") and m["color"] == map_pins.PIN_COLOR for m in marks)
    g.draw()  # the pin on the full map
    g.realm_minimap.full_map_open = False
    g.draw()  # ...and in the world / on the corner minimap
    ctx = g._journal_ctx()
    g.journal.open_map(None, "test")
    rect, scale = g.journal._map_geom(ctx)
    g.journal._click(rect.center, ctx)
    assert len(g.player.map_pins) == 2
    g.journal._click(rect.center, g._journal_ctx())  # clicking it again removes it
    assert len(g.player.map_pins) == 1
    g.journal.draw(g.screen, g._journal_ctx(), (0, 0))
    g.journal.open_dictionary("enemy:goblin")
    r = g.journal._dict_rects()
    g.journal._click(r["mini"].center, g._journal_ctx())
    assert len(g.player.map_pins) == 2
    g.journal.draw(g.screen, g._journal_ctx(), (0, 0))
    # pins are saved with the character; the co-op server stores the client's list
    q = Player.from_full_state(json.loads(json.dumps(g.player.full_state())))
    assert len(q.map_pins) == 2
    import server
    state = server.ServerState()
    me = Player("wizard", "PinCoop", pid="c0")

    class Sock:
        def sendall(self, data):
            pass
    s = server.Session("c0", Sock(), me)
    state.sessions["c0"] = s
    server._apply_action(state, s, {"action": "map_pins", "pins": [[10, 20, "Pin 1"], "junk"]})
    assert me.map_pins == [[10.0, 20.0, "Pin 1"]]
    print("check_visited_places_and_map_pins: PASSED")


if __name__ == "__main__":
    check_visited_places_and_map_pins()
    check_view_zoom()
    check_map_zoom_10x()
    check_aggro_and_a_harder_night()
    check_island_danger()
    check_hamlets_and_outposts()
    check_one_character_everywhere()
    check_blood_moon_heartbeat()
    print("\nPASSED: world tuning checks all green.")

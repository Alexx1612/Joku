"""
Zone music (game/music.py) + zone-entry banners (game/zone_banner.py).
Replaces the old per-builder theme checks (check_theme_*.py) - the ~20s themes
they pinned were replaced by ~60s seamlessly looping tracks per zone/biome/dungeon.

Renders at a low sample rate (fast path) for the signal checks.
"""
import array
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["RR_MUSIC_CACHE"] = tempfile.mkdtemp(prefix="rr_music_cache_")

import pygame
pygame.init()
screen = pygame.display.set_mode((1366, 820))

from game import music, zone_banner, ui, audio
from game import constants as C

LOW = 8000


def _pcm(zone):
    a = array.array("h")
    a.frombytes(music.compose_and_render(music.TRACKS[zone], rate=LOW))
    return a


def check_every_place_has_a_distinct_track():
    zones = set(music.TRACKS)
    for need in ["nexus", "bazaar", "vault", *music.BIOMES, "island_shard", "island_choir", "dungeon",
                 "dungeon_cave", "dungeon_frozen_crypt", "dungeon_jungle_ruins", "dungeon_ember_den",
                 "dungeon_sunken_grotto", "dungeon_wind_spire", "dungeon_forge"]:
        assert need in zones, need
    specs = [(t["key"], t["scale"], t["bpm"], t["style"], t["seed"]) for t in music.TRACKS.values()]
    assert len(set(specs)) == len(specs), "two zones share an identical track spec"
    assert len({t["title"] for t in music.TRACKS.values()}) == len(music.TRACKS)
    # dungeon label resolution (co-op only receives the label)
    assert music.dungeon_zone_for_label("Frozen Crypt") == "dungeon_frozen_crypt"
    assert music.dungeon_zone_for_label("The Forge") == "dungeon_forge"
    assert music.dungeon_zone_for_label("Forgotten Vault") == "dungeon"
    assert music.realm_zone("ashlands") == "ashlands" and music.realm_zone(None, island_idx=3) == "island_choir"
    print("check_every_place_has_a_distinct_track: PASSED")


def check_one_minute_bar_aligned_seamless_loops():
    for zone, spec in music.TRACKS.items():
        secs = music.length_seconds(spec)
        assert 55.0 <= secs <= 65.0, (zone, secs)
        bars = music.bars_for(spec["bpm"])
        assert sum(n for _s, n in music.plan_sections(bars)) == bars
        assert len({s for s, _n in music.plan_sections(bars)}) >= 3, "needs real sections (verse/chorus/bridge)"
    for zone in ("forest", "cave", "nexus", "dungeon_forge", "bazaar"):
        a = _pcm(zone)
        spec = music.TRACKS[zone]
        expect = round(music.bars_for(spec["bpm"]) * 16 * LOW * 60.0 / spec["bpm"] / 4)
        assert abs(len(a) - expect) <= 2, (zone, len(a), expect)
        peak = max(abs(v) for v in a)
        assert peak > 12000, (zone, peak)
        # the seam (last -> first sample) is no bigger a jump than ordinary sample steps
        steps = sorted(abs(a[i + 1] - a[i]) for i in range(0, len(a) - 1, 3))
        p99 = steps[int(len(steps) * 0.99)]
        assert abs(a[0] - a[-1]) <= max(p99, 2000), (zone, abs(a[0] - a[-1]), p99)
        # it develops: loudness differs across the minute (not one flat riff)
        w = len(a) // 6
        rms = [sum(v * v for v in a[i:i + w:5]) for i in range(0, 6 * w, w)]
        assert max(rms) > min(rms) * 1.15, (zone, rms)
    print("check_one_minute_bar_aligned_seamless_loops: PASSED")


def check_cache_and_background_render():
    zone = "tundra"
    p = music.cache_path(zone, LOW)
    assert not os.path.exists(p)
    t0 = time.time()
    first = music.load_or_render(zone, LOW)
    assert os.path.exists(p) and first[:4] == b"RIFF"
    t1 = time.time()
    again = music.load_or_render(zone, LOW)
    assert again == first
    assert time.time() - t1 <= max(0.05, (t1 - t0)), "cache hit should not re-render"
    lib = music.Library(rate=LOW, prewarm=False)
    t = time.time()
    assert lib.request("swamp") is None            # not ready yet -> returns at once
    assert time.time() - t < 0.05, "request() must never block the game loop"
    deadline = time.time() + 20
    while not lib.is_ready("swamp") and time.time() < deadline:
        time.sleep(0.02)
    assert lib.is_ready("swamp") and lib.request("swamp")[:4] == b"RIFF"
    print("check_cache_and_background_render: PASSED")


def check_music_hysteresis():
    h = music.Hysteresis(2.0)
    assert h.update(0.1, "forest") == "forest"
    for _ in range(15):                  # 1.5s in desert, then back: no switch
        assert h.update(0.1, "desert") == "forest"
    assert h.update(0.1, "forest") == "forest"
    for _ in range(19):
        h.update(0.1, "desert")
    assert h.update(0.2, "desert") == "desert"
    # border thrash: alternating every 0.5s never switches
    h = music.Hysteresis(2.0)
    h.update(0.1, "a")
    for i in range(40):
        assert h.update(0.5, "b" if i % 2 == 0 else "a") == "a"
    print("check_music_hysteresis: PASSED")


def _step(tr, secs, place, dt=0.05):
    out = None
    for _ in range(int(round(secs / dt))):
        out = tr.observe(dt, *place)
    return out


def check_banner_dwell_repeat_and_crossfade():
    tr = zone_banner.ZoneTracker()
    nexus = zone_banner.hub_place("nexus")
    _step(tr, 0.5, nexus)
    assert [c[0] for c in tr.visible()] == ["Nexus"], tr.visible()
    forest = ("realm", "biome:forest", "Forest", "Realm", "forest")
    desert = ("realm", "biome:desert", "Desert", "Realm", "desert")
    _step(tr, 4.0, forest)               # portal into the realm: quick accept
    assert tr.place == "biome:forest"
    _step(tr, 3.5, forest)               # card fades away
    assert tr.visible() == []
    # A -> B -> A quicker than the dwell: nothing announced, place unchanged
    for _ in range(6):
        _step(tr, 0.5, desert)
        _step(tr, 0.5, forest)
    assert tr.place == "biome:forest" and tr.visible() == []
    # stay in desert: announced once
    _step(tr, 1.5, desert)
    assert tr.place == "biome:desert" and tr.visible()[-1][0] == "Desert"
    _step(tr, 3.5, desert)
    # back to forest within 25s of its last card: accepted but NOT re-announced
    _step(tr, 1.5, forest)
    assert tr.place == "biome:forest" and tr.visible() == []
    # crossfade: a new place while a card is up -> old one fades out, new fades in, max 2 cards
    tr2 = zone_banner.ZoneTracker()
    _step(tr2, 0.6, nexus)
    _step(tr2, 0.35, zone_banner.hub_place("bazaar"))
    cards = tr2.visible()
    assert len(cards) == 2 and cards[0][0] == "Nexus" and cards[1][0] == "The Bazaar", cards
    assert cards[0][2] < 1.0 and cards[1][2] < 1.0
    _step(tr2, 0.6, zone_banner.hub_place("bazaar"))
    assert [c[0] for c in tr2.visible()] == ["The Bazaar"]
    # the music choice follows places (hub switches immediately on zone change)
    assert tr2.music.value == "bazaar"
    print("check_banner_dwell_repeat_and_crossfade: PASSED")


def check_realm_place_resolution():
    areas = {"places": [{"key": "tavern_town", "name": "Tavern Town", "biome": "forest",
                         "x": 100, "y": 100, "w": 50, "h": 46}],
             "islands": [{"idx": 4, "label": "Bonshine Shard", "x": 600, "y": 600}]}
    assert zone_banner.realm_place(areas, 110, 95, "forest")[1] == "area:tavern_town"
    isl = zone_banner.realm_place(areas, 610, 590, "desert")
    assert isl[1] == "island:4" and isl[4] == "island_shard"
    assert zone_banner.realm_place(areas, 300, 300, "ice")[1:3] == ("biome:ice", "Glacier")
    assert zone_banner.realm_place(areas, 300, 300, None) is None
    print("check_realm_place_resolution: PASSED")


def check_banner_rect_clear_of_hud():
    dock = ui.dock_frame_rect()
    for title in ("Nexus", "Abyssal Rumnal", "Forgotten Vault", "Crystal Caverns"):
        r = ui.zone_banner_rect(title, "Dungeon [Hard]")
        assert not r.colliderect(dock), (title, r, dock)
        assert r.bottom < 82, "must stay above the hub hint / item feed"
        assert r.left >= ui.SCREEN_EDGE_MARGIN and r.top >= ui.SCREEN_EDGE_MARGIN
    ui.draw_zone_banners(screen, [("Nexus", "Safe zone", 0.4), ("The Bazaar", "Safe zone", 1.0)])
    print("check_banner_rect_clear_of_hud: PASSED")


def check_clients_wire_it():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in ("main.py", "coop_client.py"):
        src = open(os.path.join(root, f), encoding="utf-8").read()
        assert "zone_tracker.observe" in src and "draw_zone_banners" in src and "audio.update_music()" in src, f
    assert audio._MUSIC_DISABLED == (os.environ.get("RR_NO_MUSIC", "") not in ("", "0"))
    print("check_clients_wire_it: PASSED")


if __name__ == "__main__":
    check_every_place_has_a_distinct_track()
    check_one_minute_bar_aligned_seamless_loops()
    check_cache_and_background_render()
    check_music_hysteresis()
    check_banner_dwell_repeat_and_crossfade()
    check_realm_place_resolution()
    check_banner_rect_clear_of_hud()
    check_clients_wire_it()
    print("PASSED: music + zone banner checks all green.")

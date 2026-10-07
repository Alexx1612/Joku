"""
Danger by distance (game/danger.py) and the in-game Calendar (game/calendar_ui.py +
RealmSim.forecast_view): mobs near the centre of the continent are much tougher (and pay
better, and drop harder dungeons), the coast is gentle; the calendar's forecast is exactly
what the coming nights turn out to be.

Run with: .venv\\Scripts\\python.exe tests\\check_danger_and_calendar.py
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
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_dc_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_dc_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_dc_ach_")

from game import realm_sim as rs, danger, calendar_ui, live_events, minimap, items as I
from game.realm_sim import RealmSim
from game.entities import Player, Enemy
from game.constants import TILE

# the forecast checks the live event due at each nightfall on the REAL clock; this test plays
# whole nights in seconds, so the schedule is held off (the suite does the same - RR_EVENT_ROTATION)
live_events._rotation = False
random.seed(13)
SIM = RealmSim()
C = SIM.realm_map.center_world_pos()
R = danger.continent_radius_px()


def _at(frac, kind="goblin"):
    """A fresh mob at this danger, run through the danger pass."""
    e = Enemy(kind, C + pygame.Vector2(R * (1 - frac), 0))
    SIM.enemies = [e]
    SIM._apply_danger()
    return e


def check_danger_gradient():
    assert abs(danger.danger_frac(C.x, C.y, SIM.realm_map.w, SIM.realm_map.h) - 1.0) < 1e-6
    assert danger.danger_frac(C.x + R * 0.999, C.y, SIM.realm_map.w, SIM.realm_map.h) < 0.01
    assert danger.danger_frac(C.x + R * 1.5, C.y, SIM.realm_map.w, SIM.realm_map.h) is None, "islands: own scale"
    assert [danger.tier(f) for f in (0.0, 0.25, 0.5, 0.7, 0.95)] == [1, 2, 3, 4, 5]
    edge, mid, core = _at(0.02), _at(0.5), _at(0.98)
    assert edge.hp_max < mid.hp_max < core.hp_max and core.hp_max >= edge.hp_max * 3, \
        (edge.hp_max, mid.hp_max, core.hp_max)
    assert edge.dmg[1] < core.dmg[1] and edge.speed < core.speed and edge.fire_rate_mult > core.fire_rate_mult
    assert edge.aggro_range < core.aggro_range
    hp = core.hp_max
    SIM._apply_danger()
    assert core.hp_max == hp, "applied once"
    # neutral wildlife and dungeons are untouched
    deer = Enemy("deer", C)
    SIM.enemies = [deer]
    SIM._apply_danger()
    assert deer.hp_max == Enemy("deer", C).hp_max
    bonus = RealmSim(bonus=True, theme="generic", difficulty_name="Easy")
    assert bonus.danger_at(C) is None
    print(f"check_danger_gradient: PASSED (goblin HP coast {edge.hp_max} / mid {mid.hp_max} / centre {core.hp_max})")


def check_danger_survives_night_rules():
    e = Enemy("goblin", C + pygame.Vector2(R * 0.05, 0))
    SIM.enemies = [e]
    SIM.night._apply_rules(True)  # night captured its "day" stats before the danger pass
    SIM._apply_danger()
    SIM.night._apply_rules(False)  # dawn restores ... the DANGER-scaled day stats
    ref = _at(0.95)
    assert abs(e.dmg[1] - ref.dmg[1]) <= 1 and abs(e.speed - ref.speed) < 1e-6, (e.dmg, ref.dmg)
    print("check_danger_survives_night_rules: PASSED")


def check_rewards_and_dungeons():
    m0, m1 = danger.mults(0.0), danger.mults(1.0)
    assert m1["xp"] > 1 > m0["xp"] and m1["loot_extra"] > 0 == m0["loot_extra"] and m1["portal"] > m0["portal"]
    random.seed(3)
    counts = {t: {"Easy": 0, "Medium": 0, "Hard": 0} for t in (1, 5)}
    for t in (1, 5):
        for _ in range(600):
            counts[t][rs.shard_difficulty("generic", t)] += 1
    assert counts[1]["Hard"] == 0 and counts[1]["Easy"] > 400, counts
    assert counts[5]["Hard"] > counts[5]["Easy"] * 5, counts
    assert rs.shard_difficulty("heroic_generic" if "heroic_generic" in rs.DUNGEON_THEMES else
                               next(k for k in rs.DUNGEON_THEMES if k.startswith(rs.HEROIC_PREFIX)), 1) == "Heroic"
    # an elite killed at the centre drops a shard that remembers it
    p = Player("warrior", "Dang", pid="dg")
    p.pos = C + pygame.Vector2(R * 0.02, 0)
    while p.level < 20:
        p.gain_xp(10 ** 5)
    old = danger.HEROIC_SHARD_CHANCE_T5
    try:
        for heroic_chance in (0.0, 1.0):
            danger.HEROIC_SHARD_CHANCE_T5 = heroic_chance
            kind = next(k for k, t in rs.THEME_FOR_KIND.items()
                        if rs.HEROIC_PREFIX + t in rs.DUNGEON_THEMES and rs.ENEMY_KINDS[k]["rank"] == "elite")
            e = _at(0.97, kind)
            e.story_guardian = 1  # (forces the shard drop)
            SIM.ground_items = []
            SIM._reward(e, p)
            shards = [it for b in SIM.ground_items for it in b.items if it.slot == "shard"]
            assert shards and shards[0].danger == 5, [(it.name, it.danger) for it in shards]
            assert shards[0].shard_theme.startswith(rs.HEROIC_PREFIX) == (heroic_chance == 1.0)
            back = I.Item.from_json(shards[0].to_json())
            assert back.danger == 5
    finally:
        danger.HEROIC_SHARD_CHANCE_T5 = old
    p.backpack = [I.make_dungeon_shard("generic", "Generic", danger=4)]
    assert p.use_shard(0) == "generic" and p.last_shard_danger == 4
    print(f"check_rewards_and_dungeons: PASSED (coast {counts[1]}, centre {counts[5]})")


def check_forecast_comes_true():
    random.seed(21)
    sim = RealmSim()
    p = Player("warrior", "Cal", pid="cal")
    p.pos = sim.spawn_point()
    p.hp = p.hp_max = 10 ** 7
    sim.day_time = 10.0
    fc = sim.forecast_view()
    assert len(fc) == rs.FORECAST_NIGHTS
    assert all(fc[i]["eta"] < fc[i + 1]["eta"] for i in range(len(fc) - 1))
    assert abs(fc[0]["eta"] - (rs.NIGHTFALL_T - 10.0)) < 0.5
    seen = []
    for _ in range(3):  # play three whole nights
        target = fc[len(seen)]
        while not sim.is_night:
            sim.begin_tick()
            sim.update(0.5, {p.pid: p})
        seen.append((sim.blood_moon_active, sim.sky.weather, sim.night.event, sim.moon_phase()))
        assert seen[-1] == (target["blood"], target["weather"],
                            "blood_moon" if target["blood"] else target["event"], target["phase"]), (seen[-1], target)
        while sim.is_night:
            sim.begin_tick()
            sim.update(0.5, {p.pid: p})
    print(f"check_forecast_comes_true: PASSED ({seen})")


def check_calendar_ui_and_clock():
    SIM.day_time = 100
    c = SIM.clock_info()
    assert c["forecast"] and len(c["forecast"]) == rs.FORECAST_NIGHTS and "night_no" in c
    import json
    json.dumps(c)  # rides in co-op snapshots
    calendar_ui.draw(screen, c)
    SIM.day_time = 420
    calendar_ui.draw(screen, SIM.clock_info())
    calendar_ui.draw(screen, None)  # outside the Realm
    live_events._rotation = True
    up = live_events.upcoming(3, 0.0)
    assert len(up) == 3 and up[0][1] == 0 and up[1][1] == live_events.EVENT_WINDOW, up
    live_events._rotation = False
    assert calendar_ui.fmt_eta(3725) == "1h 02m" and calendar_ui.fmt_eta(65) == "1:05"
    # the danger HUD + rings draw on the Realm map only
    mm = minimap.MinimapState()
    minimap.draw_corner(screen, SIM.realm_map, mm, C)
    minimap.draw_full_map(screen, SIM.realm_map, mm, C, zone_name="Realm")
    assert minimap._danger_label(SIM.realm_map, C)[0] == "Lethal"
    print("check_calendar_ui_and_clock: PASSED")


if __name__ == "__main__":
    check_danger_gradient()
    check_danger_survives_night_rules()
    check_rewards_and_dungeons()
    check_forecast_comes_true()
    check_calendar_ui_and_clock()
    print("\nALL DANGER + CALENDAR CHECKS PASSED")

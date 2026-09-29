"""
Combat feel rework (V0.2 polish): per-mob attack sets, telegraphs, bullet
motions, the screen-shake policy and the new sound effects.

- every hostile kind has its own move set; no non-boss move is an untelegraphed
  full ring (the old "everything sprays a ring" look)
- trash (the common fodder) only has plain basics: no named specials, no rings /
  AoEs / dashes, no telegraph at all; elites / mini-bosses / bosses carry the
  specials, hardened, and ONLY dangerous moves are telegraphed
- bosses / island mini-bosses rotate >= 3 named moves and break into phase 2
- ground AoEs are telegraphed for their whole wind-up before they hurt anyone
- sine / accel (brake to a stop) / homing (capped turn) / split bullets behave
- shake: dealing damage never shakes; the local player being hit does (scaled);
  another co-op player being hit doesn't; a far world-boss spawn doesn't; a
  boss phase change does
- sfx: every weapon type / ability style / enemy attack key has a distinct
  cached sound, and the rate limiter caps repeats

Run with: .venv\\Scripts\\python.exe tests\\check_combat_feel.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((400, 300))

from game import enemy_attacks as EA, vfx, audio
from game.entities import ENEMY_KINDS, Enemy, _mk_bullet
from game.realm_sim import RealmSim, ISLAND_MINI_BOSS
from game.entities import BOSS_KINDS

HOSTILE = [k for k, d in ENEMY_KINDS.items() if not d.get("neutral")]


def check_every_hostile_kind_has_an_attack_set():
    missing = [k for k in HOSTILE if not EA.moves_for(k)]
    assert not missing, f"hostile kinds with no attack set: {missing}"
    for k in HOSTILE:
        for m in EA.moves_for(k):
            assert m["fn"] in EA.PRIMITIVES, (k, m["fn"])
            assert m["windup"] > 0 and m["cd"] > 0, (k, m["name"])
    print(f"check_every_hostile_kind_has_an_attack_set: PASSED ({len(HOSTILE)} kinds)")


def check_no_untelegraphed_full_rings_for_regular_mobs():
    bad = []
    for k in HOSTILE:
        if ENEMY_KINDS[k]["rank"] == "boss":
            continue
        for m in EA.moves_for(k):
            if EA.full_ring_untelegraphed(m):
                bad.append((k, m["name"]))
    assert not bad, f"untelegraphed full rings: {bad}"
    # and rings in general always have gaps
    for k in HOSTILE:
        for m in EA.moves_for(k):
            if m["fn"] == "ring":
                assert m.get("gaps", 2) >= 2 and m.get("tele") != "glow", (k, m["name"])
    print("check_no_untelegraphed_full_rings_for_regular_mobs: PASSED")


def check_bosses_have_named_rotations_and_a_phase_change():
    bosses = list(BOSS_KINDS) + list(ISLAND_MINI_BOSS.values()) + ["mad_god"]
    for k in bosses:
        moves = EA.moves_for(k)
        names = {m["name"] for m in moves}
        assert len(names) >= 3, (k, names)
        assert any(m.get("phase", 1) == 2 or m.get("p2") for m in moves), f"{k} has no phase-2 move"
    # the real phase break: below 50% HP -> phase 2, a roar window, the flag the sim turns into vfx/sfx
    e = Enemy("cinder_colossus", pygame.Vector2(0, 0))
    e.hp = int(e.hp_max * 0.4)
    e.update(0.02, pygame.Vector2(200, 0), [], tile_map=None)
    assert e.phase == 2 and e._phase_pending and e._phase_invuln > 0
    assert e.take_damage(50) is False and e.hp == int(e.hp_max * 0.4), "no damage during the phase roar"
    print(f"check_bosses_have_named_rotations_and_a_phase_change: PASSED ({len(bosses)} bosses)")


def _sim_with(kind):
    sim = RealmSim(bonus=True, theme="forge", difficulty_name="Medium", story_act=0)
    center = pygame.Vector2(sim.boss.pos)
    e = Enemy(kind, center)
    e.set_special(True)  # a dungeon-room / guardian elite - the open-Realm version only shoots basics
    e.aggro = True
    sim.enemies = [e]
    sim.boss = None
    return sim, e, center


def check_ground_aoe_is_telegraphed_before_it_hurts():
    from game.entities import Player
    sim, e, center = _sim_with("troll")  # an elite - trash has no ground AoEs
    lob = next(m for m in e._attacks if m["fn"] == "lob")
    p = Player("wizard", "Target", pid="p1")
    p.pos = center + pygame.Vector2(120, 0)
    p.hp = p.hp_max
    # force the lob right now
    e._atk_cds = {m["name"]: (0 if m is lob else 99) for m in e._attacks}
    e._atk_gap = 0
    sim.begin_tick()
    sim.update(1 / 30, {"p1": p})
    zones = [z for z in sim.enemy_zones if z["dmg"] > 0]
    assert zones, "the lob must put a damaging ground zone down at wind-up start"
    z = zones[0]
    assert (pygame.Vector2(z["x"], z["y"]) - p.pos).length() < z["r"], "it lands where you stand/are headed"
    hp_during = p.hp
    steps = int((lob["windup"] - 0.1) * 30)
    for _ in range(steps):  # the whole telegraph: nothing hurts yet (stand still to test the zone only)
        sim.begin_tick()
        sim.update(1 / 30, {"p1": p})
    zdmg = [ev for ev in sim.vfx_events if ev[0] == "enemy_slam"]
    assert not zdmg, "the zone must not resolve before its wind-up ends"
    for _ in range(12):
        sim.begin_tick()
        sim.update(1 / 30, {"p1": p})
        if any(ev[0] == "enemy_slam" for ev in sim.vfx_events):
            break
    assert p.hp < hp_during, "standing in the zone when it lands must hurt"
    # co-op snapshot form of a zone
    e2 = Enemy("troll", center)
    EA._zone(e2, "circle", center, 1.0, EA.ORANGE, dmg_mult=1.0, r=50)
    sim.enemy_zones = e2._new_zones
    snap = sim.zone_snapshot(center, 1000)
    assert snap and snap[0][0] == "c" and snap[0][3] == 50
    vfx.draw_enemy_zones(screen, lambda pos: (int(pos[0] - center.x + 200), int(pos[1] - center.y + 150)), snap)
    print("check_ground_aoe_is_telegraphed_before_it_hurts: PASSED")


def check_bullet_motions():
    # sine: sways sideways but keeps travelling along its base direction
    b = _mk_bullet((0, 0), pygame.Vector2(1, 0), 200, 5, (255, 255, 255), motion="sine", lifetime=3,
                   wave_amp=30, wave_freq=6.0)
    ys = []
    for _ in range(30):
        b.update(1 / 30)
        ys.append(b.pos.y)
    assert b.pos.x > 150 and max(ys) > 20 and min(ys) < -20, "sine bullets snake around their line"
    # accel with negative accel brakes to a full stop (mines) and then just sits
    m = _mk_bullet((0, 0), pygame.Vector2(1, 0), 200, 5, (255, 255, 255), motion="accel", lifetime=3,
                   accel=-400.0, min_speed=0.0)
    for _ in range(30):
        m.update(1 / 30)
    x_stop = m.pos.x
    m.update(1 / 30)
    assert m.vel.length() == 0 and abs(m.pos.x - x_stop) < 1e-6
    # homing turns toward its target but never faster than home_turn rad/s
    h = _mk_bullet((0, 0), pygame.Vector2(1, 0), 100, 5, (255, 255, 255), motion="homing", lifetime=3,
                   home_turn=1.0)
    h.target = pygame.Vector2(0, 500)
    h.update(0.5)
    ang = math.atan2(h.vel.y, h.vel.x)
    assert 0 < ang <= 0.5 + 1e-6, f"turned {ang} rad in 0.5s with a 1 rad/s cap"
    # split: bursts into N children when its life ends
    s = _mk_bullet((0, 0), pygame.Vector2(1, 0), 100, 10, (255, 255, 255), lifetime=0.1, split=4, split_speed=150)
    assert s.update(0.2) is False
    kids = s.split_children(None)
    assert len(kids) == 4 and all(k.vel.length() > 100 for k in kids)
    print("check_bullet_motions: PASSED")


def _reset_shake():
    vfx._shake_mag = 0.0
    vfx._shake_time = 0.0
    vfx._hitstop_until = 0


def check_shake_policy():
    vfx.set_listener((0, 0), "me")
    _reset_shake()
    vfx.dispatch([("hit_enemy", 10, 10, (255, 220, 90)), ("hit_boss", 10, 10, (255, 220, 90))])
    assert vfx._shake_time == 0, "hitting mobs never shakes"
    _reset_shake()
    vfx.dispatch([("ab_ruin", 0, 0, (200, 100, 255)), ("nova", 0, 0, (200, 100, 255))])
    assert vfx._shake_time == 0, "your own abilities never shake"
    _reset_shake()
    vfx.dispatch([("hit_player", 0, 0, (255, 90, 90), "other", 40, 300)])
    assert vfx._shake_time == 0, "another co-op player being hit must not shake MY screen"
    _reset_shake()
    vfx.dispatch([("hit_player", 0, 0, (255, 90, 90), "me", 3, 300)])
    small = vfx._shake_time, vfx._shake_mag
    _reset_shake()
    vfx.dispatch([("hit_player", 0, 0, (255, 90, 90), "me", 60, 300)])
    big = vfx._shake_time, vfx._shake_mag
    assert big[1] > 0 and big[1] > small[1], "a bigger chunk of your HP shakes harder"
    _reset_shake()
    vfx.dispatch([("world_boss_appear", 1200, 0, (200, 80, 255))])
    assert vfx._shake_time == 0, "a far-away world boss spawn doesn't shake"
    _reset_shake()
    vfx.dispatch([("boss_appear", 5000, 0, (200, 80, 255))])
    assert vfx._shake_time == 0, "a boss appearing far away doesn't shake"
    _reset_shake()
    vfx.dispatch([("boss_phase", 100, 0, (255, 120, 60))])
    assert vfx._shake_mag >= 10, "a nearby boss phase change shakes"
    _reset_shake()
    vfx.dispatch([("enemy_slam", 1000, 0, (255, 150, 40), 60, 1)])
    assert vfx._shake_time == 0, "slams far away don't shake"
    vfx.dispatch([("enemy_slam", 100, 0, (255, 150, 40), 60, 1)])
    assert vfx._shake_time > 0, "a slam near you does"
    vfx.set_listener(None, None)
    _reset_shake()
    print("check_shake_policy: PASSED")


def check_sfx_distinct_cached_and_rate_limited():
    from game.vfx import ABILITY_STYLES
    weapon = {w: bytes(bytearray(str(audio._weapon_sound(w)[:400]), "ascii")) for w in set(audio.WEAPON_TYPE.values())}
    assert len(weapon) == 8 and len(set(weapon.values())) == 8, "8 weapon types, 8 different shot sounds"
    styles = set(ABILITY_STYLES.values())
    assert styles <= set(audio.ABILITY_SOUND), f"missing ability sounds: {styles - set(audio.ABILITY_SOUND)}"
    params = [audio.ABILITY_SOUND[s] for s in styles]
    assert len(set(params)) == len(params), "each ability style sounds different"
    keys = {m["sfx"] for k in HOSTILE for m in EA.moves_for(k)} | {"windup", "dash_windup", "boss_phase", "slam"}
    missing = keys - set(audio.ENEMY_ATTACK_SOUND)
    assert not missing, f"attack sfx keys without a sound: {missing}"
    assert len(set(audio.ENEMY_ATTACK_SOUND.values())) == len(audio.ENEMY_ATTACK_SOUND)
    # rate limiter: the same sound can't retrigger within SFX_MIN_INTERVAL, and a window has a budget
    audio._last_played.clear()
    assert audio._rate_ok("x", now=100.0) and not audio._rate_ok("x", now=100.01)
    assert audio._rate_ok("x", now=100.0 + audio.SFX_MIN_INTERVAL + 0.001)
    audio._window_start, audio._window_count = 200.0, 0
    ok = sum(audio._rate_ok(f"k{i}", now=200.0 + i * 0.001) for i in range(40))
    assert ok == audio.SFX_WINDOW_BUDGET, ok
    # the real play path with cached buffers (mixer may be dummy/off - must not crash either way)
    audio.init()
    audio._last_played.clear()
    for w in ("wizard", "archer", "rogue", "paladin"):
        audio.play_shoot(w)
    audio.play_ability("thunder")
    audio.play_enemy_attack("slam")
    print("check_sfx_distinct_cached_and_rate_limited: PASSED")


def check_dash_windup_then_lunge():
    e = Enemy("panther", pygame.Vector2(0, 0))
    e.set_special(True)  # dashes are a special-mob move (dungeons / guardians)
    e.aggro = True
    e._atk_gap = 0
    e._atk_cds = {m["name"]: (0 if m["fn"] == "dash" else 99) for m in e._attacks}  # force the Pounce
    target = pygame.Vector2(300, 0)
    e.update(0.01, target, [], tile_map=None)
    assert e._windup is not None and e._windup["move"]["tele"] == "dash"
    start = pygame.Vector2(e.pos)
    e.update(e._windup["total"] * 0.5, target, [], tile_map=None)
    assert (e.pos - start).length() < 1, "planted during the wind-up (readable)"
    e.update(e._windup["total"], target, [], tile_map=None)  # wind-up ends -> dash starts
    moved_from = pygame.Vector2(e.pos)
    e.update(0.1, target, [], tile_map=None)
    assert (e.pos - moved_from).x > e.speed * 0.1 * 2, "the lunge is much faster than walking"
    print("check_dash_windup_then_lunge: PASSED")


TRASH = [k for k in HOSTILE if ENEMY_KINDS[k]["rank"] == "trash" and not k == "totem"]
SPECIAL = [k for k in HOSTILE if ENEMY_KINDS[k]["rank"] in ("elite", "boss")]
BASIC_FNS = ("fan", "sine", "boomerang")


def check_trash_has_only_plain_untelegraphed_basics():
    assert len(TRASH) >= 8, TRASH
    for k in TRASH:
        for m in EA.moves_for(k):
            assert m["fn"] in BASIC_FNS, f"{k}: trash move {m['name']} uses {m['fn']}"
            assert m["tele"] == "none" and not EA.is_dangerous(m), f"{k}: {m['name']} is telegraphed"
            assert m["fn"] != "fan" or m.get("n", 1) <= 3, f"{k}: {m['name']} is not a small fan"
    # and in play: a trash mob never glows / flags a tell before shooting
    e = Enemy("goblin", pygame.Vector2(0, 0))
    e.aggro = True
    e._atk_gap = 0
    out = []
    for _ in range(90):
        e.update(1 / 30, pygame.Vector2(200, 0), out, tile_map=None)
        assert not e._pretelegraph and e._windup_kind is None and not e._new_zones
    assert out, "the goblin still shoots"
    print(f"check_trash_has_only_plain_untelegraphed_basics: PASSED ({len(TRASH)} kinds)")


def check_special_mobs_have_specials_and_only_dangerous_tells():
    danger_fns = ("lob", "slam", "rain", "eruption", "leap", "dash", "beam", "root_pulse")
    for k in SPECIAL:
        moves = EA.moves_for(k)
        need = 3 if ENEMY_KINDS[k]["rank"] == "boss" else 2
        assert len({m["name"] for m in moves}) >= need, (k, [m["name"] for m in moves])
        for m in moves:
            if m["fn"] in danger_fns:
                assert EA.is_dangerous(m), f"{k}: dangerous {m['name']} ({m['fn']}) has no telegraph"
            if m["fn"] in ("fan", "sine", "homing", "boomerang", "split") and m.get("tele") in ("none", None):
                assert not EA.is_dangerous(m)
    # ordinary aimed/fan/volley moves carry no tell, even on elites and bosses
    plain = [(k, m["name"]) for k in SPECIAL for m in EA.moves_for(k)
             if m["fn"] == "fan" and m["tele"] == "glow"]
    assert not plain, f"plain fans still glow: {plain[:5]}"
    # hardened vs the raw table: faster and on a shorter cycle
    raw = EA.ATTACKS["boss"][0]
    hard = EA.moves_for("boss")[0]
    assert hard["cd"] < raw["cd"] and hard.get("speed", 1) > raw.get("speed", 1.0)
    assert any(m["name"] == "Crossfire" for m in EA.moves_for("frost_monarch")), "bosses get the Crossfire combo"
    print(f"check_special_mobs_have_specials_and_only_dangerous_tells: PASSED ({len(SPECIAL)} kinds)")


def check_specials_only_for_special_mobs():
    """Everyday mobs in the open Realm / on islands (any rank) use basic shots only;
    the same kinds inside a dungeon room, landmark guardians, island anchors and
    bosses/mini-bosses fight with their named special moves."""
    for k in HOSTILE:
        if k == "totem":
            continue
        e = Enemy(k, pygame.Vector2(0, 0))
        boss_or_anchor = ENEMY_KINDS[k]["rank"] == "boss" or k in EA.SPECIAL_BY_KIND
        assert e.special == boss_or_anchor, (k, e.special)
        if not e.special:
            assert 1 <= len(e._attacks) <= 2, (k, [m["name"] for m in e._attacks])
            for m in e._attacks:
                assert m["fn"] in BASIC_FNS and not EA.is_dangerous(m), f"{k}: basic {m['name']} ({m['fn']})"
                assert m["fn"] != "fan" or (m.get("n", 1) <= 3 and m.get("spread", 0) <= 30), (k, m["name"])
    # open-Realm elite = basic, the same kind in a dungeon room = specials (promoted by the sim)
    e = Enemy("scorpion", pygame.Vector2(0, 0))
    assert not e.special and all(not EA.is_dangerous(m) for m in e._attacks)
    dung = RealmSim(bonus=True, theme="generic")
    probe = Enemy("scorpion", dung.boss.pos + pygame.Vector2(120, 0))
    dung.enemies.append(probe)
    from game.entities import Player
    p = Player("wizard", name="Spec", pid="spec")
    p.pos = pygame.Vector2(probe.pos) + pygame.Vector2(80, 0)
    dung.begin_tick()
    dung.update(1 / 30, {p.pid: p})
    assert probe.special and {m["name"] for m in probe._attacks} == {m["name"] for m in EA.moves_for("scorpion")}
    # everyday realm mobs stay basic after being simulated
    realm = RealmSim()
    sp = realm.spawn_point()
    q = Player("wizard", name="Basic", pid="basic")
    q.pos = pygame.Vector2(sp)
    wild = Enemy("yeti", sp + pygame.Vector2(150, 0))
    realm.enemies.append(wild)
    realm.begin_tick()
    realm.update(1 / 30, {q.pid: q})
    assert not wild.special
    print("check_specials_only_for_special_mobs: PASSED")


if __name__ == "__main__":
    check_every_hostile_kind_has_an_attack_set()
    check_no_untelegraphed_full_rings_for_regular_mobs()
    check_bosses_have_named_rotations_and_a_phase_change()
    check_ground_aoe_is_telegraphed_before_it_hurts()
    check_bullet_motions()
    check_shake_policy()
    check_sfx_distinct_cached_and_rate_limited()
    check_dash_windup_then_lunge()
    check_trash_has_only_plain_untelegraphed_basics()
    check_special_mobs_have_specials_and_only_dangerous_tells()
    check_specials_only_for_special_mobs()
    print("PASSED: combat feel checks all green.")

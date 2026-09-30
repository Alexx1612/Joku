"""
Telegraph accuracy: a warning must never lie.

For EVERY telegraphed move of every special mob (bosses, mini-bosses, elites
fighting with their dungeon/guardian move sets) the check forces the move,
lets its warning appear, then strafes the player sideways for the whole
wind-up. Whatever finally fires must match what was drawn at wind-up start:

- spokes (ring / half-ring / fan-sweep / accel / sine telegraphs): every bullet
  flies along one of the drawn spokes (so ring gaps are where the drawing
  showed them) - never re-aimed at the moved player
- lines (beams, lances, snares, bullet walls): every bullet flies along the lane
  and starts inside it; a wall leaves its drawn gap empty
- cones (sprays): every bullet flies inside the cone
- dash lanes: every dash (chained dashes included) goes down its own lane
- slam / leap bursts: the burst bullets fly along the spokes drawn with the slam
- nothing that shows only a warning circle fires bullets out past that circle
  (Crossfire used to), and a root pulse roots exactly the drawn radius

Run with: .venv\\Scripts\\python.exe tests\\check_telegraph_accuracy.py
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

from game import enemy_attacks as EA, vfx
from game.entities import ENEMY_KINDS, Enemy

DT = 1 / 60
BULLET_FNS = ("fan", "ring", "half_ring", "wall", "beam", "sine", "homing", "accel", "mines", "split",
              "boomerang", "spray")


def _angdiff(a, b):
    return abs(((a - b) + 180) % 360 - 180)


def _kinds():
    return [k for k, d in ENEMY_KINDS.items() if not d.get("neutral") and EA.moves_for(k)]


def _force(e, move):
    e.phase = 2
    e._is_phase2_room = True
    e._atk_cds = {m["name"]: (0 if m is move else 999) for m in e._attacks}
    e._atk_gap = 0
    e.aggro = True


def _run_move(kind, move, strafe=True):
    """Returns (zones pushed at wind-up start, bullets fired [(pos, dir)], dashes [(start, dir)])."""
    e = Enemy(kind, pygame.Vector2(0, 0))
    e.set_special(True)
    e.invulnerable = False
    _force(e, move)
    player = pygame.Vector2(220, 0)
    bullets = []
    e.update(DT, player, bullets, tile_map=None)
    zones = list(e._new_zones)
    assert e._windup is not None and e._windup["move"]["name"] == move["name"], (kind, move["name"])
    fired, dashes, seen = [], [], 0
    was_dashing = False
    total = move.get("windup", 0.3) + move.get("shell", 0) + move.get("repeat", 1) * (move.get("gap", 0.15) + 0.6) + 1.2
    t = 0.0
    while t < total:
        t += DT
        if strafe:  # sidestep hard during the whole wind-up (and after): a re-aim would follow this
            player = pygame.Vector2(220, 0) + pygame.Vector2(0, 1) * min(260.0, 400.0 * t)
        e._atk_cds = {m["name"]: 999 for m in e._attacks}  # nothing else may start
        e.update(DT, player, bullets, tile_map=None)
        for b in bullets[seen:]:
            fired.append((pygame.Vector2(b.origin), pygame.Vector2(b.vel).normalize() if b.vel.length() else None))
        seen = len(bullets)
        if e._dash is not None and not was_dashing:
            dashes.append((pygame.Vector2(e.pos), pygame.Vector2(e._dash["dir"])))
        was_dashing = e._dash is not None
        for z in e._new_zones:
            if z not in zones:
                zones.append(z)
    return e, zones, fired, dashes


def check_telegraphed_bullets_match_their_warning():
    checked = 0
    for k in _kinds():
        for m in EA.moves_for(k):
            if m.get("tele", "none") in ("none", "glow"):
                continue
            fn = m["fn"]
            then = m.get("then") if fn == "shell" else None
            if fn not in BULLET_FNS and not (then and then["fn"] in BULLET_FNS):
                continue
            e, zones, fired, _ = _run_move(k, m)
            assert fired, f"{k}/{m['name']}: nothing fired"
            spokes = [z for z in zones if z["shape"] == "spokes"]
            lines = [z for z in zones if z["shape"] == "line"]
            cones = [z for z in zones if z["shape"] == "cone"]
            if m["tele"] == "ring":
                assert spokes, f"{k}/{m['name']}: a bullet move warned with a plain circle"
                angs = [a for z in spokes for a in z["angles"]]
                for pos, d in fired:
                    if d is None:
                        continue
                    a = d.as_polar()[1]
                    best = min(_angdiff(a, s) for s in angs)
                    # sine / jitter moves wobble a little around their spoke
                    tol = 30 if (then or m)["fn"] == "sine" else 3.0
                    assert best <= tol, f"{k}/{m['name']}: bullet at {a:.1f} deg is on no drawn spoke ({best:.1f} off)"
            elif m["tele"] == "line":
                z = lines[0]
                for pos, d in fired:
                    assert _angdiff(d.as_polar()[1], z["ang"]) <= 3.0, \
                        f"{k}/{m['name']}: fired {d.as_polar()[1]:.1f} but the lane points {z['ang']:.1f}"
                    rel = pos - pygame.Vector2(z["x"], z["y"])
                    u = pygame.Vector2(1, 0).rotate(z["ang"])
                    side = rel.x * -u.y + rel.y * u.x
                    assert abs(side) <= z["width"] / 2 + 1, f"{k}/{m['name']}: a bullet started outside its lane"
                    if z.get("gap_off") is not None:
                        assert abs(side - z["gap_off"]) >= z["gap_w"] / 2 - 1, \
                            f"{k}/{m['name']}: a wall bullet sits in the drawn gap"
                assert z["length"] >= EA.reach(m) - 1, f"{k}/{m['name']}: the lane is shorter than the shots fly"
            elif m["tele"] == "cone":
                z = cones[0]
                for pos, d in fired:
                    assert _angdiff(d.as_polar()[1], z["ang"]) <= z["width"] / 2 + 0.5, \
                        f"{k}/{m['name']}: a spray bullet left its cone"
                assert z["life"] >= m["windup"] + (m.get("repeat", 1) - 1) * m.get("gap", 0.15) - 1e-6, \
                    f"{k}/{m['name']}: the cone vanishes while it is still spraying"
            checked += 1
    assert checked >= 40, checked
    print(f"check_telegraphed_bullets_match_their_warning: PASSED ({checked} moves)")


def check_dashes_follow_their_lanes():
    checked = 0
    for k in _kinds():
        for m in EA.moves_for(k):
            if m["fn"] != "dash":
                continue
            e, zones, _, dashes = _run_move(k, m)
            lanes = [z for z in zones if z["shape"] == "line"]
            reps = m.get("repeat", 1)
            assert len(dashes) == reps, f"{k}/{m['name']}: {len(dashes)} dashes for repeat={reps}"
            assert len(lanes) == reps, f"{k}/{m['name']}: every chained dash needs its own lane ({len(lanes)})"
            for (start, d), z in zip(dashes, lanes):
                assert _angdiff(d.as_polar()[1], z["ang"]) <= 1.0, f"{k}/{m['name']}: dash left its lane"
                assert start.distance_to(pygame.Vector2(z["x"], z["y"])) <= 2, f"{k}/{m['name']}: lane origin"
            checked += 1
    assert checked >= 10, checked
    print(f"check_dashes_follow_their_lanes: PASSED ({checked} dash moves)")


def check_slam_bursts_follow_their_spokes():
    from game.realm_sim import RealmSim
    from game.entities import Player
    sim = RealmSim(bonus=True, theme="forge", difficulty_name="Medium", story_act=0)
    base = pygame.Vector2(sim.boss.pos)
    sim.realm_map.has_line_of_sight = lambda *a: True  # a random room wall must not block the forced move
    checked = 0
    for k in _kinds():
        for m in EA.moves_for(k):
            if m["fn"] not in ("slam", "leap") or not m.get("burst"):
                continue
            e = Enemy(k, pygame.Vector2(base))
            e.set_special(True)
            _force(e, m)
            sim.enemies = [e]
            sim.boss = None
            sim.enemy_zones = []
            sim.bullets = []
            p = Player("wizard", "Target", pid="p1")
            p.pos = base + pygame.Vector2(150, 0)
            p.hp = p.hp_max = 10 ** 6
            spokes = None
            for i in range(int((m["windup"] + m.get("dash_time", 0) + 0.5) / DT)):
                p.pos = base + pygame.Vector2(150, min(200, i * 6))
                e._atk_cds = {x["name"]: (0 if (x is m and i == 0) else 999) for x in e._attacks}
                sim.begin_tick()
                sim.update(DT, {"p1": p})
                if spokes is None:
                    sp = [z for z in sim.enemy_zones if z["shape"] == "spokes"]
                    if sp:
                        spokes = sp[0]
                if spokes is not None and not any(z is spokes for z in sim.enemy_zones):
                    break
            assert spokes is not None, f"{k}/{m['name']}: a slam burst has no spokes"
            burst = [b for b in sim.bullets if b.owner == "enemy"
                     and b.origin.distance_to(pygame.Vector2(spokes["x"], spokes["y"])) < 2]
            assert burst, f"{k}/{m['name']}: no burst bullets from the impact point"
            for b in burst:
                a = b.vel.as_polar()[1]
                assert min(_angdiff(a, s) for s in spokes["angles"]) <= 3.0, \
                    f"{k}/{m['name']}: burst bullet off its drawn spoke"
            checked += 1
    assert checked >= 4, checked
    print(f"check_slam_bursts_follow_their_spokes: PASSED ({checked} slam/leap bursts)")


def check_no_circle_only_warning_fires_bullets_past_it():
    bad = []
    for k in _kinds():
        for m in EA.moves_for(k):
            if m.get("tele") == "zone" and m["fn"] in BULLET_FNS:
                bad.append((k, m["name"]))
    assert not bad, f"ground-circle warnings that actually fire bullets: {bad}"
    cf = next(m for m in EA.moves_for("frost_monarch") if m["name"] == "Crossfire")
    assert cf["fn"] == "rain", "Crossfire's hits must be its warned circles"
    print("check_no_circle_only_warning_fires_bullets_past_it: PASSED")


def check_root_pulse_radius_is_the_drawn_circle():
    for k in _kinds():
        for m in EA.moves_for(k):
            if m["fn"] != "root_pulse":
                continue
            e = Enemy(k, pygame.Vector2(0, 0))
            e.set_special(True)
            _force(e, m)
            e.update(DT, pygame.Vector2(100, 0), [], tile_map=None)
            z = next(z for z in e._new_zones if z.get("effect") == "root")
            EA.p_root(e, None, m)
            assert float(e._root_pulse) == z["r"], (k, m["name"], e._root_pulse, z["r"])
    print("check_root_pulse_radius_is_the_drawn_circle: PASSED")


def check_new_zone_shapes_draw_and_survive_the_coop_snapshot():
    from game.realm_sim import RealmSim
    sim = RealmSim(bonus=True, theme="forge", difficulty_name="Medium", story_act=0)
    center = pygame.Vector2(sim.boss.pos)
    e = Enemy("choir_sovereign", center)
    ring = dict(fn="ring", n=18, gaps=3, gap_w=2)
    EA._zone(e, "spokes", center, 1.0, EA.ORANGE, r=200, sfx=None,
             extra=dict(angles=EA.spoke_angles(ring, pygame.Vector2(1, 0))))
    EA._zone(e, "line", center, 1.0, EA.RED, length=300, width=230, ang=30, sfx=None,
             extra=dict(gap_off=26.0, gap_w=30.0))
    sim.enemy_zones = e._new_zones
    snap = sim.zone_snapshot(center, 1000)
    assert snap[0][0] == "s" and len(snap[0][10]) == 18 - 6, snap[0]
    assert snap[1][0] == "l" and snap[1][10] == [26.0, 30.0], snap[1]
    cam = lambda pos: (int(pos[0] - center.x + 200), int(pos[1] - center.y + 150))
    screen.fill((0, 0, 0))
    vfx.draw_enemy_zones(screen, cam, snap)  # the co-op form
    vfx.draw_enemy_zones(screen, cam, sim.enemy_zones)  # the single-player form
    lit = sum(1 for x in range(0, 400, 4) for y in range(0, 300, 4) if screen.get_at((x, y))[:3] != (0, 0, 0))
    assert lit > 50, lit
    out = os.environ.get("RR_SHOT_DIR")
    if out:
        pygame.image.save(screen, os.path.join(out, "telegraph_spokes_and_wall_gap.png"))
    print("check_new_zone_shapes_draw_and_survive_the_coop_snapshot: PASSED")


if __name__ == "__main__":
    check_no_circle_only_warning_fires_bullets_past_it()
    check_root_pulse_radius_is_the_drawn_circle()
    check_telegraphed_bullets_match_their_warning()
    check_dashes_follow_their_lanes()
    check_slam_bursts_follow_their_spokes()
    check_new_zone_shapes_draw_and_survive_the_coop_snapshot()
    print("PASSED: telegraph accuracy checks all green.")

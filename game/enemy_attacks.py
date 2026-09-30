"""
Per-mob attack sets (combat feel rework, V0.2 polish).

Every hostile kind gets its own small move list instead of "everyone sprays a
ring": aimed/predictive shots, shotguns, bursts, sweeping arcs, sine streams,
slow homers, accelerating fireballs, seed mines, boomerangs, bullet walls
with a gap, telegraphed beams, lobbed ground AoEs, slams, leaps, dashes with a
wind-up and summons. Bosses and island mini-bosses rotate 3-4 NAMED moves and
unlock more (and speed up) when they drop below 50% HP.

Design rules (danmaku readability - see docs/unity-rebuild/30-combat-feel.md):
  * every ring has gaps and every ring / ground AoE / beam / dash is preceded
    by a visible telegraph (a coloured ground zone or aim line + a sprite glow)
  * colour tells the threat: red = aimed line / dash lane, orange = ground AoE,
    purple = homing
  * dense patterns are slow, fast patterns are sparse

A move is a dict:
  name     shown in the Dictionary / docs
  fn       primitive name (see PRIMITIVES below)
  windup   telegraph time before it fires (seconds)
  cd       its own cooldown (seconds)
  tele     "glow" (sprite glow only) | "line" | "zone" | "cone" | "ring" | "dash"
  weight   selection weight (default 1)
  phase    1 = always, 2 = only after the 50% HP phase break
  p2       True = only in the dungeon's _phase2 room fight
  root     stand still during the wind-up (default: True unless tele == "glow")
  sfx      sound key for game.audio.play_enemy_attack
  + primitive-specific params

The Enemy owns the state machine (entities.Enemy._update_attacks); this module
is data + the pure "what does this move spawn" functions. Enemies never touch
the sim directly: they push telegraph zones into e._new_zones, sounds into
e._sfx_pending and summons into e._summon_pending, which RealmSim drains.
"""
import math
import random

import pygame

RED = (235, 60, 50)
ORANGE = (255, 150, 40)
PURPLE = (190, 90, 255)
BASE_SPEED = 220.0

PHASE_BREAK_FRAC = 0.5       # bosses / mini-bosses change phase below this HP fraction
PHASE_BREAK_INVULN = 0.8     # a short "roar" window with no damage taken
PHASE2_CD_MULT = 0.6         # enrage: everything comes back much faster after the phase break
GLOBAL_GAP = (0.35, 0.7)     # breathing room between two moves of the same enemy
ATTACK_RANGE = 620.0         # won't start a move from further away than this


def _E():
    from game import entities
    return entities


def _bullet(e, pos, direction, speed_mult=1.0, dmg_mult=1.0, color=RED, size=0, life=2.4, **kw):
    E = _E()
    dmg = max(1, int(round(random.randint(*e.dmg) * dmg_mult)))
    speed_mult *= getattr(e, "bullet_speed_mult", 1.0)  # Heroic dungeons fire faster bullets
    b = E._mk_bullet(pos, pygame.Vector2(direction), BASE_SPEED * speed_mult, dmg, color,
                     radius=e._bullet_radius() + size, lifetime=life, **kw)
    return b


# ------------------------------------------------------------ primitives --
# fn(e, c) -> None; c is an AttackCtx. Bullets go to c.out, zones to e._new_zones.

class AttackCtx:
    __slots__ = ("aim", "target", "lead", "tele_dir", "tele_point", "out", "step")

    def __init__(self, aim, target, lead, tele_dir, tele_point, out, step=0):
        self.aim, self.target, self.lead = aim, target, lead
        self.tele_dir, self.tele_point, self.out, self.step = tele_dir, tele_point, out, step


def _dir_for(e, c, m):
    # a telegraphed move ALWAYS fires where its warning pointed (the direction is
    # fixed at wind-up start) - never re-aimed at wherever the player moved since
    if c.tele_dir is not None:
        return pygame.Vector2(c.tele_dir)
    if m.get("lead"):
        v = c.lead - e.pos
        if v.length_squared() > 1:
            return v.normalize()
    return pygame.Vector2(c.aim)


def p_fan(e, c, m):
    """n bullets spread over `spread` degrees around the aim (n=1 -> a single aimed shot)."""
    n = m.get("n", 1)
    spread = m.get("spread", 0)
    d = _dir_for(e, c, m).rotate(m.get("sweep_step", 0) * c.step)
    for i in range(n):
        off = 0 if n == 1 else -spread / 2 + spread * i / (n - 1)
        c.out.append(_bullet(e, e.pos, d.rotate(off), m.get("speed", 1.0), m.get("dmgm", 1.0),
                             m.get("color", RED), m.get("size", 0), m.get("life", 2.4),
                             motion=m.get("motion", "straight"), **m.get("bkw", {})))


def _ring_skip(m):
    n = m.get("n", 12)
    gaps = m.get("gaps", 2)
    gap_w = m.get("gap_w", 2)
    if m.get("aim_gap"):  # the gap is centred ON you: stand still = safe, strafe = hit
        return {((i - gap_w // 2) % n) for i in range(gap_w)} | {((n // 2 + i) % n) for i in range(gap_w)}
    skip = set()
    for g in range(gaps):
        start = int(g * n / gaps)
        for k in range(gap_w):
            skip.add((start + k) % n)
    return skip


def p_ring(e, c, m):
    """A ring WITH gaps (never a solid wall of bullets) - `gaps` holes of
    `gap_w` bullets each. The rotation comes from the telegraph (tele_dir =
    the ring's base angle, picked at wind-up start so the drawn spokes show the
    real gaps); untelegraphed rings pick a random side."""
    n = m.get("n", 12)
    if c.tele_dir is not None:
        base = pygame.Vector2(c.tele_dir).as_polar()[1]
    else:
        base = random.uniform(0, 360) if not m.get("aim_gap") else _dir_for(e, c, m).as_polar()[1]
    skip = _ring_skip(m)
    origin = c.tele_point if (m.get("at_point") and c.tele_point is not None) else e.pos
    for i in range(n):
        if i in skip:
            continue
        ang = base + 360 * i / n
        c.out.append(_bullet(e, origin, pygame.Vector2(1, 0).rotate(ang), m.get("speed", 0.8),
                             m.get("dmgm", 1.0), m.get("color", ORANGE), m.get("size", 0), m.get("life", 2.4)))


def p_half_ring(e, c, m):
    """A half-ring aimed at the player - dodge sideways around it."""
    n = m.get("n", 7)
    d = _dir_for(e, c, m)
    arc = m.get("arc", 180)
    for i in range(n):
        off = -arc / 2 + arc * i / (n - 1)
        c.out.append(_bullet(e, e.pos, d.rotate(off), m.get("speed", 0.85), m.get("dmgm", 1.0),
                             m.get("color", ORANGE), m.get("size", 1), m.get("life", 2.4)))


def p_wall(e, c, m):
    """A line of bullets perpendicular to the aim, marching at you, with one gap to slip through."""
    n = m.get("n", 7)
    spacing = m.get("spacing", 26)
    d = _dir_for(e, c, m)
    perp = d.rotate(90)
    gap = getattr(e, "_wall_gap", None)  # picked (and drawn) at wind-up start
    e._wall_gap = None
    if gap is None or not (1 <= gap <= n - 2):
        gap = random.randint(1, n - 2)
    for i in range(n):
        if abs(i - gap) <= m.get("gap_w", 0):
            continue
        pos = e.pos + perp * (i - (n - 1) / 2) * spacing
        c.out.append(_bullet(e, pos, d, m.get("speed", 0.7), m.get("dmgm", 1.0), m.get("color", RED),
                             m.get("size", 0), m.get("life", 3.0)))


def p_beam(e, c, m):
    """A telegraphed lance: a dense line of fast bullets down the aim line shown during the wind-up."""
    n = m.get("n", 6)
    d = pygame.Vector2(c.tele_dir) if c.tele_dir is not None else pygame.Vector2(c.aim)
    for i in range(n):
        pos = e.pos + d * (i * 14)
        c.out.append(_bullet(e, pos, d, m.get("speed", 1.7), m.get("dmgm", 1.0), m.get("color", RED),
                             m.get("size", 0), m.get("life", 1.6)))


def p_sine(e, c, m):
    """A snaking stream - one sine bullet per step of the repeat."""
    d = _dir_for(e, c, m)
    c.out.append(_bullet(e, e.pos, d, m.get("speed", 0.8), m.get("dmgm", 1.0), m.get("color", (120, 230, 120)),
                         0, m.get("life", 3.0), motion="sine",
                         wave_amp=m.get("amp", 28), wave_freq=m.get("freq", 7.0),
                         wave_phase=(c.step * 1.1) if m.get("phase_step", True) else 0.0))


def p_homing(e, c, m):
    """Slow homing orbs (purple) with a capped turn rate - outrun or out-turn them."""
    n = m.get("n", 2)
    d = _dir_for(e, c, m)
    for i in range(n):
        off = 0 if n == 1 else -30 + 60 * i / (n - 1)
        c.out.append(_bullet(e, e.pos, d.rotate(off), m.get("speed", 0.5), m.get("dmgm", 1.0), PURPLE,
                             m.get("size", 1), m.get("life", 3.2), motion="homing",
                             home_turn=m.get("turn", 1.6)))


def p_accel(e, c, m):
    """Fireballs that start slow and speed up (danger grows with distance)."""
    n = m.get("n", 1)
    spread = m.get("spread", 0)
    d = _dir_for(e, c, m)
    for i in range(n):
        off = 0 if n == 1 else -spread / 2 + spread * i / (n - 1)
        c.out.append(_bullet(e, e.pos, d.rotate(off), m.get("speed", 0.4), m.get("dmgm", 1.0),
                             m.get("color", (255, 120, 40)), m.get("size", 0), m.get("life", 2.6),
                             motion="accel", accel=m.get("accel", 330.0),
                             max_speed=BASE_SPEED * m.get("max_speed", 1.6)))


def p_mines(e, c, m):
    """Seed pods / bubble mines: fly out, brake to a stop, sit there, then pop into small bits."""
    n = m.get("n", 3)
    d = _dir_for(e, c, m)
    spread = m.get("spread", 50)
    for i in range(n):
        off = 0 if n == 1 else -spread / 2 + spread * i / (n - 1)
        c.out.append(_bullet(e, e.pos, d.rotate(off), m.get("speed", 1.0), m.get("dmgm", 1.0),
                             m.get("color", (200, 220, 90)), 2, m.get("life", 2.6), motion="accel",
                             accel=-BASE_SPEED * m.get("speed", 1.0) / 0.6, max_speed=999, min_speed=0.0,
                             split=m.get("pop", 4), split_speed=BASE_SPEED * 0.6))


def p_split(e, c, m):
    """A heavy shot that bursts into 3 when its life ends."""
    d = _dir_for(e, c, m)
    c.out.append(_bullet(e, e.pos, d, m.get("speed", 0.8), m.get("dmgm", 1.2), m.get("color", (255, 200, 90)),
                         2, m.get("life", 1.1), split=m.get("pieces", 3), split_speed=BASE_SPEED * 0.9,
                         split_aimed=True))


def p_boomerang(e, c, m):
    d = _dir_for(e, c, m)
    for off in m.get("offs", (-15, 15)):
        c.out.append(_bullet(e, e.pos, d.rotate(off), m.get("speed", 1.0), m.get("dmgm", 1.0),
                             m.get("color", (230, 220, 200)), 1, m.get("life", 2.2), motion="boomerang"))


def p_spray(e, c, m):
    """Flamethrower / vomit: a short-lived stream swept across the cone shown during the wind-up."""
    d = pygame.Vector2(c.tele_dir) if c.tele_dir is not None else pygame.Vector2(c.aim)
    arc = m.get("arc", 40)
    steps = m.get("repeat", 8)
    frac = (c.step / max(1, steps - 1)) if steps > 1 else 0.5
    ang = -arc / 2 + arc * frac
    for k in range(m.get("per_step", 2)):
        jitter = random.uniform(-4, 4)
        c.out.append(_bullet(e, e.pos, d.rotate(ang + jitter), m.get("speed", 1.1) * random.uniform(0.85, 1.1),
                             m.get("dmgm", 0.6), m.get("color", (255, 140, 50)), -1, m.get("life", 0.8)))


def _zone(e, shape, pos, life, color, dmg_mult=0.0, r=60, length=0, width=0, ang=0.0, sfx="slam",
          burst=None, effect=None, shake=True, extra=None):
    dmg = 0
    if dmg_mult > 0:
        dmg = max(1, int(round(random.randint(*e.dmg) * dmg_mult)))
    z = dict(shape=shape, x=float(pos[0]), y=float(pos[1]), r=float(r), length=float(length),
             width=float(width), ang=float(ang), life=float(life), t=0.0, color=color,
             dmg=dmg, sfx=sfx, burst=burst, effect=effect, shake=shake and dmg > 0,
             src_rank=e.rank, src=e)
    if extra:
        z.update(extra)
    e._new_zones.append(z)
    return z


# each primitive's default bullet lifetime (so a telegraph can be drawn as long as the real shot flies)
_PRIM_LIFE = {"fan": 2.4, "ring": 2.4, "half_ring": 2.4, "wall": 3.0, "beam": 1.6, "sine": 3.0,
              "homing": 3.2, "accel": 2.6, "mines": 2.6, "split": 1.1, "boomerang": 2.2, "spray": 0.8}
SPOKE_MAX_LEN = 150.0  # spokes point the way (and show the gaps); they don't need to cross the screen


def reach(m):
    """How far a move's bullets really travel (px) - telegraph lanes are drawn this long."""
    fn = m["fn"]
    life = m.get("life", _PRIM_LIFE.get(fn, 2.4))
    if fn == "accel":
        return BASE_SPEED * m.get("max_speed", 1.6) * life * 0.6
    return BASE_SPEED * m.get("speed", _PRIM_SPEED.get(fn, 1.0)) * life


def spoke_angles(m, d):
    """Every direction (degrees) the bullets of move `m` will fly when it fires
    along base direction `d` - including every step of a sweep. The spokes
    telegraph draws exactly these, so the warning can never lie."""
    fn = m["fn"]
    base = pygame.Vector2(d).as_polar()[1]
    if fn == "ring":
        n = m.get("n", 12)
        skip = _ring_skip(m)
        return [base + 360 * i / n for i in range(n) if i not in skip]
    if fn == "half_ring":
        n = max(2, m.get("n", 7))
        arc = m.get("arc", 180)
        return [base - arc / 2 + arc * i / (n - 1) for i in range(n)]
    offs = [0.0]
    if fn in ("fan", "accel", "mines"):
        n = m.get("n", 1)
        spread = m.get("spread", 50 if fn == "mines" else 0)
        offs = [0.0 if n == 1 else -spread / 2 + spread * i / (n - 1) for i in range(n)]
    elif fn == "homing":
        n = m.get("n", 2)
        offs = [0.0 if n == 1 else -30 + 60 * i / (n - 1) for i in range(n)]
    elif fn == "boomerang":
        offs = [float(o) for o in m.get("offs", (-15, 15))]
    sweep = m.get("sweep_step", 0) if fn == "fan" else 0
    steps = range(m.get("repeat", 1)) if sweep else (0,)
    out = []
    for s in steps:
        for o in offs:
            a = base + sweep * s + o
            if not any(abs(((a - b) + 180) % 360 - 180) < 0.5 for b in out):
                out.append(a)
    return out


def _burst_move(burst):
    bm = dict(burst)
    bm["fn"] = "half_ring" if burst.get("kind") == "half" else "ring"
    return bm


# ------- telegraph builders: called at WIND-UP START, before the move fires --

def tele_for(e, m, target, lead, aim):
    """Pushes the move's telegraph zone(s) and returns (tele_dir, tele_point).
    Everything random or aimed about the move (direction, ring gaps, wall gap,
    slam-burst facing) is decided HERE and stored, and the move fires exactly
    that later - moving during the wind-up never re-aims a telegraphed attack."""
    tele = m.get("tele", "none")
    windup = m.get("windup", 0.3)
    fn = m.get("tele_fn", m["fn"])
    run = windup + max(0, m.get("repeat", 1) - 1) * m.get("gap", 0.15)  # wind-up + every repeat step

    def toward(p):
        d = pygame.Vector2(p) - e.pos
        return d.normalize() if d.length_squared() > 1 else pygame.Vector2(aim)

    br = e._bullet_radius() + m.get("size", 0)
    fast = getattr(e, "bullet_speed_mult", 1.0)  # lanes / spokes are drawn as far as the real shots fly
    if tele == "line":
        d = toward(lead if m.get("lead") else target)
        length = max(m.get("tele_len", 420), reach(m) * fast)
        if m["fn"] == "wall":
            n = m.get("n", 7)
            spacing = m.get("spacing", 26)
            gap = random.randint(1, n - 2)
            e._wall_gap = gap
            width = (n - 1) * spacing + 2 * br + 8
            gap_px = (2 * m.get("gap_w", 0) + 1) * spacing - 2 * br
            _zone(e, "line", e.pos, windup, RED, length=length, width=width, ang=d.as_polar()[1], sfx=None,
                  extra=dict(gap_off=(gap - (n - 1) / 2) * spacing, gap_w=max(8.0, gap_px)))
        else:
            _zone(e, "line", e.pos, run, RED, length=length, width=max(m.get("tele_w", 14), 2 * br + 4),
                  ang=d.as_polar()[1], sfx=None)
        return d, None
    if tele == "cone":
        d = toward(target)
        _zone(e, "cone", e.pos, run, ORANGE, r=max(m.get("tele_len", 170), reach(m) * 1.12 * fast),
              width=m.get("arc", 40) + 10, ang=d.as_polar()[1], sfx=None)
        return d, None
    if tele == "dash":
        d = toward(target)
        dist = e.speed * m.get("dash_mult", 3.2) * m.get("dash_time", 0.45)
        _zone(e, "line", e.pos, windup, RED, length=dist + e.radius, width=max(18, e.radius * 2),
              ang=d.as_polar()[1], sfx=None)
        return d, None
    if tele == "ring":
        mm = m.get("then") if m["fn"] == "shell" else m
        if m["fn"] == "summon" or mm is None or mm["fn"] not in _PRIM_LIFE:
            _zone(e, "circle", e.pos, windup, ORANGE, r=m.get("tele_r", 90), sfx=None)  # a summoning circle
            return None, None
        if mm["fn"] == "ring" and not mm.get("aim_gap"):
            d = pygame.Vector2(1, 0).rotate(random.uniform(0, 360))  # the ring's rotation = where its gaps are
        else:
            d = toward(lead if mm.get("lead") else target)
        life = run + (m.get("shell", 1.5) if m["fn"] == "shell" else 0.0)
        _zone(e, "spokes", e.pos, life, ORANGE, r=min(reach(mm), SPOKE_MAX_LEN), sfx=None,
              extra=dict(angles=spoke_angles(mm, d)))
        return d, None
    if tele == "zone":
        if fn in ("slam", "leap"):
            point = pygame.Vector2(e.pos) if fn == "slam" else pygame.Vector2(lead)
            life = windup if fn == "slam" else windup + m.get("dash_time", 0.35)
            burst = m.get("burst")
            extra = None
            if burst:
                # the burst's facing is fixed now and drawn as spokes from the impact point
                if burst.get("kind") == "half":
                    bd = pygame.Vector2(target) - point
                    bd = bd.normalize() if bd.length_squared() > 1 else pygame.Vector2(aim)
                else:
                    bd = pygame.Vector2(1, 0).rotate(random.uniform(0, 360))
                extra = dict(burst_ang=bd.as_polar()[1])
                bm = _burst_move(burst)
                _zone(e, "spokes", point, life, ORANGE, r=min(reach(bm), SPOKE_MAX_LEN), sfx=None,
                      extra=dict(angles=spoke_angles(bm, bd)))
            _zone(e, "circle", point, life, ORANGE, dmg_mult=m.get("dmgm", 1.3),
                  r=m.get("r", 110 if fn == "slam" else 70), sfx=m.get("sfx", "slam"), burst=burst, extra=extra)
            if fn == "slam":
                return None, point
            return toward(point), point
        if fn == "lob":
            point = pygame.Vector2(lead if m.get("lead", True) else target)
            _zone(e, "circle", point, windup, ORANGE, dmg_mult=m.get("dmgm", 1.2), r=m.get("r", 60),
                  sfx=m.get("sfx", "lob"), burst=m.get("burst"))
            return None, point
        if fn == "rain":
            for i in range(m.get("n", 5)):
                off = (pygame.Vector2(random.uniform(-1, 1), random.uniform(-1, 1)) * m.get("spread", 150))
                if i == 0:
                    off = pygame.Vector2(0, 0)  # one always right on you - keep moving
                life = windup + i * m.get("stagger", 0.12)
                _zone(e, "circle", target + off, life, ORANGE, dmg_mult=m.get("dmgm", 1.0), r=m.get("r", 45),
                      sfx=m.get("sfx", "lob"))
            return None, pygame.Vector2(target)
        if fn == "eruption":
            for k in range(m.get("rings", 3)):
                n = 6 + 3 * k
                for i in range(n):
                    ang = 360 * i / n + k * 17
                    p = e.pos + pygame.Vector2(1, 0).rotate(ang) * (80 + 70 * k)
                    _zone(e, "circle", p, windup + 0.35 * k, ORANGE, dmg_mult=m.get("dmgm", 1.0), r=36,
                          sfx=m.get("sfx", "slam") if i == 0 else None)
            return None, pygame.Vector2(e.pos)
        if fn == "root_pulse":
            # the drawn circle IS the root radius (RealmSim roots everyone inside m["r"] of the mob)
            _zone(e, "circle", e.pos, windup, (120, 220, 90), r=m.get("r", 170), sfx=m.get("sfx", "root"),
                  effect="root", shake=False)
            return None, pygame.Vector2(e.pos)
    return None, None


# --- zone-only moves: the telegraph zone IS the attack, nothing fires later --
def p_none(e, c, m):
    pass


def p_dash(e, c, m):
    d = pygame.Vector2(c.tele_dir) if c.tele_dir is not None else pygame.Vector2(c.aim)
    e._dash = dict(dir=d, t=m.get("dash_time", 0.45), mult=m.get("dash_mult", 3.2), end=m.get("end"))


def p_leap(e, c, m):
    if c.tele_point is None:
        return
    d = c.tele_point - e.pos
    t = m.get("dash_time", 0.35)
    mult = (d.length() / t) / max(1.0, e.speed)
    e._dash = dict(dir=(d.normalize() if d.length_squared() > 1 else pygame.Vector2(c.aim)), t=t, mult=mult,
                   end=None, stop_at=pygame.Vector2(c.tele_point))


def p_summon(e, c, m):
    e._summon_pending = (m.get("kind", "imp"), m.get("n", 2))


def p_shell(e, c, m):
    """Invulnerable for a moment (shell / fade / burrow feint), then an attack."""
    e._shell_t = m.get("shell", 1.5)
    e._shell_then = m.get("then")
    e._shell_dir = c.tele_dir  # the follow-up fires where the wind-up's spokes pointed


def p_root(e, c, m):
    e._root_pulse = float(m.get("r", 170))  # the radius the wind-up circle showed


PRIMITIVES = {
    "fan": p_fan, "ring": p_ring, "half_ring": p_half_ring, "wall": p_wall, "beam": p_beam,
    "sine": p_sine, "homing": p_homing, "accel": p_accel, "mines": p_mines, "split": p_split,
    "boomerang": p_boomerang, "spray": p_spray, "dash": p_dash, "leap": p_leap, "summon": p_summon,
    "shell": p_shell, "root_pulse": p_root,
    # zone-only (the ground telegraph does the damage when it resolves)
    "lob": p_none, "slam": p_none, "rain": p_none, "eruption": p_none,
}


def execute(e, m, c):
    PRIMITIVES[m["fn"]](e, c, m)


# ----------------------------------------------------------- the tables --
def M(name, fn, windup=0.25, cd=2.0, tele=None, sfx=None, **kw):
    if tele is None:
        # ordinary shots (aimed / fans / volleys / sine / homers) get NO visual hint -
        # only dangerous moves carry a telegraph (see TELEGRAPHED / is_dangerous)
        tele = "none"
        windup = min(windup, 0.12)
    d = dict(name=name, fn=fn, windup=windup, cd=cd, tele=tele, sfx=sfx or _DEFAULT_SFX.get(fn, "shot"))
    d.update(kw)
    return d


_DEFAULT_SFX = {
    "fan": "shot", "ring": "burst", "half_ring": "slam", "wall": "wall", "beam": "beam", "sine": "wave",
    "homing": "homing", "accel": "fire", "mines": "lob", "split": "shot", "boomerang": "throw",
    "spray": "spray", "dash": "dash", "leap": "leap", "summon": "summon", "shell": "shell",
    "lob": "lob", "slam": "slam", "rain": "lob", "eruption": "slam", "root_pulse": "root",
}

# gapped ring used by leaps / slams landing (always telegraphed by the zone first)
_LAND_RING = dict(n=10, gaps=2, gap_w=2, speed=0.75)

ATTACKS = {
    # ---------------- trash: simple, readable basics - no specials, no telegraphs ----------------
    # (the common fodder; named specials/telegraphs are reserved for elites, mini-bosses and bosses)
    "imp": [M("Ember Flick", "fan", lead=True, speed=1.15, cd=1.3, sfx="shot_small")],
    "goblin": [M("Rock Throw", "fan", cd=1.3, sfx="shot_small")],
    "bat": [M("Screech Dart", "fan", cd=1.6, speed=1.1, sfx="shot_small")],
    "ember_wisp": [M("Ember Pair", "fan", cd=1.8, repeat=2, gap=0.14, speed=1.0, sfx="shot_small")],
    "fury_shard": [M("Shard Triplet", "fan", n=3, spread=16, cd=1.9, speed=1.05, sfx="shot_small")],
    "rubble_crawler": [M("Heavy Pebble", "fan", cd=1.9, speed=0.7, dmgm=1.4, size=3, sfx="shot_small")],
    "spite_spirit": [M("Spite Wave", "sine", cd=1.9, amp=18, sfx="shot_small")],
    "tide_wisp": [M("Drift Shot", "sine", cd=1.8, amp=22, freq=6.0, sfx="shot_small")],
    "pearl_acolyte": [M("Pearl Pair", "fan", cd=1.9, repeat=2, gap=0.16, lead=True, color=(240, 240, 255),
                        sfx="shot_small")],
    "brine_crawler": [M("Brine Boomerang", "boomerang", cd=2.4, offs=(0,), sfx="shot_small")],
    "abyssal_chorister": [M("Hum Fan", "fan", n=3, spread=20, cd=1.9, speed=0.85, sfx="shot_small")],
    # ---------------- outer biomes ----------------
    "thornling": [M("Seed Pods", "mines", windup=0.4, cd=3.0, n=3, spread=60, pop=4),
                  M("Thorn", "fan", cd=1.6)],
    "scorpion": [M("Pincer Spray", "fan", n=5, spread=30, speed=1.0, life=1.2, cd=2.0, sfx="shotgun"),
                 M("Stinger", "fan", windup=0.5, cd=5.0, tele="line", n=1, speed=1.45, dmgm=1.4, size=2,
                   use_tele=True, bkw=dict(status_effect="slow"))],
    "dune_stalker": [M("Sand Burrow", "shell", windup=0.3, cd=6.0, tele="ring", tele_r=70, shell=1.2,
                       then=dict(fn="fan", n=5, spread=40, speed=1.0)),
                     M("Dune Lunge", "dash", windup=0.45, cd=4.0, tele="dash", dash_time=0.45, dash_mult=3.0,
                       end=dict(fn="fan", n=3, spread=30))],
    "yeti": [M("Snowball", "fan", speed=0.7, dmgm=1.3, size=3, cd=1.6),
             M("Avalanche Slam", "slam", windup=0.7, cd=7.0, tele="zone", r=100, dmgm=1.2,
               burst=dict(kind="half", n=7))],
    "frost_sprite": [M("Icicle Weave", "sine", cd=0.5, repeat=3, gap=0.15, amp=26),
                     M("Frost Blink", "shell", windup=0.3, cd=6.0, shell=0.6, then=dict(fn="fan", n=3, spread=24))],
    "ghost": [M("Wisp Pair", "homing", windup=0.35, cd=3.4, n=2, speed=0.5),
              M("Fade", "shell", windup=0.3, cd=7.0, shell=1.5, then=dict(fn="fan", n=3, spread=30))],
    "troll": [M("Club Bolt", "fan", speed=0.7, dmgm=1.5, size=3, cd=1.8),
              M("Boulder Lob", "lob", windup=1.0, cd=8.0, tele="zone", r=70, dmgm=1.4)],
    "bog_crawler": [M("Poison Glob", "lob", windup=0.8, cd=4.5, tele="zone", r=62, dmgm=1.0, sfx="bubble"),
                    M("Bog Spiral", "fan", cd=3.0, repeat=6, gap=0.18, n=2, spread=180, sweep_step=30,
                      speed=0.75)],
    "skeleton": [M("Bone Boomerangs", "boomerang", cd=2.4),
                 M("Rattle Burst", "fan", windup=0.3, cd=4.0, repeat=3, gap=0.12, speed=1.1)],
    # ---------------- inner biomes ----------------
    "harpy": [M("Feather Strafe", "fan", cd=0.9, repeat=4, gap=0.12, n=2, spread=90, speed=0.9),
              M("Talon Dive", "dash", windup=0.45, cd=5.0, tele="dash", dash_time=0.4, dash_mult=3.2)],
    "cliff_strider": [M("Cliff Leap", "leap", windup=0.6, cd=5.0, tele="zone", r=70, dmgm=1.2, dash_time=0.35,
                        burst=dict(kind="ring", **_LAND_RING)),
                      M("Rock Chip", "fan", n=2, spread=14, cd=1.8)],
    "salamander": [M("Flamethrower", "spray", windup=0.4, cd=4.0, tele="cone", arc=40, repeat=10, gap=0.08,
                     tele_len=190),
                   M("Spit", "fan", cd=1.6, speed=1.0)],
    "cinder_wisp": [M("Kindling", "accel", cd=1.6, n=1),
                    M("Flare Fan", "accel", windup=0.35, cd=4.5, n=3, spread=30)],
    "panther": [M("Claw Flick", "fan", n=2, spread=14, cd=1.6, lead=True), M("Pounce", "dash", windup=0.4, cd=3.5, tele="dash", dash_time=0.35, dash_mult=3.4,
                  end=dict(fn="fan", n=3, spread=70, speed=0.9, life=0.5))],
    "vine_serpent": [M("Serpent Stream", "sine", cd=2.2, repeat=5, gap=0.12, amp=30, phase_step=False),
                     M("Vine Snare", "fan", windup=0.4, cd=5.0, tele="line", speed=1.2, use_tele=True,
                       bkw=dict(status_effect="slow"))],
    "ghoul": [M("Rot Orbs", "homing", windup=0.35, cd=3.6, n=2, speed=0.45, turn=1.3),
              M("Vomit", "spray", windup=0.5, cd=5.5, tele="cone", arc=60, repeat=6, gap=0.08, per_step=2,
                speed=0.8, color=(150, 200, 60))],
    "husk_wanderer": [M("Husk Wall", "wall", windup=1.0, cd=4.5, tele="line", n=7, speed=0.6, tele_len=280,
                        tele_w=180),
                      M("Shamble Charge", "dash", windup=0.6, cd=6.0, tele="dash", dash_time=0.5, dash_mult=2.6)],
    "frost_wraith": [M("Frost Sweep", "fan", windup=0.3, cd=3.2, repeat=7, gap=0.07, sweep_step=13,
                       speed=0.95, color=(150, 220, 255)),
                     M("Chill", "fan", n=2, spread=10, cd=1.8)],
    "glacier_shard": [M("Ice Lance", "beam", windup=0.6, cd=3.2, tele="line", n=6),
                      M("Shard Split", "split", cd=2.5)],
    "cave_lurker": [M("Ambush", "fan", windup=0.2, cd=2.4, n=5, spread=34, life=0.9, speed=1.1, sfx="shotgun"),
                    M("Lurker Lunge", "dash", windup=0.35, cd=5.0, tele="dash", dash_time=0.3, dash_mult=3.2)],
    "deep_stalker": [M("Quick Shot", "fan", cd=1.5, speed=1.2), M("Sniper Shot", "fan", windup=0.8, cd=3.0, tele="line", lead=True, use_tele=True,
                       speed=1.7, size=1, sfx="beam")],
    # ---------------- Reforging island elites ----------------
    "shard_sentinel": [M("Shard Burst", "fan", n=3, spread=20, cd=1.7, repeat=2, gap=0.2), M("Cross Beam", "fan", windup=0.45, cd=3.0, tele="ring", tele_r=60, n=4, spread=270,
                         repeat=5, gap=0.15, sweep_step=9, speed=0.85)],
    "echo_knight": [M("Echo Lance", "beam", windup=0.6, cd=4.5, tele="line", n=5, lead=True), M("Echo Strike", "fan", cd=1.6, repeat=2, gap=0.5, speed=1.1)],
    "shattered_golem": [M("Golem Slam", "slam", windup=0.8, cd=6.0, tele="zone", r=105, dmgm=1.2,
                          burst=dict(kind="half", n=7)),
                        M("Splitting Stone", "split", cd=2.4)],
    "fracture_hound": [M("Fracture Bite", "fan", n=3, spread=26, cd=1.6, life=0.8), M("Zigzag Charge", "dash", windup=0.4, cd=3.0, tele="dash", dash_time=0.35,
                         dash_mult=3.2, end=dict(fn="fan", n=3, spread=36))],
    "stone_revenant": [M("Orbit Shards", "accel", windup=0.5, cd=4.0, tele="ring", tele_r=55, n=4, spread=60,
                         speed=0.2, accel=380),
                       M("Grave Chip", "fan", cd=1.6)],
    "cinder_warden": [M("Warden Flame", "spray", windup=0.4, cd=4.0, tele="cone", arc=50, repeat=10, gap=0.08),
                      M("Cinder Grenade", "lob", windup=0.9, cd=5.0, tele="zone", r=62, dmgm=1.3),
                      M("Call the Embers", "summon", windup=0.6, cd=14.0, tele="ring", tele_r=70,
                        kind="ember_wisp", n=2)],
    "coral_sentinel": [M("Coral Buckshot", "fan", n=5, spread=26, cd=2.2, sfx="shotgun"),
                       M("Reef Spiral", "fan", cd=4.0, repeat=6, gap=0.16, n=2, spread=180, sweep_step=28,
                         speed=0.7)],
    "drowned_custodian": [M("Undertow Slam", "slam", windup=0.8, cd=6.0, tele="zone", r=100, dmgm=1.2, burst=dict(kind="half", n=7)), M("Anchor Toss", "boomerang", cd=2.6, offs=(0,), dmgm=1.4)],
    "kelp_stalker": [M("Kelp Stream", "sine", cd=2.2, repeat=4, gap=0.13),
                     M("Snare Bolt", "fan", windup=0.4, cd=5.0, tele="line", use_tele=True, speed=1.2,
                       bkw=dict(status_effect="root"))],
    "shellback_guardian": [M("Shell Up", "shell", windup=0.4, cd=7.0, tele="ring", tele_r=80, shell=2.0,
                             then=dict(fn="ring", n=12, gaps=2, gap_w=2, speed=0.7)),
                           M("Shell Shot", "fan", cd=1.7, speed=0.9, dmgm=1.2)],
    "siren_wraith": [M("Lure", "homing", cd=3.6, n=2, speed=0.55, turn=1.5), M("Siren Waves", "sine", cd=1.9, repeat=3, gap=0.2, amp=40, freq=4.0)],
    "choir_warden": [M("Choir Charge", "dash", windup=0.5, cd=4.5, tele="dash", dash_time=0.45, dash_mult=3.0),
                     M("Wave Arc", "half_ring", windup=0.45, cd=4.0, tele="ring", tele_r=70, n=7, arc=120),
                     M("Call the Tide", "summon", windup=0.6, cd=14.0, tele="ring", tele_r=70, kind="tide_wisp",
                       n=2)],
}

# ---------------- island mini-bosses: 3 named moves, 1 unlocked by the phase break ----------------
ATTACKS.update({
    "cinder_colossus": [M("Magma Slam", "slam", windup=0.8, cd=5.0, tele="zone", r=120, dmgm=1.2,
                          burst=dict(kind="ring", n=12, gaps=2, gap_w=2, speed=0.7)),
                        M("Flame Sweep", "spray", windup=0.5, cd=4.0, tele="cone", arc=70, repeat=12, gap=0.07),
                        M("Ember Rain", "rain", windup=0.9, cd=7.0, tele="zone", n=6, r=48, phase=2),
                        M("Cinder Fist", "fan", n=3, spread=20, cd=1.6, lead=True, repeat=2, gap=0.22)],
    "rubble_warlord": [M("Triple Charge", "dash", windup=0.5, cd=5.0, tele="dash", dash_time=0.4, dash_mult=3.0,
                         end=dict(fn="fan", n=5, spread=50)),
                       M("Boulder Toss", "lob", windup=0.9, cd=4.0, tele="zone", r=72, dmgm=1.3),
                       M("Rally", "summon", windup=0.8, cd=15.0, tele="ring", tele_r=90, kind="rubble_crawler",
                         n=3, phase=2)],
    "ashreach_revenant": [M("Soul Spiral", "fan", cd=4.0, repeat=10, gap=0.12, n=2, spread=180, sweep_step=20,
                            speed=0.7, color=(170, 120, 255)),
                          M("Grave Hands", "rain", windup=0.8, cd=5.5, tele="zone", n=3, r=50, spread=90),
                          M("Ash Orbit", "accel", windup=0.6, cd=6.0, tele="ring", tele_r=70, n=6, spread=300,
                            speed=0.15, accel=300, phase=2)],
    "thornrock_colossus": [M("Quake", "eruption", windup=0.9, cd=7.0, tele="zone", rings=2),
                           M("Thorn Wall", "wall", windup=0.8, cd=4.0, tele="line", n=9, speed=0.65, tele_len=300,
                             tele_w=230),
                           M("Root Burst", "root_pulse", windup=1.0, cd=9.0, tele="zone", r=160, phase=2),
                           M("Pebble Fan", "fan", n=3, spread=24, cd=1.8)],
    "ashenreach_devourer": [M("Lunge Chain", "dash", windup=0.45, cd=4.0, tele="dash", dash_time=0.35,
                              dash_mult=3.4, repeat=2, gap=0.5),
                            M("Maw Cone", "spray", windup=0.55, cd=4.5, tele="cone", arc=60, repeat=8, gap=0.08,
                              color=(200, 90, 200)),
                            M("Split Spit", "split", windup=0.3, cd=3.0, repeat=2, gap=0.3, phase=2)],
    "choir_sovereign": [M("Choir Wall", "wall", windup=0.8, cd=4.0, tele="line", n=9, speed=0.6, tele_len=300,
                          tele_w=230),
                        M("Echo Volley", "fan", cd=2.0, repeat=2, gap=0.45, n=3, spread=22),
                        M("Crescendo", "ring", windup=1.1, cd=8.0, tele="ring", tele_r=150, n=18, gaps=3,
                          gap_w=2, speed=0.7, phase=2)],
    "coral_leviathan": [M("Tidal Beam", "beam", windup=0.8, cd=4.0, tele="line", n=8),
                        M("Bubble Mines", "mines", windup=0.5, cd=4.5, n=4, spread=90, pop=4),
                        M("Surge Charge", "dash", windup=0.6, cd=6.0, tele="dash", dash_time=0.45, dash_mult=3.0,
                          phase=2)],
    "tideglass_warden": [M("Mirror Lances", "beam", windup=0.7, cd=3.5, tele="line", n=6, lead=True),
                         M("Glass Orbit", "accel", windup=0.6, cd=5.0, tele="ring", tele_r=70, n=5, spread=280,
                           speed=0.15, accel=320),
                         M("Shatter Nova", "ring", windup=1.0, cd=8.0, tele="ring", tele_r=140, n=16, gaps=2,
                           gap_w=2, speed=0.8, phase=2)],
    "driftbell_matriarch": [M("Bell Toll", "ring", windup=1.0, cd=6.0, tele="ring", tele_r=130, n=14, gaps=2,
                              gap_w=2, speed=0.65),
                            M("Call the Tide", "summon", windup=0.7, cd=14.0, tele="ring", tele_r=80,
                              kind="tide_wisp", n=3),
                            M("Drift Homers", "homing", windup=0.4, cd=4.5, n=3, speed=0.5, phase=2),
                            M("Bell Chime", "fan", n=2, spread=16, cd=1.8)],
    "abyssal_choirmaster": [M("Dirge Wall", "wall", windup=0.8, cd=4.0, tele="line", n=9, speed=0.6,
                              tele_len=300, tele_w=230),
                            M("Abyss Pull", "homing", windup=0.5, cd=4.5, n=3, speed=0.55, turn=1.8),
                            M("Silence", "rain", windup=0.9, cd=7.0, tele="zone", n=4, r=55, spread=120, phase=2),
                            M("Low Note", "fan", n=3, spread=20, cd=1.8)],
})

# ---------------- dungeon bosses: 4 named moves (3rd after the phase break, 4th in the phase-2 room) --------
ATTACKS.update({
    "boss": [M("Aimed Shotgun", "fan", windup=0.3, cd=2.2, repeat=3, gap=0.2, n=5, spread=34, sfx="shotgun"),
             M("Grenade Barrage", "rain", windup=0.9, cd=5.0, tele="zone", n=3, r=55, spread=110),
             M("Gapped Spin", "fan", windup=0.5, cd=6.0, tele="ring", tele_r=100, repeat=12, gap=0.12, n=4,
               spread=270, sweep_step=11, speed=0.8, phase=2),
             M("Crystal Rage", "ring", windup=1.1, cd=9.0, tele="ring", tele_r=160, n=20, gaps=3, gap_w=2,
               speed=0.85, p2=True)],
    "frost_monarch": [M("Ice Lances", "beam", windup=0.65, cd=3.4, tele="line", n=5, lead=True),
                      M("Blizzard", "fan", windup=0.35, cd=4.5, repeat=10, gap=0.07, sweep_step=10, n=2,
                        spread=24, speed=0.9, color=(170, 220, 255)),
                      M("Hailstones", "fan", n=3, spread=18, cd=2.0, color=(200, 235, 255)),
                      M("Frozen Floor", "rain", windup=0.9, cd=6.0, tele="zone", n=5, r=50, phase=2),
                      M("Glacial Nova", "ring", windup=1.2, cd=9.0, tele="ring", tele_r=170, n=22, gaps=3,
                        gap_w=2, speed=0.8, p2=True)],
    "ash_behemoth": [M("Behemoth Flame", "spray", windup=0.5, cd=3.5, tele="cone", arc=60, repeat=12, gap=0.07),
                     M("Magma Meteors", "rain", windup=0.9, cd=5.0, tele="zone", n=5, r=52),
                     M("Molten Charge", "dash", windup=0.6, cd=6.0, tele="dash", dash_time=0.45, dash_mult=3.0,
                       end=dict(fn="half_ring", n=7), phase=2),
                     M("Eruption", "eruption", windup=1.0, cd=9.0, tele="zone", rings=3, p2=True)],
    "void_reaper": [M("Scythe Boomerangs", "boomerang", cd=2.4, offs=(-20, 0, 20), dmgm=1.1),
                    M("Blink Slash", "dash", windup=0.45, cd=4.5, tele="dash", dash_time=0.3, dash_mult=4.0,
                      end=dict(fn="fan", n=5, spread=90, speed=1.0, life=0.6)),
                    M("Summon Shades", "summon", windup=0.8, cd=14.0, tele="ring", tele_r=100, kind="ghost", n=2,
                      phase=2),
                    M("Void Spiral", "fan", windup=0.6, cd=8.0, tele="ring", tele_r=120, repeat=14, gap=0.1, n=4,
                      spread=270, sweep_step=13, speed=0.75, color=(170, 90, 255), p2=True)],
    "thorn_warden": [M("Root Pulse", "root_pulse", windup=1.0, cd=7.0, tele="zone", r=170),
                     M("Thorn Walls", "wall", windup=0.8, cd=3.0, tele="line", n=9, speed=0.7, tele_len=300,
                       tele_w=230, dmgm=1.2),
                     M("Seed Mines", "mines", windup=0.5, cd=5.0, n=5, spread=120, pop=4, phase=2),
                     M("Vine Lash", "fan", windup=0.4, cd=6.0, repeat=10, gap=0.07, sweep_step=12, n=3, spread=20,
                       speed=0.95, color=(120, 220, 90), p2=True),
                     M("Thorn Shot", "fan", n=3, spread=18, cd=1.2, lead=True)],
    "sand_wyrm": [M("Sand Spit", "fan", windup=0.25, cd=2.0, n=5, spread=36, sfx="shotgun"),
                  M("Tail Sweep", "fan", windup=0.35, cd=4.5, repeat=8, gap=0.07, sweep_step=14, speed=1.0,
                    color=(230, 190, 90)),
                  M("Sandstorm", "sine", windup=0.5, cd=6.0, tele="ring", tele_r=90, repeat=8, gap=0.1, amp=36,
                    phase=2),
                  M("Dune Collapse", "rain", windup=0.9, cd=8.0, tele="zone", n=6, r=50, p2=True)],
    # the finale: Oryx-style - keeps its armor-piercing volley (tests/check_story check_mad_god_threat)
    "mad_god": [M("Star Shotgun", "fan", windup=0.25, cd=0.9, repeat=3, gap=0.18, n=3, spread=28, speed=1.25,
                  bkw=dict(status_effect="armor_pierce"), sfx="shotgun"),
                M("Minion Grenades", "rain", windup=0.9, cd=4.5, tele="zone", n=4, r=58, spread=140, dmgm=1.5),
                M("Blade Burst", "half_ring", windup=0.45, cd=3.5, tele="ring", tele_r=90, n=9, arc=200,
                  speed=1.0, dmgm=1.2),
                M("Gathering Power", "ring", windup=1.3, cd=7.0, tele="ring", tele_r=190, n=24, gaps=3, gap_w=2,
                  speed=0.85, dmgm=1.4, phase=2),
                M("Madness Spiral", "fan", windup=0.5, cd=6.0, tele="ring", tele_r=120, repeat=12, gap=0.1, n=5,
                  spread=288, sweep_step=12, speed=0.8, p2=True, bkw=dict(status_effect="armor_pierce"))],
})


# telegraph styles that mark a DANGEROUS move (ground AoE, slam/nova, beam/lance line, dash/leap, big
# boss specials). "none" = an ordinary shot with no visual hint at all.
TELEGRAPHED = ("zone", "ring", "cone", "line", "dash", "glow")


def is_dangerous(move):
    return move.get("tele", "none") in TELEGRAPHED


# ------------------------------------------------ special-mob hardening --
# Elites, mini-bosses and bosses are the "special" mobs: their moves are sped up,
# densified (more bullets -> narrower, but never removed, gaps) and come back
# sooner; bosses/mini-bosses also get a Crossfire combo (a predictive burst while
# ground AoEs land around you). Trash keeps its plain basics untouched.
HARDEN = {
    "elite": dict(speed=1.18, cd=0.75, fan_n=1, ring_mult=1.2, wall_n=2, repeat=0),
    "boss": dict(speed=1.2, cd=0.72, fan_n=1, ring_mult=1.3, wall_n=2, repeat=0),
}
FAST_CD = 1.5  # moves already on a short cycle (primaries) only get 10% faster, not the full factor
_NO_SPEEDUP = ("dash", "leap", "summon", "shell", "root_pulse", "lob", "slam", "rain", "eruption")
# each primitive's own default bullet speed (so hardening scales the REAL speed)
_PRIM_SPEED = {"fan": 1.0, "ring": 0.8, "half_ring": 0.85, "wall": 0.7, "beam": 1.7, "sine": 0.8,
               "homing": 0.5, "accel": 0.4, "mines": 1.0, "split": 0.8, "boomerang": 1.0, "spray": 1.1}


def _harden_move(m, h):
    m = dict(m)
    m["cd"] = round(m["cd"] * (0.9 if m["cd"] < FAST_CD else h["cd"]), 2)
    if m["fn"] not in _NO_SPEEDUP:
        m["speed"] = round(m.get("speed", _PRIM_SPEED.get(m["fn"], 1.0)) * h["speed"], 3)
    if m["fn"] == "fan" and m.get("n", 1) >= 3:
        m["n"] = m["n"] + h["fan_n"]
    elif m["fn"] == "fan" and m.get("n", 1) == 1 and m.get("repeat", 1) == 1 and not is_dangerous(m):
        m["n"], m["spread"] = 2, 9  # a special mob's plain shot becomes a tight double
    if m["fn"] in ("ring", "half_ring"):
        m["n"] = int(round(m.get("n", 10) * h["ring_mult"]))
        if m["fn"] == "ring":
            m["gaps"] = max(2, m.get("gaps", 2))  # the safe gaps always stay
    if m["fn"] == "wall":
        m["n"] = m.get("n", 7) + h["wall_n"]
    if m.get("repeat", 1) > 1 and h["repeat"]:
        m["repeat"] = m["repeat"] + h["repeat"]
    if is_dangerous(m):
        m["windup"] = round(max(0.35, m.get("windup", 0.3) * 0.9), 2)  # still readable
    return m


def _crossfire():
    # every hit comes from the warned circles (it used to also fire predictive volleys that
    # ignored its own warning - "leave the circle" while the real shots flew past it)
    return M("Crossfire", "rain", windup=0.7, cd=6.5, tele="zone", n=6, spread=130, r=52, stagger=0.16,
             dmgm=1.1, sfx="lob", phase=2)


_HARDENED = {}


def moves_for(kind):
    """The move list for an enemy kind (phase-2 room kinds reuse the base kind's
    moves, with their p2-only move enabled), or None for kinds with no set
    (neutral wildlife / the totem). Elite / boss sets come back hardened."""
    base = kind[:-7] if kind.endswith("_phase2") else kind
    if base in _HARDENED:
        return _HARDENED[base]
    moves = ATTACKS.get(base)
    if moves is None:
        return None
    rank = _E().ENEMY_KINDS.get(base, {}).get("rank", "trash")
    h = HARDEN.get(rank)
    if h is not None:
        moves = [_harden_move(m, h) for m in moves]
        if rank == "boss" and not any(m["name"] == "Crossfire" for m in moves):
            moves.append(_crossfire())
    _HARDENED[base] = moves
    return moves


def is_phase2_room(kind):
    return kind.endswith("_phase2")


def full_ring_untelegraphed(move):
    """True for a move that would spray a full, gap-free ring with no telegraph -
    the samey look this rework removes (tests assert no non-boss move does it)."""
    if move["fn"] == "ring":
        return move.get("gaps", 2) <= 0 or move.get("tele", "glow") == "glow"
    if move["fn"] == "fan" and move.get("spread", 0) >= 300 and move.get("n", 1) >= 8:
        return move.get("tele", "glow") == "glow"
    return False


# ------------------------------------------- special vs everyday mobs --
# The named, hardened move sets above only belong to SPECIAL mobs: bosses (incl. phase 2,
# world boss, Mad God), island mini-bosses, the island anchors, landmark story guardians and
# every elite fought inside a dungeon room (RealmSim marks those via Enemy.set_special).
# Everyday mobs roaming the open Realm and the islands - of ANY rank - only use plain,
# un-telegraphed basic shots (still varied per kind so biomes feel different).
SPECIAL_BY_KIND = ("cinder_warden", "choir_warden")
BASIC_FNS = ("fan", "sine", "boomerang")

# fallback basic shot from the kind's old `pattern` when its move list has no plain shot
_BASIC_FROM_PATTERN = {
    "aimed": dict(fn="fan", n=1),
    "erratic": dict(fn="fan", n=1, cd=2.0),
    "spread": dict(fn="fan", n=3, spread=20),
    "burst": dict(fn="fan", n=3, spread=30),          # was an 8-bullet ring
    "spiral": dict(fn="sine", amp=18),
    "volley": dict(fn="fan", n=1, repeat=2, gap=0.14),
    "charge": dict(fn="fan", n=1, lead=True),
    "boss": dict(fn="fan", n=3, spread=24),
    "boss_root": dict(fn="fan", n=3, spread=24),
    "boss_burrow": dict(fn="fan", n=3, spread=24),
    "mad_god": dict(fn="fan", n=3, spread=24),
}
_BASIC = {}


def special_by_default(kind):
    base = kind[:-7] if kind.endswith("_phase2") else kind
    return base in SPECIAL_BY_KIND or _E().ENEMY_KINDS.get(base, {}).get("rank") == "boss"


def _basicize(m, elite):
    b = dict(m)
    b["tele"], b["windup"] = "none", min(b.get("windup", 0.1), 0.12)
    b["sfx"] = "shot_small"
    for k in ("phase", "p2", "root"):
        b.pop(k, None)
    if b["fn"] == "fan":  # a plain aimed shot / small fan / short volley - never a spray
        b["n"] = min(b.get("n", 1), 3)
        b["spread"] = min(b.get("spread", 20), 30)
        b["repeat"] = min(b.get("repeat", 1), 2)
        b.pop("sweep_step", None)
    if elite:  # elites shoot a little harder than trash, but nothing special
        b["speed"] = round(b.get("speed", _PRIM_SPEED.get(b["fn"], 1.0)) * 1.08, 3)
        b["cd"] = round(b["cd"] * 0.9, 2)
    return b


def basic_moves_for(kind):
    """Plain everyday attacks for a kind (<= 2 moves, no telegraphs, no AoE/dash/ring)."""
    base = kind[:-7] if kind.endswith("_phase2") else kind
    if base in _BASIC:
        return _BASIC[base]
    moves = ATTACKS.get(base)
    if moves is None:
        return None
    d = _E().ENEMY_KINDS.get(base, {})
    elite = d.get("rank") != "trash"
    plain = [m for m in moves if m["fn"] in BASIC_FNS and not is_dangerous(m) and not m.get("p2")
             and m.get("phase", 1) == 1 and not (m["fn"] == "fan" and m.get("spread", 0) > 60)]
    if not plain:
        spec = dict(_BASIC_FROM_PATTERN.get(d.get("pattern"), dict(fn="fan", n=1)))
        fn = spec.pop("fn")
        plain = [M(f"{_pretty_kind(base)} Shot", fn, cd=spec.pop("cd", 1.6), **spec)]
    out = [_basicize(m, elite) for m in plain[:2]]
    _BASIC[base] = out
    return out


def _pretty_kind(kind):
    return kind.replace("_", " ").title()


def moves_for_enemy(kind, special):
    return moves_for(kind) if special else basic_moves_for(kind)

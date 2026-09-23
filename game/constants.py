"""
Shared constants and the RotMG-inspired stat formulas.

Stat formulas below are the real Realm of the Mad God (Exalt) formulas,
reproduced from public wiki documentation:
  DMG   = random(min,max) * (ATT + 25) / 50
  DEF   reduces incoming damage 1:1, floor is 10% of the roll getting through
  SPD   tiles/sec = 5.6 * (SPD + 53.5) / 75
  DEX   attacks/sec = 6.5 * (DEX + 17.3) / 75
  VIT   HP regen/sec = 0.2407 * (VIT + 8.3)
  WIS   MP regen/sec = 0.12 * (WIS + 4.2)
"""

TITLE = "Realm Reforged - v0 (RotMG-inspired prototype)"
SCREEN_W, SCREEN_H = 1366, 820  # bigger window per user request - "1300x800 or a lil bit higher"
TILE = 32
FPS = 60
NET_TICK_HZ = 30
NET_PORT = 50777

# ---------------------------------------------------------------- palette --
COL_BG = (18, 18, 22)
COL_GRASS = (46, 92, 46)
COL_GRASS_DARK = (38, 78, 38)
COL_DIRT = (94, 74, 52)
COL_ROCK = (90, 90, 96)
COL_WATER = (36, 72, 120)
COL_SAND = (196, 170, 100)
COL_SWAMP = (58, 74, 44)
COL_SNOW = (214, 224, 230)
COL_STONE = (120, 118, 128)
COL_ASH = (74, 40, 34)
COL_JUNGLE = (28, 84, 40)
COL_WASTELAND = (96, 88, 66)
COL_ICE = (150, 200, 224)
COL_CAVE = (54, 46, 68)
COL_NEXUS_FLOOR = (70, 62, 96)
COL_WHITE = (235, 235, 235)
COL_BLACK = (10, 10, 10)
COL_HP = (200, 40, 40)
COL_HP_BG = (60, 15, 15)
COL_MP = (40, 90, 210)
COL_MP_BG = (15, 25, 60)
COL_XP = (230, 190, 40)

# item tier -> badge colour (mirrors RotMG's tier badge colour bands)
TIER_COLORS = {
    "t_low": (222, 222, 222),      # tiers 1-3 (brown-bag common)
    "t_mid": (86, 156, 255),       # tiers 4-6
    "t_high": (176, 84, 232),      # tiers 7-9 (purple bag / soulbound)
    "t_top": (255, 150, 40),       # tiers 10+
    "ut": (255, 210, 60),          # untiered - rarest, white-bag drop
}
BAG_COLORS = {
    "brown": (120, 84, 48),
    "purple": (130, 60, 160),
    "white": (235, 235, 235),
}

# --------------------------------------------------------------- formulas --
def damage_roll(min_dmg: int, max_dmg: int, att: int) -> int:
    import random
    base = random.randint(min_dmg, max_dmg)
    return max(1, round(base * (att + 25) / 50))


def apply_defense(damage, deF: int, floor_frac: float = 0.1, whole: bool = True):
    """`floor_frac`: the minimum fraction of the raw roll that always gets
    through regardless of deF - "a hit can never be trivialized below this
    much." Default 0.1 is the player's own value (unchanged). Enemies use a
    per-rank floor instead (see entities.ENEMY_DEFENSE_FLOOR) so a boss's
    floor is meaningfully higher than a trash mob's.

    `whole=False` skips the round()+max(1,...) integer floor and returns a
    raw float instead - needed for continuous DoT ticks (bleed/burn, a tiny
    dps*dt fraction every frame), where forcing "at least 1 whole point"
    every single tick would silently multiply a DoT's real damage-per-second
    by the tick rate. Discrete hits (bullets, ability magnitudes, player
    incoming damage) keep the default whole=True."""
    reduced = damage - deF
    floor = damage * floor_frac
    real = max(reduced, floor)
    if not whole:
        return max(0.0, real)
    return max(1, round(real))


def speed_tiles_per_sec(spd: int) -> float:
    return 5.6 * (spd + 53.5) / 75


def attacks_per_sec(dex: int) -> float:
    return 6.5 * (dex + 17.3) / 75


def hp_regen_per_sec(vit: int) -> float:
    return 0.2407 * (vit + 8.3)


def mp_regen_per_sec(wis: int) -> float:
    return 0.12 * (wis + 4.2)


def xp_to_next(level: int) -> int:
    # soft curve, gentle early / steeper late - tuned ~4x faster than the
    # v0 curve so a level 1-20 co-op run is a single evening, not a grind
    return int(5 * level ** 1.7 + 8)

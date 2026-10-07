"""
Danger by distance (RotMG's beaches-to-Godlands gradient, for every mob on the continent):
the closer to the CENTRE of the continent, the deadlier everything is - more HP, harder hits,
faster attacks, sharper aggro - and the better the reward (XP, extra loot, and the Dungeon
Shards they drop open harder dungeons, the very centre even Heroic ones). The shores are
gentle. Night mobs follow the same rule (and come more often near the centre).

The big islands (out in the ocean ring) are NOT on this scale - they're the level-20 endgame
with their own scaling (doc 34), so danger_frac() returns None out there.

Pure functions of a world position + the map size, so co-op clients compute the same HUD
label locally. RealmSim._apply_danger() applies the multipliers once to every new hostile.
"""
import math

from game.constants import TILE

# tier 1 (shore) .. 5 (heart of the Realm)
TIERS = {
    1: ("Calm", (120, 205, 120)),
    2: ("Mild", (185, 215, 110)),
    3: ("Wild", (235, 200, 90)),
    4: ("Deadly", (240, 135, 60)),
    5: ("Lethal", (235, 60, 60)),
}
OCEAN_SLACK = 1.06  # beyond the continent's radius x this: the ocean ring / islands (no danger scale)

# Dungeon Shard difficulty weights by the tier the shard dropped in (Easy, Medium, Hard)
SHARD_DIFFICULTY_WEIGHTS = {
    0: (55, 32, 13),   # unknown (old saves, quest shards)
    1: (85, 15, 0),
    2: (65, 30, 5),
    3: (40, 42, 18),
    4: (18, 45, 37),
    5: (5, 35, 60),
}
HEROIC_SHARD_CHANCE_T5 = 0.08  # a tier-5 elite's shard is a HEROIC shard this often (killer level 16+)
HEROIC_MIN_LEVEL = 16


def continent_radius_px():
    from game import world
    return world.CONTINENT_R * TILE


def danger_frac(x, y, map_w_tiles, map_h_tiles):
    """0.0 at the continent's coast .. 1.0 at its centre; None out in the ocean / on islands."""
    cx, cy = map_w_tiles * TILE / 2, map_h_tiles * TILE / 2
    r = continent_radius_px()
    d = math.hypot(x - cx, y - cy) / r
    if d > OCEAN_SLACK:
        return None
    return max(0.0, min(1.0, 1.0 - d))


def tier(frac):
    if frac is None:
        return 0
    return 1 + min(4, int(frac * 5))


def label(frac):
    """("Wild", colour, tier) for the HUD, or None off the continent."""
    t = tier(frac)
    if not t:
        return None
    name, col = TIERS[t]
    return name, col, t


def mults(frac):
    """Stat multipliers for a mob spawned at this danger (frac 0 = coast .. 1 = centre)."""
    f = max(0.0, min(1.0, frac or 0.0))
    return {
        "hp": 0.6 + 1.6 * f ** 1.2,     # coast x0.6 .. centre x2.2
        "dmg": 0.65 + 0.85 * f,         # x0.65 .. x1.5
        "speed": 0.92 + 0.16 * f,       # x0.92 .. x1.08
        "cd": 1.15 - 0.30 * f,          # attack cooldowns x1.15 (slower) .. x0.85 (faster)
        "aggro": 0.9 + 0.35 * f,        # notices you from x0.9 .. x1.25 as far
        "xp": 0.8 + 0.8 * f,            # x0.8 .. x1.6 XP
        "loot_extra": max(0.0, f - 0.4) * 0.9,  # chance of an extra loot roll: 0 .. 54%
        "portal": 0.05 + 0.08 * f,      # an elite's Dungeon Shard chance: 5% .. 13%
    }


def ring_fracs():
    """The tier boundaries as fractions of the continent radius (for the full map's rings)."""
    return [1.0 - k / 5.0 for k in range(1, 5)]  # tier edges at 80/60/40/20% of the radius

"""
Weapon Shards ("runes"): equippable items that add effects to your weapon's shots.

They live in the dock's "Shards" tab - 12 slots, the first RUNE_ACTIVE_SLOTS (4) of which
are ACTIVE sockets that apply to whatever weapon you have equipped; the rest is storage.
Item slot "rune" (the name "shard" is already the dungeon-shard portal item), shape
"rune_<effect>" so every effect gets its own icon colour (sprites.item_icon).

Each shard has one effect and a rarity (common / rare / epic / mythic) that scales it.
Two shards with the same effect don't simply add up: the strongest counts in full and
every extra copy adds RUNE_STACK_BONUS on top.

Pure logic + data (no pygame): realm_sim.player_fire builds a bullet's effect list with
active_effects(), and realm_sim._resolve_bullet_hits applies them on hit.
"""
import random

RUNE_SLOTS = 12
RUNE_ACTIVE_SLOTS = 4
RARITIES = ("common", "rare", "epic", "mythic")
RARITY_MULT = {"common": 1.0, "rare": 1.4, "epic": 1.9, "mythic": 2.6}
RARITY_WEIGHT = {"common": 60, "rare": 28, "epic": 10, "mythic": 2}
RARITY_TIER = {"common": 3, "rare": 6, "epic": 9, "mythic": 12}  # drives the item's badge / feed value
RARITY_COLORS = {"common": (200, 200, 205), "rare": (110, 170, 255), "epic": (190, 100, 255),
                 "mythic": (255, 180, 60)}
RUNE_STACK_BONUS = 0.15

# effect -> (display name, colour, short description with {v} = the common-rarity value)
EFFECTS = {
    "bleed": ("Bleeding", (210, 40, 40), "hits make the target bleed"),
    "burn": ("Burning", (255, 130, 40), "hits set the target on fire"),
    "vulnerable": ("Sundering", (235, 205, 90), "hits make the target take more damage"),
    "frostbite": ("Frostbite", (140, 210, 255), "hits slow the target"),
    "chain": ("Chain Spark", (170, 150, 255), "hits arc to nearby enemies"),
    "keen": ("Keen Edge", (255, 245, 200), "a chance to crit for double damage"),
    "leech": ("Leech", (120, 230, 120), "heals you for part of the damage"),
    "splinter": ("Splinter", (230, 220, 180), "the shot splits into shards on hit"),
    "seeker": ("Seeker", (120, 255, 220), "shots curve toward enemies"),
    "impact": ("Impact", (200, 160, 120), "hits knock the target back"),
    "executioner": ("Executioner", (180, 20, 60), "bonus damage to enemies under 30% HP"),
    "echo": ("Echo", (160, 220, 255), "every few hits strike twice"),
}
EFFECT_KEYS = tuple(EFFECTS)

# per-effect base numbers at common rarity (scaled by RARITY_MULT, see magnitude())
BASE = {
    "bleed": 1.0, "burn": 1.0,          # x the normal bleed / burn DoT
    "vulnerable": 0.2,                  # +20% damage taken
    "frostbite": 0.25,                  # -25% speed (capped)
    "chain": 1.0,                       # 1 jump (rounded, max 3)
    "keen": 0.1,                        # 10% crit chance
    "leech": 0.03,                      # 3% of damage dealt healed
    "splinter": 2.0,                    # 2 splinters (max 4)
    "seeker": 1.6,                      # turn rate (rad/s)
    "impact": 16.0,                     # px of knockback
    "executioner": 0.3,                 # +30% damage under 30% HP
    "echo": 5.0,                        # every 5th hit repeats (fewer with rarity)
}


def magnitude(effect, mult):
    """The effect's real number at a combined strength `mult`."""
    b = BASE[effect]
    if effect == "chain":
        return max(1, min(3, int(round(b * mult))))
    if effect == "splinter":
        return max(2, min(4, int(round(b * (0.7 + 0.3 * mult)))))
    if effect == "echo":
        return max(2, int(round(b / mult ** 0.7)))
    if effect == "frostbite":
        return min(0.6, b * mult)
    if effect == "keen":
        return min(0.45, b * mult)
    return b * mult


def describe(effect, rarity):
    name, _col, desc = EFFECTS[effect]
    v = magnitude(effect, RARITY_MULT[rarity])
    nums = {"vulnerable": f"+{int(v * 100)}%", "frostbite": f"-{int(v * 100)}% speed",
            "chain": f"{v} jump{'s' if v > 1 else ''}", "keen": f"{int(v * 100)}% crit",
            "leech": f"{v * 100:.1f}% lifesteal", "splinter": f"{v} splinters", "impact": f"{int(v)} px",
            "executioner": f"+{int(v * 100)}%", "echo": f"every {v}th hit",
            "bleed": f"x{v:.1f} bleed", "burn": f"x{v:.1f} burn", "seeker": "homing"}
    return f"{desc} ({nums.get(effect, '')})"


def make_rune(rarity=None, effect=None, rng=random):
    """A Weapon Shard (random rarity by RARITY_WEIGHT and random effect if not given)."""
    from game.items import Item
    if rarity is None:
        rarity = rng.choices(RARITIES, weights=[RARITY_WEIGHT[r] for r in RARITIES])[0]
    if effect is None:
        effect = rng.choice(EFFECT_KEYS)
    name = f"{rarity.title()} {EFFECTS[effect][0]} Shard"
    return Item(name, "rune", RARITY_TIER[rarity], f"rune_{effect}", rune_effect=effect, rune_rarity=rarity,
                description=f"Weapon Shard - socket it in an ACTIVE slot of the Shards tab: {describe(effect, rarity)}.")


def is_rune(item):
    return item is not None and getattr(item, "slot", None) == "rune"


def active_effects(rune_slots):
    """{effect: combined strength} from the ACTIVE sockets (the strongest copy of an effect
    counts in full, each extra copy adds RUNE_STACK_BONUS)."""
    by = {}
    for it in (rune_slots or [])[:RUNE_ACTIVE_SLOTS]:
        if is_rune(it) and it.rune_effect in EFFECTS:
            by.setdefault(it.rune_effect, []).append(RARITY_MULT.get(it.rune_rarity, 1.0))
    return {eff: max(ms) + RUNE_STACK_BONUS * (len(ms) - 1) for eff, ms in by.items()}


def effect_color(effects):
    """The bullet tint for a set of effects (the strongest one's colour)."""
    if not effects:
        return None
    eff = max(effects, key=lambda k: effects[k])
    return EFFECTS[eff][1]


# --- drops: a small chance on elite / boss kills (night mobs and the Blood Moon pass a higher one)
RUNE_DROP_CHANCE = {"elite": 0.04, "boss": 0.25}


def maybe_drop(rank, chance_mult=1.0, rng=random):
    """A rune for a kill of this rank, or None (callers add it to the personal loot)."""
    ch = RUNE_DROP_CHANCE.get(rank, 0.0) * chance_mult
    if ch > 0 and rng.random() < ch:
        return make_rune(rng=rng)
    return None


def fuse_result(runes):
    """3 shards of the same rarity -> 1 shard of the next rarity (the first one's effect), or None."""
    if len(runes) != 3 or not all(is_rune(r) for r in runes):
        return None
    rar = runes[0].rune_rarity
    if any(r.rune_rarity != rar for r in runes) or rar == RARITIES[-1]:
        return None
    return make_rune(RARITIES[RARITIES.index(rar) + 1], runes[0].rune_effect)

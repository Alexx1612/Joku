"""
Item / loot system, modelled on RotMG's tiered vs. untiered (UT) equipment
and its brown / purple / white loot-bag rarity bands.

Honesty note: the *mechanics* here (tier bands, ATT/DEF/etc. formulas in
constants.py, the brown/purple/white bag rarity system) are reproduced from
the public wiki. The specific item names below are original, RotMG-style
tiered gear names, not a verified 1:1 transcription of the wiki's full
item tables (which run into the hundreds of entries per class) - see
README for the honest scope of what was and wasn't hand-verified.
"""
import json
import math
import os
import random
from dataclasses import dataclass, field
from game.constants import TIER_COLORS, BAG_COLORS
from game import achievements
from game import live_events

SLOT_WEAPON, SLOT_ABILITY, SLOT_ARMOR, SLOT_RING, SLOT_EGG = "weapon", "ability", "armor", "ring", "egg"
SLOT_SHARD = "shard"  # dungeon shards (see make_dungeon_shard) - used from the backpack like a potion/egg


def tier_band(tier: int) -> str:
    if tier <= 3:
        return "t_low"
    if tier <= 6:
        return "t_mid"
    if tier <= 9:
        return "t_high"
    return "t_top"


@dataclass
class Item:
    name: str
    slot: str
    tier: int
    shape: str
    is_ut: bool = False
    stat_bonus: dict = field(default_factory=dict)
    min_dmg: int = 0
    max_dmg: int = 0
    proc: str = ""
    # ability items only: "nova" | "heal" | "haste" | "chain" | "freeze" | "shield" | "drain" (SPACE to cast)
    effect: str = ""
    mp_cost: int = 0    # ability items only
    magnitude: int = 0  # ability items only: dmg (nova/chain/drain/freeze) / hp (heal/shield) / seconds (haste)
    description: str = ""  # flavor text shown in tooltips
    pet_kind: str = ""  # egg items only: which PET_KINDS entry it hatches into
    shard_theme: str = ""  # shard items only: which DUNGEON_THEMES key it opens (see realm_sim.py)
    # weapons only: one of "boomerang"/"bleed"/"burn"/"vulnerable" once a UT's proc has
    # been socketed onto this weapon via apply_socket() below - realm_sim.player_fire
    # checks this FIRST, before the name-based BOOMERANG_UT_NAMES/etc. lookup, so a
    # socketed weapon behaves identically downstream to a natively-procced UT.
    socketed_proc: str = None
    # pet carriers only (SLOT_EGG + shape "carrier"): a packed pet's full state
    # (Pet.net_state()) - using the item unpacks exactly that pet, levels/xp/bond
    # intact, instead of hatching a fresh one (see Player.pack_pet/use_potion)
    pet_state: dict = None

    @property
    def band(self) -> str:
        return "ut" if self.is_ut else tier_band(self.tier)

    @property
    def color(self):
        return TIER_COLORS[self.band]

    @property
    def display_name(self) -> str:
        prefix = f"[T{self.tier}] " if not self.is_ut and self.shape != "carrier" else ""
        return f"{prefix}{self.name}"

    def to_json(self):
        return dict(name=self.name, slot=self.slot, tier=self.tier, shape=self.shape,
                    is_ut=self.is_ut, stat_bonus=self.stat_bonus,
                    min_dmg=self.min_dmg, max_dmg=self.max_dmg, proc=self.proc,
                    effect=self.effect, mp_cost=self.mp_cost, magnitude=self.magnitude,
                    description=self.description, pet_kind=self.pet_kind, shard_theme=self.shard_theme,
                    socketed_proc=self.socketed_proc, pet_state=self.pet_state)

    @staticmethod
    def from_json(d):
        return Item(**d)


# ------------------------------------------------------------- item tables --
# Full 11-tier weapon progressions per class (T1 starter -> T11 near-endgame) -
# every tier 1-11 now has a dedicated item (previously only odd tiers 1,3,5,7,9,11
# did, with even tiers only reachable incidentally via _random_tiered's inclusive
# range check). Even-tier entries were added by interpolating damage roughly
# midway between their odd-tier neighbors, keeping the existing curve shape.
WEAPONS = {
    "wizard":     [("Wand", "staff", 1, (2, 4)), ("Cracked Wand", "staff", 2, (3, 6)),
                   ("Hexing Wand", "staff", 3, (4, 7)), ("Arc Wand", "staff", 4, (5, 9)),
                   ("Tome-Bound Staff", "staff", 5, (6, 11)), ("Warded Staff", "staff", 6, (8, 13)),
                   ("Glowing Rod", "staff", 7, (9, 15)), ("Radiant Rod", "staff", 8, (11, 18)),
                   ("Void Rod", "staff", 9, (13, 20)), ("Rod of the Void Marches", "staff", 10, (16, 24)),
                   ("Staff of the Astral Codex", "staff", 11, (18, 27))],
    "archer":     [("Shortbow", "bow", 1, (2, 5)), ("Hunting Bow", "bow", 2, (4, 7)),
                   ("Hunter's Bow", "bow", 3, (5, 9)), ("Recurved Longbow", "bow", 4, (6, 11)),
                   ("Recurve Bow", "bow", 5, (7, 13)), ("Ashwood Bow", "bow", 6, (9, 15)),
                   ("Wardbow", "bow", 7, (10, 17)), ("Stormtip Bow", "bow", 8, (12, 20)),
                   ("Longshot Bow", "bow", 9, (14, 22)), ("Duskrunner Bow", "bow", 10, (17, 25)),
                   ("Bow of Covert Havens", "bow", 11, (19, 29))],
    "warrior":    [("Rusty Sword", "sword", 1, (3, 6)), ("Notched Blade", "sword", 2, (5, 8)),
                   ("Falchion", "sword", 3, (6, 10)), ("Tempered Falchion", "sword", 4, (8, 13)),
                   ("Broadsword", "sword", 5, (9, 15)), ("Battle Cleaver", "sword", 6, (11, 17)),
                   ("Longsword", "sword", 7, (12, 19)), ("War Blade", "sword", 8, (14, 22)),
                   ("Runed Blade", "sword", 9, (16, 24)), ("Runed Greatsword", "sword", 10, (19, 28)),
                   ("Doom Bringer", "sword", 11, (21, 31))],
    "priest":     [("Wand of Light", "staff", 1, (1, 3)), ("Wand of Solace", "staff", 2, (2, 4)),
                   ("Wand of Recovery", "staff", 3, (2, 5)), ("Wand of Grace", "staff", 4, (3, 6)),
                   ("Seal of Blessing", "staff", 5, (3, 6)), ("Seal of Devotion", "staff", 6, (4, 7)),
                   ("Wand of the Lich King", "staff", 7, (4, 8)), ("Wand of the High Cleric", "staff", 8, (5, 9)),
                   ("Aegis Rod", "staff", 9, (6, 10)), ("Aegis of the Faithful", "staff", 10, (7, 12)),
                   ("Staff of the Sanctuary", "staff", 11, (8, 13))],
    "rogue":      [("Dirty Dagger", "sword", 1, (2, 5)), ("Honed Dagger", "sword", 2, (4, 7)),
                   ("Twisted Dagger", "sword", 3, (5, 9)), ("Serrated Dagger", "sword", 4, (7, 11)),
                   ("Fanged Knife", "sword", 5, (8, 13)), ("Venomfang Knife", "sword", 6, (10, 15)),
                   ("Assassin's Blade", "sword", 7, (11, 17)), ("Nightfall Blade", "sword", 8, (13, 20)),
                   ("Skean Dhu", "sword", 9, (15, 22)), ("Shadow Dhu", "sword", 10, (18, 26)),
                   ("Fang of Nefertati", "sword", 11, (20, 29))],
    "necromancer":[("Skull Wand", "staff", 1, (2, 4)), ("Bone Wand", "staff", 2, (3, 6)),
                   ("Wand of Bones", "staff", 3, (4, 8)), ("Wand of the Grave", "staff", 4, (5, 10)),
                   ("Wand of the Necromancer", "staff", 5, (6, 12)), ("Wraith-Touched Staff", "staff", 6, (8, 14)),
                   ("Wraith Staff", "staff", 7, (9, 16)), ("Staff of Withering", "staff", 8, (11, 19)),
                   ("Staff of Nightmares", "staff", 9, (13, 21)), ("Staff of the Reaper's Court", "staff", 10, (16, 25)),
                   ("Staff of the Void Reaper", "staff", 11, (18, 28))],
    "paladin":    [("Blunt Mace", "sword", 1, (2, 5)), ("Iron Mace", "sword", 2, (4, 7)),
                   ("Spiked Mace", "sword", 3, (5, 9)), ("Barbed Mace", "sword", 4, (7, 12)),
                   ("War Mace", "sword", 5, (8, 14)), ("War Hammer", "sword", 6, (10, 16)),
                   ("Holy Mace", "sword", 7, (11, 18)), ("Sacred Mace", "sword", 8, (13, 21)),
                   ("Mace of Wrath", "sword", 9, (15, 23)), ("Mace of Retribution", "sword", 10, (18, 27)),
                   ("Mace of the Crusader", "sword", 11, (20, 30))],
    "assassin":   [("Throwing Knife", "sword", 1, (2, 4)), ("Balanced Knife", "sword", 2, (3, 6)),
                   ("Poison Dagger", "sword", 3, (4, 8)), ("Numbing Dagger", "sword", 4, (6, 10)),
                   ("Katar", "sword", 5, (7, 12)), ("Twin Katar", "sword", 6, (9, 14)),
                   ("Shadow Blade", "sword", 7, (10, 16)), ("Nightshade Blade", "sword", 8, (12, 19)),
                   ("Kris of Shadows", "sword", 9, (14, 21)), ("Kris of the Void", "sword", 10, (17, 24)),
                   ("Blade of the Nightblade", "sword", 11, (19, 27))],
}

UT_WEAPONS = {
    "wizard": [("Doomstaff", "staff", (14, 22), "Piercing bolts that split on hit",
                "Forged from a shattered star. Its bolts punch through the first "
                "target and split into two lesser bolts, spreading the ruin behind them."),
               ("Staff of Esben", "staff", (17, 26), "Bolts pierce and home slightly",
                "Named for the mad archivist who bound a hunting spirit into the "
                "wood. Bolts curve gently toward the nearest foe as they fly."),
               ("Staff of Esoteria", "staff", (20, 30), "Bolts split into two on hit",
                "Bound in a language no living scholar can read. Every bolt "
                "wants to be two bolts, and mostly gets its way."),
               ("Wand of the Forbidden", "staff", (24, 34), "Bolts pierce through everything",
                "Confiscated from a mage who broke a law nobody remembered was "
                "still on the books. Nothing it hits ever slows the next bolt down.")],
    "archer": [("Hellfire Bow", "bow", (16, 24), "Shots leave a burning trail",
                "Strung with a sinew that never stopped burning. Every loosed "
                "arrow leaves a wake of embers that scorches anything crossing it."),
               ("Bow of Coordinated Void", "bow", (19, 28), "Shots occasionally split",
                "Strung from a single thread pulled out of nowhere at all. Every "
                "so often, one arrow insists on becoming two."),
               ("Bow of Covert Havens", "bow", (22, 32), "Grants brief invisibility on shot",
                "A ranger's last resort. Loosing an arrow folds the wielder briefly "
                "out of sight, just long enough to vanish into the treeline."),
               ("Bow of the Still Wind", "bow", (26, 36), "Shots never miss a stationary target",
                "Carved in a place where the air itself never moves. Its shots "
                "seem to already know exactly where they're going.")],
    "warrior": [("Oryxmas Cleaver", "sword", (18, 28), "Swings hit in a wide arc",
                 "A festival blade too large for any normal duel. Every swing "
                 "carves a wide arc, catching everything foolish enough to crowd in."),
                ("Blade of the Unshackled", "sword", (21, 31), "Attack speed increases as HP drops",
                 "Once bound to a champion who fought hardest when cornered. It "
                 "still remembers - and quickens the angrier its wielder gets."),
                ("Skardhal", "sword", (24, 34), "Chance to stun on hit",
                 "A runed greatsword said to ring like a struck bell on impact - "
                 "the sound alone is enough to stagger lesser foes."),
                ("Blade of the Grand Sepulcher", "sword", (27, 38), "Deals bonus damage to bosses",
                 "Recovered from a tomb built for something that was never "
                 "supposed to wake back up. It remembers how to hurt big things.")],
    "priest": [("Staff of the Sunken", "staff", (10, 16), "Heals nearby allies on hit",
                "Recovered from a drowned temple. Every strike sends a ripple of "
                "restorative light through nearby allies."),
               ("Rod of Convalescence", "staff", (12, 18), "Heals self for a portion of damage dealt",
                "Once used by a field medic who never lost a patient. Every "
                "strike quietly returns a sliver of the harm it deals."),
               ("Wand of the Wild Ancients", "staff", (14, 20), "Heals allies and self on hit",
                "Carved from a tree that grew for a thousand years over a "
                "battlefield. Its touch mends both friend and wielder alike."),
               ("Sceptre of the First Light", "staff", (17, 24), "Piercing bolts that heal on hit",
                "Said to be carved from the very first sunrise. Its light passes "
                "clean through the wicked and mends everyone it passes over instead.")],
    "rogue": [("Fiery Dagger", "sword", (16, 24), "Shots leave a burn DoT",
               "Quenched in dragon's blood instead of water. Every cut smolders "
               "long after the blade has moved on."),
              ("Dagger of Twilight", "sword", (18, 26), "Guaranteed crit from stealth",
               "Forged in the last light before true dark. It strikes truest in "
               "the instant just before you're seen."),
              ("Coat of Diamond Dust", "sword", (20, 28), "Guaranteed crit vs. slowed targets",
               "Its edge is lined with crystal dust that finds every gap in "
               "armor - especially on a target too slow to twist away."),
              ("Shiver Blade", "sword", (23, 32), "Shots leave a chilling DoT",
               "Kept sheathed in a block of ice for a century before anyone dared "
               "draw it. It never quite warmed back up.")],
    "necromancer": [("Staff of Prisms", "staff", (16, 24), "Bolts split into three on hit",
                      "A lattice of dark crystal that refracts every cast bolt into "
                      "three converging shards of the same curse."),
                     ("Sceptre of the Forgotten King", "staff", (18, 26), "Heals self for a portion of damage dealt",
                      "The last thing a fallen tyrant held. It still siphons "
                      "strength from whatever it strikes, same as it always did."),
                     ("Staff of Lore", "staff", (20, 28), "Bolts pierce through undead-like foes",
                      "Bound with forbidden texts on the nature of death - its bolts "
                      "pass clean through anything already halfway there."),
                     ("Staff of the Unliving Choir", "staff", (23, 32), "Bolts split into three and pierce",
                      "Every voice bound into it died singing the same curse. Cast "
                      "it and you can still hear all of them at once.")],
    "paladin": [("Mace of the Tinkerer", "sword", (18, 26), "Heals self for a portion of damage dealt",
                 "An eccentric inventor's masterwork. Every blow it lands feeds a "
                 "portion of the damage straight back into the wielder's own wounds."),
                ("Hammer of the Vigil", "sword", (20, 28), "Emits a protective aura on hit",
                 "Carried by an order that never slept in shifts - all of them "
                 "stood watch together, always. Its aura still remembers how."),
                ("Mace of the Fallen King", "sword", (22, 30), "Emits a protective aura on hit",
                 "Once wielded by a king who fell defending his own. Every strike "
                 "still radiates a faint shield over those who stand nearby."),
                ("Warhammer of the Last Stand", "sword", (25, 34), "Deals bonus damage to bosses",
                 "Swung by the last defender of a siege nobody else survived. It "
                 "hits hardest exactly when the fight looks most hopeless.")],
    "assassin": [("Ghostly Katar", "sword", (18, 26), "Brief invisibility after a kill",
                  "Forged in a plane between worlds. A confirmed kill lets the "
                  "wielder slip half out of reality for a heartbeat."),
                 ("Fang of the Silent Order", "sword", (20, 28), "Guaranteed crit from stealth",
                  "Carried by an order sworn never to speak of their work. Its "
                  "wielder never needs to be seen to be effective."),
                 ("Kris of Elón", "sword", (22, 30), "Guaranteed crit from stealth",
                  "A wavy-bladed heirloom blessed to never miss the vital point - "
                  "provided the first strike comes from the shadows."),
                 ("Nightbringer's Edge", "sword", (25, 34), "Shots leave a chilling DoT",
                  "Quenched in the coldest hour of the longest night. Whatever it "
                  "touches carries that cold with it long after the strike lands.")],
}

# ------------------------------------------------------------ UT socketing --
# Each per-class UT_WEAPONS list has exactly 4 entries; realm_sim.py's
# BOOMERANG_UT_NAMES/BLEED_UT_NAMES/BURN_UT_NAMES/VULNERABLE_UT_NAMES dicts
# resolve a UT's mechanic purely from ITS OWN INDEX in that list (0=bleed,
# 1=boomerang, 2=burn, 3=vulnerable) matched by exact name - identify_proc_kind
# below mirrors that same index convention so a "socket" action can figure out
# which mechanic a given UT carries without importing realm_sim (which already
# imports FROM this module - importing it back here would be circular).
_UT_PROC_KIND_BY_INDEX = {0: "bleed", 1: "boomerang", 2: "burn", 3: "vulnerable"}


def identify_proc_kind(item: "Item"):
    """Returns "boomerang"/"bleed"/"burn"/"vulnerable" if `item`'s exact name
    matches one of the 4 per-class UT_WEAPONS entries that carries a real
    mechanic, else None (a plain tiered weapon, armor, or a UT whose flavor
    proc has no matching mechanic)."""
    for uts in UT_WEAPONS.values():
        for idx, ut_tuple in enumerate(uts):
            if ut_tuple[0] == item.name:
                return _UT_PROC_KIND_BY_INDEX.get(idx)
    return None


def apply_socket(source: "Item", target: "Item"):
    """Consumes `source` (expected to be a UT weapon carrying one of the 4
    known proc kinds) to imprint that same proc onto `target` (a different
    weapon), overwriting anything previously socketed onto `target`. Does NOT
    remove `source` from wherever it's stored - the caller (main.py's
    _transfer_item / server.py's "socket_proc" action) does that, since only
    the caller knows which backpack/equip slot `source` came from. Returns
    (ok: bool, message: str) for feed-message display either way."""
    if source is target:
        return False, "Can't socket a weapon into itself"
    if target.slot != SLOT_WEAPON:
        return False, "Can only socket a proc onto a weapon"
    kind = identify_proc_kind(source)
    if kind is None:
        return False, f"{source.name} doesn't carry a socketable proc"
    target.socketed_proc = kind
    return True, f"Socketed {kind} onto {target.name}"


# Active abilities (the 2nd equip slot) - cast with Space, cost MP, one signature
# effect per class (mirrors RotMG: every class's ability slot does something
# different - a caster nova, a healer's tome, a fighter's rally, a rogue's dash),
# original names/values, three tiers each so ability items fit into the same loot
# rolls as weapons/armor/rings instead of being a separate never-upgraded stub.
# The T9 ultimate of four classes upgrades to a more elaborate effect kind
# ("chain" / "freeze" / "drain" / "shield" - see realm_sim.use_ability) so the
# top of each ability line feels like a real capstone spell, not just a bigger
# number on the same nova/heal/haste effect as the starter tier.
ABILITIES = {
    # damage-effect magnitudes (nova/chain/drain/freeze only - heal/haste/shield below
    # are untouched) bumped ~25% over their original values: these 4 effect types are
    # now TELEGRAPHED (see realm_sim.TELEGRAPH_DELAY) instead of resolving instantly, so
    # an enemy that reacts to the warning can now walk out of the blast entirely - the
    # bump keeps a LANDED cast feeling like the real burst-on-a-real-cooldown spike the
    # plan calls for, compensating for the damage the new dodge window can now avoid.
    "wizard":      [("Orb of Shatter", "nova", 1, 40, 22,
                      "Hurls a crackling orb that shatters on impact, scorching everything caught in the blast."),
                     ("Orb of Ruin", "nova", 5, 55, 40,
                      "A denser, angrier orb - the shockwave alone is enough to crack stone."),
                     ("Orb of the Void", "chain", 9, 70, 56,
                      "Rips a tear in reality at the target point; the resulting arc of void-lightning "
                      "leaps between up to four nearby enemies, unraveling each one it touches.")],
    "necromancer": [("Skull of Blight", "nova", 1, 40, 20,
                      "Throws a cursed skull that bursts into a cloud of withering blight."),
                     ("Skull of Corruption", "nova", 5, 55, 35,
                      "The blight cloud thickens into something with real teeth."),
                     ("Skull of the Reaper", "drain", 9, 70, 50,
                      "Detonates a skull that siphons the life from every enemy in the blast, "
                      "channeling half of all damage dealt straight back into the caster as healing.")],
    "archer":      [("Quiver of Thunder", "nova", 1, 35, 17,
                      "Looses a volley of thunder-tipped arrows in every direction at once."),
                     ("Quiver of Storms", "nova", 5, 50, 32,
                      "The volley grows into a small localized storm front."),
                     ("Quiver of the Gale", "freeze", 9, 65, 37,
                      "Unleashes a howling gale of ice-tipped arrows that damages and roots every "
                      "enemy caught in it, freezing them in place for a few seconds.")],
    "priest":      [("Tome of Mending", "heal", 1, 45, 20,
                      "Reads a passage of the old liturgy, mending the caster and nearby allies."),
                     ("Tome of Restoration", "heal", 5, 60, 35,
                      "A longer, more potent verse - closes wounds that Mending couldn't reach."),
                     ("Tome of Rebirth", "heal", 9, 75, 55,
                      "The final chapter. A wave of pure restorative light washes over the whole "
                      "party, closing even grievous wounds in an instant.")],
    "paladin":     [("Aegis of Faith", "heal", 1, 45, 16,
                      "Calls down a small blessing that mends the caster and nearby allies."),
                     ("Aegis of Devotion", "heal", 5, 60, 28,
                      "A stronger blessing, warm enough to feel from across the room."),
                     ("Aegis of the Ward", "shield", 9, 75, 60,
                      "Raises a shimmering barrier of holy light around the caster and nearby allies "
                      "that absorbs incoming damage before a single point of it reaches their HP.")],
    "warrior":     [("Rally Horn", "haste", 1, 35, 6,
                      "A short, sharp horn blast that quickens the whole party's step."),
                     ("War Horn", "haste", 5, 50, 6,
                      "A deeper blast that carries the fury of an old battlefield."),
                     ("Horn of the Vanguard", "haste", 9, 65, 8,
                      "The horn that once led armies. Its call pushes the whole party into a "
                      "sustained battle-fury, faster on their feet and quicker on the draw.")],
    "rogue":       [("Smoke Draught", "haste", 1, 30, 6,
                      "A bitter draught that thins the air around the drinker, quickening every step."),
                     ("Shadow Draught", "haste", 5, 45, 6,
                      "Distilled from something that doesn't like the sun."),
                     ("Draught of the Void", "haste", 9, 60, 8,
                      "A drop of the space between moments. Time itself seems to slow for "
                      "everyone except the party.")],
    "assassin":    [("Cloak of Shadows", "haste", 1, 30, 6,
                      "Wraps the caster and nearby allies in a sliver of true darkness, quickening their step."),
                     ("Veil of Night", "haste", 5, 45, 6,
                      "The darkness deepens into something with real weight to it."),
                     ("Veil of the Abyss", "haste", 9, 60, 8,
                      "A veil torn from the space between stars. For a few seconds, the whole "
                      "party moves like they were never bound by ordinary time at all.")],
}

# Armor comes in 3 archetypes, matching real RotMG's own grouping exactly onto
# this project's 8 classes with no leftovers: Heavy (Warrior/Paladin - highest
# DEF+VIT), Light/Leather (Archer/Assassin/Rogue - moderate DEF + a touch of
# SPD), Robe (Wizard/Necromancer/Priest - lowest DEF, WIS+VIT instead). Which
# archetype a drop pulls from is resolved from _pick_drop_class's result via
# CLASS_ARMOR_ARCHETYPE, same as weapons/abilities - so cross-class drops can
# hand a Wizard a piece of Heavy armor exactly as easily as a Warrior weapon.
HEAVY_ARMORS = [
    ("Padded Vest", 1, {"deF": 3}, "Thick padding, more bruise-absorber than armor."),
    ("Leather Cuirass", 2, {"deF": 4}, "A stiff leather breastplate, better than nothing."),
    ("Chain Mail", 3, {"deF": 5, "vit": 1}, "Interlocking rings that turn a glancing blow."),
    ("Banded Mail", 4, {"deF": 7, "vit": 1}, "Iron bands riveted over chain for the joints that matter most."),
    ("Plate Armor", 5, {"deF": 9, "vit": 2}, "Heavy plate favored by front-line fighters."),
    ("Reinforced Plate", 6, {"deF": 10, "vit": 2}, "Plate doubled over at every seam a blade could find."),
    ("Guardian Plate", 7, {"deF": 12, "vit": 3}, "Plate forged for those who stand between others and harm."),
    ("Bulwark Plate", 8, {"deF": 14, "vit": 3}, "Built to be the wall an ally hides behind."),
    ("Armor of the Snake Pit", 9, {"deF": 16, "vit": 4}, "Scaled plating salvaged from something enormous."),
    ("Armor of the Coiled Serpent", 10, {"deF": 18, "vit": 5}, "Scaled plating from something that was still alive when it was taken."),
    ("Armor of the Golden Rooster", 11, {"deF": 21, "vit": 5}, "Gleaming ceremonial plate said to ward off death itself."),
]
LIGHT_ARMORS = [
    ("Traveler's Leather", 1, {"deF": 2, "spd": 1}, "Worn-in leather, light enough to run in."),
    ("Studded Leather", 2, {"deF": 3, "spd": 1}, "Metal studs sewn in without slowing the wearer down."),
    ("Ranger's Jerkin", 3, {"deF": 4, "spd": 2}, "Cut close to the body, built for moving through brush unheard."),
    ("Reinforced Jerkin", 4, {"deF": 5, "spd": 2}, "A jerkin with just enough hidden plating to matter."),
    ("Shadowweave Vest", 5, {"deF": 6, "spd": 3}, "Dyed dark enough to disappear between one step and the next."),
    ("Duskweave Vest", 6, {"deF": 7, "spd": 3}, "Woven from something that never quite catches the light."),
    ("Nightsilk Coat", 7, {"deF": 8, "spd": 4}, "Impossibly light for how much it turns aside."),
    ("Stormsilk Coat", 8, {"deF": 9, "spd": 4}, "Said to have been woven during an actual storm, for reasons nobody agrees on."),
    ("Cloak of the Wildlands", 9, {"deF": 10, "spd": 5}, "Patched together from a dozen different hides, none of them tame."),
    ("Cloak of the Long Road", 10, {"deF": 12, "spd": 5}, "Worn thin by a road that never seemed to end, and still holding."),
    ("Cloak of the Silent Step", 11, {"deF": 14, "spd": 6}, "You only ever hear this one after it's already too late."),
]
ROBES = [
    ("Novice's Robe", 1, {"deF": 1, "wis": 1}, "Plain cloth, still smelling faintly of the academy."),
    ("Apprentice Robe", 2, {"deF": 1, "wis": 2}, "A robe for someone who's cast the spell wrong at least once."),
    ("Scholar's Robe", 3, {"deF": 2, "wis": 2, "vit": 1}, "Lined with pockets for scrolls nobody ever files properly."),
    ("Warded Robe", 4, {"deF": 2, "wis": 3, "vit": 1}, "A minor ward woven into the hem, more habit than protection."),
    ("Robe of the Grove", 5, {"deF": 3, "wis": 4, "vit": 1}, "Woven from living bark; it seems to heal alongside its wearer."),
    ("Robe of the Deep Wood", 6, {"deF": 3, "wis": 4, "vit": 2}, "Grown, not woven, somewhere sunlight rarely reaches."),
    ("Robe of Whispers", 7, {"deF": 4, "wis": 5, "vit": 2}, "You can hear it thinking, if you stand close enough."),
    ("Robe of Hidden Sight", 8, {"deF": 4, "wis": 6, "vit": 2}, "Embroidered with an eye that's definitely watching something."),
    ("Robe of the Arcane Court", 9, {"deF": 5, "wis": 7, "vit": 3}, "Formal wear for a court that stopped meeting centuries ago."),
    ("Robe of the Void Between", 10, {"deF": 5, "wis": 8, "vit": 3}, "Stitched from a fabric that doesn't quite finish being there."),
    ("Robe of the Astral Sea", 11, {"deF": 6, "wis": 9, "vit": 4}, "Wearing it feels like standing somewhere very far above the ground."),
]
CLASS_ARMOR_ARCHETYPE = {
    "warrior": "heavy", "paladin": "heavy",
    "archer": "light", "assassin": "light", "rogue": "light",
    "wizard": "robe", "necromancer": "robe", "priest": "robe",
}
_ARMOR_TABLE_BY_ARCHETYPE = {"heavy": HEAVY_ARMORS, "light": LIGHT_ARMORS, "robe": ROBES}

# Rings are NOT class-restricted in real RotMG either - stays a single shared
# 11-tier table, no archetype split needed.
RINGS = [("Ring of Vigor", 1, {"vit": 2}, "A plain band that quickens the body's own healing."),
         ("Ring of Clarity", 2, {"wis": 2}, "A thin silver band that quiets a racing mind."),
         ("Ring of Sages", 3, {"wis": 3}, "Etched with formulas even its wearer doesn't fully understand."),
         ("Ring of Tenacity", 4, {"vit": 2, "att": 2}, "Worn smooth by a hand that never let go of anything."),
         ("Ring of Fury", 5, {"att": 4}, "Warms with the wearer's own anger, sharpening every blow."),
         ("Ring of Resolve", 6, {"att": 3, "vit": 2}, "Given to those who chose to stand their ground once, and never stopped."),
         ("Ring of Decades", 7, {"vit": 3, "wis": 3}, "Said to have passed through a hundred hands, each a little wiser."),
         ("Ring of the Wanderer", 8, {"att": 4, "deF": 2}, "Worn thin by a road that never seemed to end."),
         ("Ring of the Sphinx", 9, {"att": 5, "deF": 3}, "Carved with a riddle that has never been solved."),
         ("Ring of the Ancients", 10, {"att": 5, "wis": 5}, "Older than the ruins it was finally found in."),
         ("Ring of Perpetual Light", 11, {"att": 6, "wis": 6}, "A sliver of captured sunrise, warm to the touch.")]

# One flavor line per tier 1-11 (index 0-10) - expanded in lockstep with WEAPONS
# gaining a dedicated item at every tier instead of just the odd ones.
_WEAPON_TIER_FLAVOR = [
    "A basic starting weapon - not much to look at, but it swings true.",
    "A slightly sturdier take on the starter gear, still rough around the edges.",
    "A step up from the starter gear, favored by adventurers past their first week.",
    "Serviceable and unglamorous - the kind of weapon nobody remembers buying.",
    "A dependable mid-tier weapon favored by working adventurers.",
    "Solid craftsmanship, the sort a guild smith would sign their name to.",
    "Well-crafted and battle-tested; veterans keep these long after they've moved on.",
    "Fine enough that other adventurers will ask where you found it.",
    "A rare, powerful weapon that most adventurers only ever see in a shop window.",
    "Exceptional work, spoken of in the same breath as actual named heroes.",
    "A near-mythical weapon of legend, the stuff of Nexus rumors.",
]


def _weapon_description(cls_name, idx):
    return f"{_WEAPON_TIER_FLAVOR[idx]} A {cls_name}'s tool of the trade."


def make_starter_weapon(cls_name: str) -> Item:
    name, shape, tier, (mn, mx) = WEAPONS[cls_name][0]
    return Item(name, SLOT_WEAPON, tier, shape, min_dmg=mn, max_dmg=mx,
                description=_weapon_description(cls_name, 0))


def make_starter_ability(cls_name: str) -> Item:
    name, effect, tier, mp_cost, magnitude, desc = ABILITIES[cls_name][0]
    return Item(name, SLOT_ABILITY, tier, "ability", effect=effect, mp_cost=mp_cost,
                magnitude=magnitude, description=desc)


# ------------------------------------------------------------------- pets --
# Pets hatch from egg items (see PET_KINDS / make_egg below) and follow their
# owner, passively using THREE independent effects on their own cooldowns -
# heal, mp-restore, AND a weak attack, all able to fire in the very same tick
# (see entities.Pet.update) - matching how RotMG pets really work (3 separate
# ability slots, each fed/leveled on its own) rather than the old v0 shape
# where a pet was locked to exactly one of the three forever.
#
# Every pet can use all 3 abilities; PET_FAMILY_BASE gives each ability's base
# magnitude/cooldown at level 1, scaled up by that ability's OWN level (see
# pet_ability_stats below) as it's fed. A pet's hatch "family" just decides
# which ability it STARTS more advanced in (its natural specialty) - the
# other two start at level 1 and are worth feeding up if you want a pet that
# does everything well.
PET_FAMILY_BASE = {
    "heal": dict(magnitude=8, cooldown=6.0),
    "magic": dict(magnitude=6, cooldown=6.0),
    "attack": dict(magnitude=6, cooldown=2.6),
}
PET_ABILITY_KEYS = ("heal", "magic", "attack")
# Egg rarity gates how far EACH ability can be leveled, and how advanced the
# pet's specialty ability starts (its other two abilities always start at 1).
# "mythic" is fusion-only (two maxed legendaries, see Player.feed_pet) - it never
# drops as an egg (_EGG_RARITY_WEIGHT has no entry for it).
PET_RARITY_MAX_LEVEL = {"common": 10, "uncommon": 15, "rare": 20, "legendary": 30, "mythic": 40}
PET_RARITY_START_LEVEL = {"common": 3, "uncommon": 5, "rare": 7, "legendary": 10, "mythic": 14}
PET_RARITY_ORDER = ["common", "uncommon", "rare", "legendary", "mythic"]
PET_RARITY_COLORS = {"common": (200, 200, 205), "uncommon": (120, 220, 130), "rare": (110, 170, 255),
                     "legendary": (255, 190, 70), "mythic": (255, 110, 220)}
# carrier item tier by rarity - only drives the icon/bag color band, a carrier is never fed
PET_CARRIER_TIER = {"common": 2, "uncommon": 5, "rare": 8, "legendary": 11, "mythic": 12}

PET_LEVEL_XP_STEP = 30    # flat feed-xp needed to advance one ability level
PET_FEED_XP_PER_TIER = 6  # feed-xp granted per point of the fed item's tier, split across all 3 abilities


# Bond: lifetime feed-xp a pet has soaked up (every feed counts in full, even once
# its abilities are capped, and fusion sums both pets' bond) - the "how much you've
# put into it" knob. Bond level multiplies magnitudes (up to x2) and trims
# cooldowns (up to -25%), see pet_ability_stats.
PET_BOND_DIVISOR = 30
PET_BOND_MAX_LEVEL = 25
# heal/mana cooldowns never drop below this, however maxed/bonded the pet - keeps a
# mythic pet a strong sustain companion rather than a free invulnerability aura
PET_SUSTAIN_COOLDOWN_FLOOR = 1.5


def pet_bond_level(bond):
    return min(PET_BOND_MAX_LEVEL, int(math.sqrt(max(0.0, bond) / PET_BOND_DIVISOR)))


def pet_bond_progress(bond):
    """(level, fraction toward the next level) - fraction is 1.0 once capped."""
    lvl = pet_bond_level(bond)
    if lvl >= PET_BOND_MAX_LEVEL:
        return lvl, 1.0
    lo, hi = lvl * lvl * PET_BOND_DIVISOR, (lvl + 1) * (lvl + 1) * PET_BOND_DIVISOR
    return lvl, (bond - lo) / (hi - lo)


def pet_ability_stats(ability, level, bond_level=0):
    """magnitude/cooldown for one of a pet's 3 independent ability slots at a
    given level - replaces the old fixed per-kind values now that every pet
    can level (and simultaneously use) all 3 abilities instead of being
    locked to a single family forever. Modest per-level scaling, and cooldown
    is floored well above zero so a maxed pet still has a real cadence."""
    base = PET_FAMILY_BASE[ability]
    # past level 30 (mythic-only territory) each level adds a third as much, so
    # the extra mythic levels are a real upgrade without the curve running away
    lvl_gain = 0.15 * (min(level, 30) - 1) + 0.05 * max(0, level - 30)
    bond_level = max(0, min(PET_BOND_MAX_LEVEL, bond_level))
    magnitude = max(1, round(base["magnitude"] * (1 + lvl_gain) * (1 + 0.04 * bond_level)))
    floor = 0.5 if ability == "attack" else PET_SUSTAIN_COOLDOWN_FLOOR
    cooldown = max(floor, round(base["cooldown"] * (0.95 ** (level - 1)) * (1 - 0.01 * bond_level), 2))
    return magnitude, cooldown


def _pet_kind(base, tint, family, rarity, name, description):
    return dict(base=base, tint=tint, family=family, rarity=rarity, name=name, description=description)


PET_KINDS = {
    "hatchling": _pet_kind("bat", (255, 205, 90), "heal", "common", "Hatchling",
                            "A tiny bat pup that never quite learned to be scary. "
                            "Chirps softly and mends your wounds every few seconds."),
    "imp_pup": _pet_kind("imp", (255, 130, 130), "attack", "common", "Imp Pup",
                          "A pint-sized imp with a big attitude. Lobs a weak cinder "
                          "at the nearest enemy whenever one strays too close."),
    "wisp": _pet_kind("ghost", (150, 210, 255), "magic", "uncommon", "Wisp",
                       "A friendly will-o'-the-wisp that drifts at your shoulder, "
                       "trickling mana back to you as it glows."),
    "griffin_cub": _pet_kind("harpy", (255, 235, 180), "attack", "rare", "Griffin Cub",
                              "A downy cub with a griffin's fierce instincts already "
                              "showing. Dive-bombs nearby enemies with sharp little talons."),
    "moon_sprite": _pet_kind("ghost", (200, 160, 255), "heal", "rare", "Moon Sprite",
                              "Said to be born from a sliver of fallen moonlight. Its "
                              "gentle glow closes wounds far faster than its size would suggest."),
    "spirit_fox": _pet_kind("panther", (150, 220, 255), "magic", "rare", "Spirit Fox",
                             "A fox-shaped wisp that slips between worlds. Refills mana "
                             "faster and deeper than any lesser spirit."),
    "phoenix_chick": _pet_kind("salamander", (255, 170, 60), "heal", "legendary", "Phoenix Chick",
                                "Hatched from an ember that never went out. Legends say a full-grown "
                                "phoenix can raise the dead - this one just mends wounds, but fast."),
    "tipsy_thunderbird": _pet_kind("harpy", (255, 240, 120), "attack", "legendary", "Tipsy Thunderbird",
                                    "Swears it can fly in a straight line. Cannot. Still calls down "
                                    "a crackling peck on anything that looks at you funny."),
    "sommelier_serpent": _pet_kind("vine_serpent", (190, 90, 150), "magic", "legendary", "Sommelier Serpent",
                                    "Swirls, sniffs, and judges your mana like a fine vintage - then "
                                    "pours you another glass. Notes of oak and arcane regret."),
    # mythic - fusion only (two maxed legendaries), never an egg drop
    "hangover_hydra": _pet_kind("bog_crawler", (255, 120, 210), "heal", "mythic", "Hangover Hydra",
                                 "Three heads, three headaches, one very caring disposition. Each "
                                 "head insists the others are the drunk one. Mends wounds anyway."),
    "last_call_leviathan": _pet_kind("vine_serpent", (120, 230, 255), "attack", "mythic", "Last-Call Leviathan",
                                      "Rings a tiny bell and everything nearby is suddenly cut off. "
                                      "Permanently. Tips generously in bite marks."),
    "brewmaster_djinn": _pet_kind("ghost", (255, 170, 255), "magic", "mythic", "Brewmaster Djinn",
                                   "Grants exactly one wish: 'more mana, please.' Grants it again. "
                                   "And again. Has read the terms and conditions; you have not."),
    "sentient_fish": _pet_kind("frost_wraith", (120, 255, 170), "magic", "uncommon", "Sentient Fish",
                                "Hooked, reeled in, and unmistakably judging you for it. Floats "
                                "alongside in a small orb of water, muttering in bubbles, and "
                                "restores mana whenever it feels you've earned it."),
}


def make_egg(kind: str, tier: int = 1) -> Item:
    d = PET_KINDS[kind]
    return Item(f"{d['name']} Egg", SLOT_EGG, tier, "egg", pet_kind=kind,
                description=f"An egg, warm to the touch. Hatches into a {d['name']} "
                            f"({d['rarity']}). {d['description']}")


def pet_is_maxed(rarity, levels):
    """True when every ability in `levels` ({ability: level}) sits at that rarity's cap."""
    cap = PET_RARITY_MAX_LEVEL.get(rarity, 10)
    return all(levels.get(ab, 0) >= cap for ab in PET_ABILITY_KEYS)


def make_carrier(pet_state: dict) -> Item:
    """A packed pet as a backpack item (see Player.pack_pet) - tradable, vaultable,
    bag-droppable like any item; using it unpacks that exact pet."""
    kind = pet_state["kind"]
    d = PET_KINDS[kind]
    rarity = d["rarity"]
    levels = pet_state.get("levels", {})
    maxed = pet_is_maxed(rarity, levels)
    if rarity == "mythic":
        hint = "Mythic - the top of the food chain, can't fuse further."
    elif maxed:
        hint = f"MAXED - drop onto your active maxed {rarity} pet to fuse them into a "                f"{PET_RARITY_ORDER[PET_RARITY_ORDER.index(rarity) + 1]} pet."
    else:
        hint = f"Max every ability to fuse it with another maxed {rarity} pet."
    desc = f"Your {d['name']} is napping in here. Use it to let them out. {hint}"
    return Item(f"{d['name']} Carrier", SLOT_EGG, PET_CARRIER_TIER[rarity], "carrier",
                pet_kind=kind, description=desc, pet_state=dict(pet_state))


# How much of a rank's tier band the toughest mob of that rank (difficulty
# fraction 1.0, see entities.difficulty_fraction) has its FLOOR raised by, as a
# fraction of the band's width. The weakest mob of a rank (fraction 0.0) keeps
# the exact original [lo, hi] range untouched - tougher mobs only ever roll
# BETTER than the old flat-per-rank behavior, never worse, so no existing
# balance gets nerfed by this change; only the top end of the roster pulls ahead.
LOOT_DIFFICULTY_FLOOR_LIFT = 0.85


def _nudge_tier_range(lo, hi, difficulty):
    width = hi - lo
    if width <= 0:
        return lo, hi
    new_lo = lo + round(difficulty * LOOT_DIFFICULTY_FLOOR_LIFT * width)
    return min(new_lo, hi), hi


_ALL_CLASSES = list(WEAPONS.keys())
CROSS_CLASS_DROP_CHANCE = 0.4  # see _pick_drop_class


def _pick_drop_class(killer_cls):
    """60% the killer's own class, 40% split evenly among the other 7 - so e.g.
    an Archer can occasionally find a Priest wand, matching real RotMG's "any
    class's item can drop" loot pool instead of always handing back your own
    class's gear. Equipping/combat has no class-lock anywhere in the codebase
    (confirmed: Player.equip()/the drag-drop transfer/the server's equip action
    all check only item.slot, and realm_sim.player_fire()'s fire pattern always
    follows the WIELDER's own cls_name, never the weapon's origin class) - so
    this is purely a loot-variety change, not something that needs equip/combat
    code changes to "work"."""
    if random.random() >= CROSS_CLASS_DROP_CHANCE:
        return killer_cls
    others = [c for c in _ALL_CLASSES if c != killer_cls]
    return random.choice(others) if others else killer_cls


def roll_loot(cls_name: str, enemy_rank: str, difficulty: float = 0.5) -> list:
    """
    enemy_rank: 'trash' | 'elite' | 'boss' - controls bag odds AND how many
    tiers drop at once, mirroring RotMG's brown (common) / purple (mid,
    soulbound) / white (UT) bags. Bumped up from the v0 rates so co-op runs
    feel generous rather than grindy.

    difficulty: 0.0 (weakest of its rank) .. 1.0 (strongest of its rank) - see
    entities.difficulty_fraction. Nudges which end of each tier band below a
    roll draws from; the drop CHANCES (the random.random() < X checks) and the
    brown/purple/white bag colors are untouched by it.

    A "double_loot"-style live event (see game/live_events.py) doubles the
    expected count by running the whole independent roll a second (or Nth)
    time and merging the results, rather than inflating each individual
    random.random() < X chance past 1.0 - so a "double" event really means
    twice the drops, not diminishing-returns odds tweaks.
    """
    drops = _roll_loot_once(cls_name, enemy_rank, difficulty)
    extra_rolls = int(round(live_events.get_multiplier("loot_rolls"))) - 1
    for _ in range(max(0, extra_rolls)):
        drops.extend(_roll_loot_once(cls_name, enemy_rank, difficulty))
    return drops


def _roll_loot_once(cls_name: str, enemy_rank: str, difficulty: float = 0.5) -> list:
    # Rates rehauled alongside the tier-ladder/cross-class expansion above: elite's
    # brown/purple split shifted toward purple (more to find now that purple's own
    # band is denser), trash pulled back slightly since its pool is denser too, and
    # boss's UT chance raised (bosses should feel like the real UT gate).
    drops = []
    if enemy_rank == "trash":
        if random.random() < 0.18:
            lo, hi = _nudge_tier_range(1, 3, difficulty)
            drops.append(("brown", _random_tiered(cls_name, lo=lo, hi=hi)))
        if random.random() < 0.04:
            drops.append(("brown", _random_egg()))
        if random.random() < 0.06:
            drops.append(("brown", _random_potion()))
    elif enemy_rank == "elite":
        if random.random() < 0.55:
            lo, hi = _nudge_tier_range(1, 7, difficulty)
            drops.append(("brown", _random_tiered(cls_name, lo=lo, hi=hi)))
        if random.random() < 0.35:
            lo, hi = _nudge_tier_range(5, 11, difficulty)
            drops.append(("purple", _random_tiered(cls_name, lo=lo, hi=hi)))
        if random.random() < 0.12:
            drops.append(("purple", _random_egg()))
        if random.random() < 0.10:
            drops.append(("brown", _random_potion()))
        if random.random() < 0.06:
            drops.append(("brown", _random_temp_potion()))
    elif enemy_rank == "boss":
        lo, hi = _nudge_tier_range(7, 11, difficulty)
        drops.append(("purple", _random_tiered(cls_name, lo=lo, hi=hi)))
        drops.append(("purple", _random_tiered(cls_name, lo=lo, hi=hi)))
        if random.random() < 0.65:
            drops.append(("white", _random_ut(cls_name)))
        if random.random() < 0.35:
            drops.append(("white", _random_egg()))
        if random.random() < 0.30:
            drops.append(("purple", _random_potion()))
        if random.random() < 0.20:
            drops.append(("purple", _random_temp_potion()))
    return drops


def _random_tiered(cls_name, lo, hi) -> Item:
    """cls_name here is the KILLER's class - the weapon/ability portion of the
    pool actually sources from _pick_drop_class(cls_name), which is usually
    cls_name itself but sometimes a different class (see CROSS_CLASS_DROP_CHANCE).
    Armor is resolved to that same drop class's archetype (Heavy/Light/Robe -
    see CLASS_ARMOR_ARCHETYPE); rings are class-agnostic in real RotMG too, so
    they're unaffected by any of this."""
    drop_cls = _pick_drop_class(cls_name)
    pool = []
    for i, (n, shape, t, (mn, mx)) in enumerate(WEAPONS[drop_cls]):
        if lo <= t <= hi:
            pool.append(Item(n, SLOT_WEAPON, t, shape, min_dmg=mn, max_dmg=mx,
                              description=_weapon_description(drop_cls, i)))
    armor_table = _ARMOR_TABLE_BY_ARCHETYPE[CLASS_ARMOR_ARCHETYPE[drop_cls]]
    for n, t, bonus, desc in armor_table:
        if lo <= t <= hi:
            pool.append(Item(n, SLOT_ARMOR, t, "armor", stat_bonus=bonus, description=desc))
    for n, t, bonus, desc in RINGS:
        if lo <= t <= hi:
            pool.append(Item(n, SLOT_RING, t, "ring", stat_bonus=bonus, description=desc))
    for n, effect, t, mp_cost, magnitude, desc in ABILITIES.get(drop_cls, []):
        if lo <= t <= hi:
            pool.append(Item(n, SLOT_ABILITY, t, "ability", effect=effect, mp_cost=mp_cost,
                              magnitude=magnitude, description=desc))
    if not pool:
        n, shape, t, (mn, mx) = WEAPONS[drop_cls][0]
        pool.append(Item(n, SLOT_WEAPON, t, shape, min_dmg=mn, max_dmg=mx,
                          description=_weapon_description(drop_cls, 0)))
    return random.choice(pool)


def _random_ut(cls_name) -> Item:
    name, shape, (mn, mx), proc, desc = random.choice(UT_WEAPONS[cls_name])
    return Item(name, SLOT_WEAPON, 0, shape, is_ut=True, min_dmg=mn, max_dmg=mx, proc=proc, description=desc)


_EGG_RARITY_WEIGHT = {"common": 50, "uncommon": 25, "rare": 12, "legendary": 2}


def _random_egg() -> Item:
    # mythic (fusion-only) kinds have no weight entry, so they never drop as eggs
    kinds = [k for k in PET_KINDS if PET_KINDS[k]["rarity"] in _EGG_RARITY_WEIGHT]
    weights = [_EGG_RARITY_WEIGHT[PET_KINDS[k]["rarity"]] for k in kinds]
    kind = random.choices(kinds, weights=weights)[0]
    return make_egg(kind)


STAT_KEYS = ["att", "deF", "spd", "dex", "vit", "wis"]
SLOT_TEMP_POTION = "temp_potion"  # a second consumable family - see make_temp_potion()
PERMANENT_POTION_CAP = 20    # total permanent stat potions one character may EVER drink,
# freely allocated across the 6 stats - see Player.potions_used/use_potion()
TEMP_POTION_DURATION = 60.0  # seconds a temp-potion buff lasts, ticked in Player.net_update()
TEMP_POTION_AMOUNT = 6       # a temp buff is a much bigger, non-permanent version of the +1 permanent potion

_POTION_NAMES = {
    "att": "Potion of Attack", "deF": "Potion of Defense", "spd": "Potion of Speed",
    "dex": "Potion of Dexterity", "vit": "Potion of Vitality", "wis": "Potion of Wisdom",
}
_POTION_FLAVOR = {
    "att": "A bottled dose of raw striking power. Drinking it permanently sharpens every blow.",
    "deF": "A thick, metallic draught. Drinking it permanently toughens the skin like armor.",
    "spd": "A fizzing tonic that never sits still. Drinking it permanently quickens the step.",
    "dex": "A precise, steady brew. Drinking it permanently steadies the hand and the aim.",
    "vit": "A bottled dose of raw vigor. Drinking it permanently toughens the body.",
    "wis": "A bitter, clarifying tea. Drinking it permanently sharpens the mind.",
}


def make_potion(stat_key: str) -> Item:
    """A permanent +1 to one of the 6 stats when drunk - capped at
    PERMANENT_POTION_CAP total drinks per character, freely allocated across
    the 6 stats (see Player.use_potion/potions_used). shape="potion_<stat>"
    so sprites.item_icon() can render a distinct bottle color per stat (was
    one generic "potion" shape shared by all 6 - looked identical)."""
    return Item(_POTION_NAMES[stat_key], "consumable", 0, f"potion_{stat_key}", stat_bonus={stat_key: 1},
                description=_POTION_FLAVOR[stat_key])


def make_temp_potion(stat_key: str) -> Item:
    """A TEMP_POTION_DURATION-second +TEMP_POTION_AMOUNT buff to one stat - a
    bigger, non-permanent version of the potion above, not counted against
    the permanent-drink cap (see Player.temp_buffs). shape="draught_<stat>"
    gets sprites.item_icon()'s bigger/glowing "dramatic" treatment so it
    reads as visually distinct from the small permanent-potion bottle."""
    label = _POTION_NAMES[stat_key].split(" of ", 1)[1]
    return Item(f"Draught of {label}", SLOT_TEMP_POTION, 0, f"draught_{stat_key}",
                stat_bonus={stat_key: TEMP_POTION_AMOUNT},
                description="A potent but fleeting brew - its effects fade after about a minute.")


def _random_potion() -> Item:
    return make_potion(random.choice(STAT_KEYS))


# ------------------------------------------------------- goofy fishing junk --
# The fishing "junk" tier (45% of every catch - the single most common
# outcome, see RealmSim.fish_action) used to be a plain make_potion() call,
# mechanically identical to any other potion source and with zero personality
# despite being what most casts actually reel in. These give it a real,
# varied, funny catch table instead - most are still genuinely equippable
# (a real slot/stat_bonus, not just flavor text), one carries an actual
# player-chosen downside, and one is a real hatchable pet via the normal
# PET_KINDS/make_egg system above (see "sentient_fish").

def make_old_boot() -> Item:
    """A joke armor piece - real slot/stat_bonus (tiny but positive, never
    literally useless), just comically undersized next to a T1 armor drop."""
    return Item("Old Boot", SLOT_ARMOR, 0, "armor", stat_bonus={"deF": 1},
                 description="One boot. Just the one. Still has some fight "
                             "left in it - mostly holes, technically defense.")


def make_rubber_duck() -> Item:
    """A joke ring - real slot/stat_bonus, proc is flavor-text-only (see the
    Item.proc docstring) so this stays a pure content addition with no new
    mechanical hook, matching this fork's file scope."""
    return Item("Rubber Duck Ring", SLOT_RING, 0, "ring", stat_bonus={"wis": 1},
                 proc="Squeaks faintly, in perfect rhythm with every shot.",
                 description="A small yellow ring shaped like a bath toy. "
                             "Wearing it makes you feel inexplicably buoyant.")


def make_cursed_ring() -> Item:
    """The one entry with a REAL mechanical downside - a genuine trade-off
    the player chooses to accept by equipping it (or not), not just a
    negative-flavor item with no teeth. stat_bonus supports negative ints
    fine - Player.total_stat/equip just sum the dict, no validation rejects
    a negative value."""
    return Item("Cursed Ring of Buyer's Remorse", SLOT_RING, 0, "ring",
                 stat_bonus={"att": 2, "deF": -2},
                 description="CURSED. Hits noticeably harder. Also makes you "
                             "noticeably easier to hit. The previous owner "
                             "left it in the lake on purpose.")


def make_fishing_net_weapon() -> Item:
    """A joke weapon - real SLOT_WEAPON with genuinely poor damage, shape
    reuses the existing 'sword' icon primitive (sprites.item_icon() falls
    back cleanly for any shape without dedicated art, so this needed no
    sprites.py change)."""
    return Item("Tangled Fishing Net", SLOT_WEAPON, 0, "sword", min_dmg=1, max_dmg=2,
                 description="Technically a weapon now. You caught it on your "
                             "hook and, out of respect for the effort, are "
                             "legally required to try wielding it.")


def make_waterlogged_sandwich() -> Item:
    """A joke consumable - same 'consumable' slot as a stat potion, same
    permanent tiny stat_bonus shape, purely a flavor/personality entry."""
    return Item("Waterlogged Sandwich", "consumable", 0, "sandwich", stat_bonus={"vit": 1},
                 description="Has been in the lake for an unknowable length "
                             "of time and is, somehow, still technically "
                             "edible. Eating it toughens you up out of spite.")


_GOOFY_JUNK_TABLE = [
    (20, _random_potion),          # a real stat potion stays in the pool - junk isn't ALWAYS a joke
    (15, make_old_boot),
    (15, make_rubber_duck),
    (10, make_cursed_ring),
    (15, make_fishing_net_weapon),
    (15, make_waterlogged_sandwich),
    (10, lambda: make_egg("sentient_fish")),
]


def _random_junk_catch() -> Item:
    """The full junk-tier catch table - see RealmSim.fish_action, the
    caller. Weighted so a plain useful potion is still possible, but most
    casts now reel in one of the goofy items above instead."""
    weights = [w for w, _ in _GOOFY_JUNK_TABLE]
    maker = random.choices([m for _, m in _GOOFY_JUNK_TABLE], weights=weights)[0]
    return maker()


def _random_temp_potion() -> Item:
    return make_temp_potion(random.choice(STAT_KEYS))


def make_dungeon_shard(theme_name: str, theme_label: str) -> Item:
    """An elite kill's mob-portal chance (see realm_sim.MOB_PORTAL_CHANCE) now
    drops this into the loot bag instead of instantly opening a portal at the
    kill spot - RotMG-authentic "mobs drop dungeons" as a real carried item,
    used later from the backpack (like a potion/egg) to open a themed portal
    wherever the player happens to be standing."""
    return Item(f"{theme_label} Shard", SLOT_SHARD, 0, "shard", shard_theme=theme_name,
                description=f"A fragment of the {theme_label}. Use it to tear open a portal there.")


BAG_COLOR_FOR = BAG_COLORS


# --------------------------------------------------------------- wishing fountain --
# The Nexus fountain plaza (see world.make_nexus) doubles as a gamble: toss an item
# in, get something else back. Weighted toward a lateral "sidegrade" so it's rarely
# a total loss, with real upside (upgrade) and downside (downgrade) risk, plus a
# rare untiered jackpot - RotMG doesn't have this exact mechanic, but "risk an item
# at a fountain for a random reroll" is a natural extension of its wishing-well flavor.
def wish_reroll(cls_name: str, item: "Item") -> "Item":
    base_tier = item.tier if item.tier else 5
    roll = random.random()
    if roll < 0.05:
        return _random_ut(cls_name)
    if roll < 0.30:
        return _random_tiered(cls_name, lo=min(11, base_tier + 1), hi=min(11, base_tier + 3))
    if roll < 0.75:
        return _random_tiered(cls_name, lo=max(1, base_tier - 1), hi=min(11, base_tier + 1))
    return _random_tiered(cls_name, lo=1, hi=max(1, base_tier - 1))


def wish_fountain(player):
    """Sacrifices the lowest-tier eligible backpack item (never an egg - those are
    worth keeping) for a reroll. Returns (old_item, new_item, error_message)."""
    eligible = [i for i, it in enumerate(player.backpack) if it.slot != SLOT_EGG]
    if not eligible:
        return None, None, "You have nothing worth wishing on"
    idx = min(eligible, key=lambda i: player.backpack[i].tier or 0)
    old = player.backpack[idx]
    new = wish_reroll(player.cls_name, old)
    player.backpack[idx] = new
    if new.is_ut:
        changed, title = achievements.unlock(player.name, "high_roller")
        if changed:
            player.title = title
    return old, new, None


# ------------------------------------------------------------------ vault --
# The vault is per-account persistent storage, shared between single-player
# and co-op (the server writes it too), keyed by the player's chosen name.
# RotMG's real vault is a row of separate chests (8 slots each) you flip
# between, not one giant grid - VAULT_CHEST_SIZE/VAULT_SLOTS below mirror that
# (7 chests, matching the real game's default vault chest count).
VAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vaults")
VAULT_CHEST_SIZE = 8
VAULT_CHEST_COUNT = 10  # grown from 7 per user request
VAULT_SLOTS = VAULT_CHEST_SIZE * VAULT_CHEST_COUNT


def _vault_path(player_name: str) -> str:
    safe = "".join(c for c in player_name if c.isalnum() or c in "-_") or "player"
    return os.path.join(VAULT_DIR, f"{safe}.json")


def vault_exists(player_name: str) -> bool:
    return os.path.exists(_vault_path(player_name))


def load_vault(player_name: str) -> list:
    """Returns a FIXED-length (VAULT_SLOTS) list, `None` for an empty slot -
    each of the 10 chests is real, independent 8-slot storage (its own
    absolute index range) rather than a page into one shared, shifting list,
    so a chest genuinely acts as its own permanent bag (RotMG-style): taking
    an item out of chest 3 never moves anything in chest 4 into a different
    chest. A legacy save (from before this change - a COMPACT list with no
    `None`s, possibly shorter than VAULT_SLOTS) is migrated once by simply
    padding it out, sequentially filling from slot 0 - a faithful migration
    since that compact ordering IS how those items already behaved."""
    path = _vault_path(player_name)
    if not os.path.exists(path):
        return [None] * VAULT_SLOTS
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        items = [(Item.from_json(d) if d is not None else None) for d in raw]
    except (json.JSONDecodeError, OSError, TypeError, KeyError):
        return [None] * VAULT_SLOTS
    if len(items) < VAULT_SLOTS:
        items = items + [None] * (VAULT_SLOTS - len(items))
    elif len(items) > VAULT_SLOTS:
        items = items[:VAULT_SLOTS]
    return items


def save_vault(player_name: str, items: list) -> None:
    os.makedirs(VAULT_DIR, exist_ok=True)
    path = _vault_path(player_name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([(it.to_json() if it is not None else None) for it in items], f)
    os.replace(tmp, path)

"""
Brother Hammerstein's Anvil (Nexus): the forge. Pure logic over a player's backpack -
no pygame, no sim. The Anvil NPC's dialogue (game/dialogue.py) lists forge_options()
and applies the picked one with apply_forge(); in co-op the SERVER owns that
conversation, so forging is authoritative there.

Recipes
  Temper  - 3 items of the same slot and tier (weapon / armor / ring / ability, not UT
            or Divine) -> 1 item of the NEXT tier that slot has (abilities: 1 -> 5 -> 9
            -> 12 -> 14). The result follows the first item's class / armor type.
            Results of T12-T13 cost 1 Forge Ingot, T14 costs 2. T14 exists ONLY here.
  Reforge - 1 UT weapon + 2 Forge Ingots -> "Reforged <name>": +20% damage, its proc
            kept (socketed so it survives the rename). A Reforged UT can't be reforged
            again.
"""
from game import items as I

FORGE_SLOTS = (I.SLOT_WEAPON, I.SLOT_ARMOR, I.SLOT_RING, I.SLOT_ABILITY)
MAX_TEMPER_TIER = 14
REFORGE_INGOTS = 2
REFORGE_DMG_MULT = 1.2
REFORGED_PREFIX = "Reforged "


def ingot_cost(result_tier):
    return 0 if result_tier <= 11 else (1 if result_tier <= 13 else 2)


def _is_ingot(it):
    return it is not None and it.slot == I.SLOT_MATERIAL and it.shape == "ingot"


def _row_for(item):
    """(table kind, class/archetype, row index, rows) for a tiered item, or None."""
    if item.slot == I.SLOT_WEAPON:
        for cls, rows in I.WEAPONS.items():
            for i, r in enumerate(rows):
                if r[0] == item.name:
                    return "weapon", cls, i, rows
    elif item.slot == I.SLOT_ABILITY:
        for cls, rows in I.ABILITIES.items():
            for i, r in enumerate(rows):
                if r[0] == item.name:
                    return "ability", cls, i, rows
    elif item.slot == I.SLOT_ARMOR:
        for arch, rows in I._ARMOR_TABLE_BY_ARCHETYPE.items():
            for i, r in enumerate(rows):
                if r[0] == item.name:
                    return "armor", arch, i, rows
    elif item.slot == I.SLOT_RING:
        for i, r in enumerate(I.RINGS):
            if r[0] == item.name:
                return "ring", None, i, I.RINGS
    return None


def _tier_of_row(kind, row):
    return row[2] if kind in ("weapon", "ability") else row[1]


def _build(kind, owner, row, idx):
    if kind == "weapon":
        n, shape, t, (mn, mx) = row
        return I.Item(n, I.SLOT_WEAPON, t, shape, min_dmg=mn, max_dmg=mx,
                      description=I._weapon_description(owner, idx))
    if kind == "ability":
        n, effect, t, mp, mag, desc = row
        return I.Item(n, I.SLOT_ABILITY, t, "ability", effect=effect, mp_cost=mp, magnitude=mag, description=desc)
    if kind == "armor":
        n, t, bonus, desc = row
        return I.Item(n, I.SLOT_ARMOR, t, "armor", stat_bonus=dict(bonus), description=desc)
    n, t, bonus, desc = row
    return I.Item(n, I.SLOT_RING, t, "ring", stat_bonus=dict(bonus), description=desc)


def temper_result(item):
    """The item 3 copies of `item`'s slot+tier temper into (next tier of the same line), or None."""
    if item.is_ut or getattr(item, "divine", False) or item.slot not in FORGE_SLOTS:
        return None
    found = _row_for(item)
    if found is None:
        return None
    kind, owner, _i, rows = found
    nxt = [(j, r) for j, r in enumerate(rows) if _tier_of_row(kind, r) > item.tier]
    if not nxt:
        return None
    j, r = min(nxt, key=lambda jr: _tier_of_row(kind, jr[1]))
    if _tier_of_row(kind, r) > MAX_TEMPER_TIER:
        return None
    return _build(kind, owner, r, j)


def reforge_result(item):
    if not (item.slot == I.SLOT_WEAPON and item.is_ut) or item.name.startswith(REFORGED_PREFIX):
        return None
    proc_kind = item.socketed_proc or I.identify_proc_kind(item)
    return I.Item(REFORGED_PREFIX + item.name, I.SLOT_WEAPON, 0, item.shape, is_ut=True,
                  min_dmg=int(round(item.min_dmg * REFORGE_DMG_MULT)),
                  max_dmg=int(round(item.max_dmg * REFORGE_DMG_MULT)), proc=item.proc,
                  socketed_proc=proc_kind,
                  description=(item.description + " Reforged at the Anvil: it hits noticeably harder now.").strip())


def forge_options(player, limit=3):
    """Recipes the player's BACKPACK can make right now (equipped gear is never used), best first.
    Each: {kind, label, use: [items], ingots: [items], result: Item}."""
    bag = list(player.backpack)
    ingots = [it for it in bag if _is_ingot(it)]
    groups = {}
    for it in bag:
        if it.slot in FORGE_SLOTS and not it.is_ut and not getattr(it, "divine", False):
            groups.setdefault((it.slot, it.tier), []).append(it)
    out = []
    for (slot, tier), its in sorted(groups.items(), key=lambda kv: -kv[0][1]):
        if len(its) < 3:
            continue
        res = temper_result(its[0])
        if res is None:
            continue
        cost = ingot_cost(res.tier)
        if len(ingots) < cost:
            continue
        pretty = {"weapon": "weapons", "armor": "armors", "ring": "rings", "ability": "abilities"}[slot]
        extra = f" + {cost} Ingot{'s' if cost > 1 else ''}" if cost else ""
        out.append(dict(kind="temper", use=its[:3], ingots=ingots[:cost], result=res,
                        label=f"Temper 3 T{tier} {pretty}{extra} -> [T{res.tier}] {res.name}"))
    if len(ingots) >= REFORGE_INGOTS:
        for it in bag:
            res = reforge_result(it)
            if res is not None:
                out.append(dict(kind="reforge", use=[it], ingots=ingots[:REFORGE_INGOTS], result=res,
                                label=f"Reforge {it.name} + {REFORGE_INGOTS} Ingots"))
    return out[:limit]


def apply_forge(player, recipe):
    """Consumes the recipe's items from the backpack and adds the result.
    Returns (ok, message, result_item)."""
    need = list(recipe["use"]) + list(recipe["ingots"])
    bag = player.backpack
    for it in need:
        if not any(b is it for b in bag):
            return False, "Those items aren't in your backpack any more.", None
    for it in need:
        for i, b in enumerate(bag):
            if b is it:
                bag.pop(i)
                break
    res = recipe["result"]
    bag.append(res)
    return True, f"Brother Hammerstein hammers away... you got {res.display_name}!", res

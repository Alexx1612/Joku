"""
Brother Hammerstein's Anvil (Nexus): the forge. Pure logic over a player's backpack -
no pygame, no sim. The Anvil NPC's dialogue (game/dialogue.py) lists forge_options()
and applies the picked one with apply_forge(); in co-op the SERVER owns that
conversation, so forging is authoritative there.

Recipes
  Temper  - any 3 gear items of the same tier (weapon / armor / ring / ability, mixed
            slots are fine; not UT or Divine) -> 1 item of the NEXT tier of the FIRST
            item's line (abilities: 1 -> 5 -> 9 -> 12 -> 14), so it keeps that item's slot,
            class and armor type. (It used to need 3 of the same slot too - the pacing bot
            showed random loot rarely gives you that by Act III.)
            Results of T12-T13 cost 1 Forge Ingot, T14 costs 2. T14 exists ONLY here.
  Fuse    - 3 Weapon Shards of the same rarity -> 1 shard of the next rarity
            (the first one's effect; see game/runes.py).
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
            groups.setdefault(it.tier, []).append(it)
    out = []
    for tier, its in sorted(groups.items(), key=lambda kv: -kv[0]):
        if len(its) < 3:
            continue
        # the first item whose line has a next tier decides the result
        lead = next((it for it in its if temper_result(it) is not None), None)
        if lead is None:
            continue
        res = temper_result(lead)
        its = [lead] + [it for it in its if it is not lead]
        slot = res.slot
        cost = ingot_cost(res.tier)
        if len(ingots) < cost:
            continue
        used_slots = {it.slot for it in its[:3]}
        pretty = ({"weapon": "weapons", "armor": "armors", "ring": "rings", "ability": "abilities"}[slot]
                  if used_slots == {slot} else "items")
        extra = f" + {cost} Ingot{'s' if cost > 1 else ''}" if cost else ""
        out.append(dict(kind="temper", use=its[:3], ingots=ingots[:cost], result=res,
                        label=f"Temper 3 T{tier} {pretty}{extra} -> [T{res.tier}] {res.name}"))
    # Weapon Shards: 3 of the same rarity fuse into 1 of the next rarity (game/runes.py)
    from game import runes as _runes
    by_rarity = {}
    for it in bag:
        if _runes.is_rune(it):
            by_rarity.setdefault(it.rune_rarity, []).append(it)
    for rar in reversed(_runes.RARITIES):
        its = by_rarity.get(rar, [])
        if len(its) >= 3:
            res = _runes.fuse_result(its[:3])
            if res is not None:
                out.append(dict(kind="fuse", use=its[:3], ingots=[], result=res,
                                label=f"Fuse 3 {rar} Shards -> {res.name}"))
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

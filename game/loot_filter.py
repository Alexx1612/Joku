"""
Loot filter + auto-loot + loot beams (Options > Loot). Shared by single-player, the co-op
server (auto-loot is done by RealmSim, so it's authoritative) and the co-op client (which only
sees bag "ghosts" - Bag.net_state carries the few facts the filter needs).

  Auto-loot   - walk within AUTO_RADIUS of your own bag and the small stuff jumps into your
                backpack (overflowing into Bag 2): potions, Weapon Shards, gemstones, Forge
                Ingots / materials and dungeon shards. Gear is never auto-picked - you choose it.
  Hide below  - bags that hold ONLY gear under tier N are not drawn and can't be opened by
                right-click (anything rare - UT, Divine, T12+ - always shows).
  Beams       - a column of light over bags with something special in them (cyan mythic T12+,
                pink UT, gold Divine), so a good drop is visible from across the screen.
"""
import math

import pygame

AUTO_RADIUS = 40
HIDE_CHOICES = (0, 3, 5, 7, 9, 11)  # 0 = show everything
GEAR = ("weapon", "armor", "ring", "ability")
AUTO_SLOTS = ("consumable", "temp_potion", "material", "gem", "shard")
BEAM_COLORS = {"divine": (255, 210, 80), "ut": (255, 120, 220), "mythic": (80, 230, 240)}


def auto_pick(item):
    """Is this the small stuff auto-loot grabs?"""
    return item.slot in AUTO_SLOTS or bool(getattr(item, "rune_effect", ""))


def summary(items):
    """(top gear tier or 0, gear_only, rare kind or None) for a bag's items."""
    rank = {None: 0, "mythic": 1, "ut": 2, "divine": 3}
    top, rare = 0, None
    for it in items:
        kind = ("divine" if getattr(it, "divine", False) else "ut" if it.is_ut else
                "mythic" if it.slot in GEAR and it.tier >= 12 else None)
        if rank[kind] > rank[rare]:
            rare = kind
        if it.slot in GEAR and not it.is_ut:
            top = max(top, it.tier)
    gear_only = bool(items) and all(it.slot in GEAR for it in items)
    return top, gear_only, rare


def _bag_facts(bag):
    if isinstance(getattr(bag, "items", None), list):
        return summary(bag.items)
    return getattr(bag, "top", 0), getattr(bag, "gear_only", False), getattr(bag, "rare", None)


def hidden(bag, hide_below=None):
    """True when the filter hides this bag (never a chest, never anything rare)."""
    from game import settings
    n = settings.get("loot_hide_below") if hide_below is None else hide_below
    if not n or getattr(bag, "is_chest", False) or type(bag).__name__ in ("BazaarChest", "GhostChest"):
        return False
    top, gear_only, rare = _bag_facts(bag)
    return gear_only and rare is None and 0 < top < n


def visible_bags(bags, hide_below=None):
    return [b for b in bags if not hidden(b, hide_below)]


def auto_loot(player, bags, events=None):
    """Moves the small stuff out of the player's own nearby bags. Returns the items taken."""
    from game.entities import withdraw_from_bag, Bag
    if not getattr(player, "auto_loot", False) or not getattr(player, "alive", True):
        return []
    taken = []
    for bag in list(bags):
        if type(bag) is not Bag or not bag.can_be_taken_by(player.pid):
            continue
        if bag.pos.distance_to(player.pos) > AUTO_RADIUS:
            continue
        for i in range(len(bag.items) - 1, -1, -1):
            it = bag.items[i]
            if auto_pick(it) and withdraw_from_bag(bags, bag.id, i, player) is not None:
                taken.append(it)
                if events is not None:
                    events.append((player.pid, f"Picked up {it.display_name}", it.color))
    return taken


def draw_beam(surf, cam, bag, t=0.0):
    """A soft column of light over a bag with something rare inside."""
    from game import settings
    if not settings.get("loot_beams"):
        return
    _top, _g, rare = _bag_facts(bag)
    if rare is None:
        return
    col = BEAM_COLORS[rare]
    x, y = cam(bag.pos)
    h = 160
    pulse = 0.8 + 0.2 * math.sin(t * 4 + bag.pos.x * 0.01)
    beam = pygame.Surface((26, h), pygame.SRCALPHA)
    for i in range(h):
        a = int(230 * pulse * (i / h) ** 1.2)
        pygame.draw.line(beam, (*col, a // 3), (0, i), (25, i))
        pygame.draw.line(beam, (*col, a), (9, i), (16, i))
    surf.blit(beam, (int(x) - 13, int(y) - h + 4))

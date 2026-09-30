"""
Level / gear gates for the endgame zones (pure logic, no pygame).

  Heroic dungeons      level HEROIC_LEVEL+
  the big islands      level ISLAND_LEVEL+ (top-tier gear recommended - a warning, not a wall)
  the Mad God's Room   level MG_ROOM_LEVEL+ AND at least one T12+ (or Divine) item equipped

main.py / server.py call can_enter() right before swapping a player into one of
those instances; a refusal plays the "gate_denied" sound and shows the message.
"""
HEROIC_LEVEL = 16
ISLAND_LEVEL = 20
MG_ROOM_LEVEL = 20
MG_ROOM_TIER = 12
RECOMMENDED_ISLAND_TIER = 11
HEROIC_PREFIX = "heroic_"
MAD_GOD_ROOM = "mad_god_room"
ISLAND_PREFIX = "island_zone_"


def island_link_check(player, sim, target_pos):
    """A hub island_link portal: (ok, message) - only a trip ONTO an island is gated
    (the "Return" portals on the islands always work)."""
    tiles = getattr(sim, "island_tiles", None) or ()
    if target_pos is None or not tiles:
        return True, ""
    from game.constants import TILE
    if (int(target_pos[0] // TILE), int(target_pos[1] // TILE)) not in tiles:
        return True, ""
    return can_enter(player, ISLAND_PREFIX + "link")


def zone_kind(theme):
    theme = theme or ""
    if theme.startswith(HEROIC_PREFIX):
        return "heroic"
    if theme == MAD_GOD_ROOM:
        return "mg_room"
    if theme.startswith(ISLAND_PREFIX):
        return "island"
    return None


def _equipped(player):
    return [it for it in (getattr(player, s, None) for s in ("weapon", "armor", "ring", "ability")) if it is not None]


def average_gear_tier(player):
    tiers = [it.tier for it in _equipped(player) if not it.is_ut]
    return sum(tiers) / len(tiers) if tiers else 0.0


def can_enter(player, theme):
    """(ok, message). message is also set when ok but with a friendly warning."""
    kind = zone_kind(theme)
    lvl = getattr(player, "level", 1)
    if kind == "heroic" and lvl < HEROIC_LEVEL:
        return False, f"Heroic dungeons need level {HEROIC_LEVEL}+ (you're {lvl}). The portal hisses at you."
    if kind == "island":
        if lvl < ISLAND_LEVEL:
            return False, f"The ferryman won't take anyone under level {ISLAND_LEVEL} (you're {lvl}). Liability."
        if average_gear_tier(player) < RECOMMENDED_ISLAND_TIER:
            return True, f"The ferryman eyes your gear: \"T{RECOMMENDED_ISLAND_TIER}+ recommended. No refunds.\""
    if kind == "mg_room":
        if lvl < MG_ROOM_LEVEL:
            return False, f"The Mad God's Room needs level {MG_ROOM_LEVEL}+ (you're {lvl})."
        if not any(it.tier >= MG_ROOM_TIER or getattr(it, "divine", False) for it in _equipped(player)):
            return False, f"The Key won't turn. Equip at least one T{MG_ROOM_TIER}+ item first."
    return True, ""

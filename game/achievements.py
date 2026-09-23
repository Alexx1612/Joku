"""
Per-character achievements/titles - persisted the same way the vault is
(one small JSON file per player name), unlocked at natural milestones across
the game (first kill, first boss, first dungeon clear, first pet, first catch,
a wishing-fountain jackpot, hitting level 10/20). The most recently unlocked
title is what shows next to your name - no separate picker screen, deliberately
kept simple since the point is the moment of unlocking, not inventory management.
"""
import json
import os

# (id, title, description) - title is what's appended to your name, e.g. "Alice the Bloodied"
ACHIEVEMENTS = [
    ("first_blood", "the Bloodied", "Land your first kill"),
    ("angler", "the Angler", "Reel in your first catch while fishing"),
    ("egg_parent", "the Beastkeeper", "Hatch your first pet"),
    ("high_roller", "the Lucky", "Win an untiered item from the wishing fountain"),
    ("dungeoneer", "the Dungeoneer", "Clear a bonus dungeon's boss"),
    ("veteran", "the Veteran", "Reach level 10"),
    ("godslayer", "the Godslayer", "Slay a Mad God's Avatar in the open Realm"),
    ("reforger", "the Reforger", "Help calm a flaring shard or singing spire"),
    ("legend", "the Legend", "Reach level 20"),
]
ACH_BY_ID = {a[0]: a for a in ACHIEVEMENTS}
# unlock order == display priority: later entries in ACHIEVEMENTS are the "bigger"
# titles, so title_for() prefers the highest-index unlocked one, not just the newest
_ORDER = {a[0]: i for i, a in enumerate(ACHIEVEMENTS)}

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "achievements")


def _path(player_name: str) -> str:
    safe = "".join(c for c in player_name if c.isalnum() or c in "-_") or "player"
    return os.path.join(_DIR, f"{safe}.json")


def load(player_name: str) -> set:
    path = _path(player_name)
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(a for a in data if a in ACH_BY_ID)
    except (json.JSONDecodeError, OSError, TypeError):
        return set()


def save(player_name: str, ids: set) -> None:
    os.makedirs(_DIR, exist_ok=True)
    path = _path(player_name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f)
    os.replace(tmp, path)


def title_for(ids: set) -> str:
    if not ids:
        return ""
    best = max(ids, key=lambda a: _ORDER.get(a, -1))
    return ACH_BY_ID[best][1]


def unlock(player_name: str, ach_id: str):
    """Idempotent - safe to call every time the triggering moment happens, not just
    the first time. Returns (newly_unlocked: bool, new_title_or_None)."""
    if ach_id not in ACH_BY_ID:
        return False, None
    ids = load(player_name)
    if ach_id in ids:
        return False, None
    ids.add(ach_id)
    save(player_name, ids)
    return True, title_for(ids)

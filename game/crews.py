"""
Lightweight, client-local "Crew" identity for co-op - a persistent named
group (member list + one shared counter) with no server verification,
same trust model as friends.py (there's no auth to verify against). One
JSON file per crew, plus a small reverse-index file mapping player name ->
crew name for fast lookups. Atomic tmp+os.replace writes, same persistence
pattern as accounts.py/friends.py/vault/achievements.
"""
import json
import os

from game.accounts import sanitize_name

CREWS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "crews")
_MEMBERS_PATH = os.path.join(CREWS_DIR, "_members.json")


def _path(crew_name: str) -> str:
    return os.path.join(CREWS_DIR, f"{sanitize_name(crew_name)}.json")


def _atomic_write(path: str, data) -> None:
    os.makedirs(CREWS_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def load_crew(crew_name: str) -> dict:
    path = _path(crew_name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        members = data.get("members", [])
        return {
            "name": data.get("name", crew_name),
            "members": [n for n in members if isinstance(n, str)] if isinstance(members, list) else [],
            "boss_kills": int(data.get("boss_kills", 0)) if isinstance(data.get("boss_kills", 0), (int, float)) else 0,
        }
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


def _save_crew(crew: dict) -> None:
    _atomic_write(_path(crew["name"]), crew)


def _load_members_index() -> dict:
    if not os.path.exists(_MEMBERS_PATH):
        return {}
    try:
        with open(_MEMBERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def _save_members_index(index: dict) -> None:
    _atomic_write(_MEMBERS_PATH, index)


def get_crew_for_player(player_name: str) -> str:
    """Returns the crew name the player belongs to, or "" if none."""
    return _load_members_index().get(player_name, "")


def create_crew(crew_name: str, founder_name: str) -> dict:
    """Creates a new crew with founder as its first member. No-op (returns
    the existing crew) if a crew with this name already exists."""
    existing = load_crew(crew_name)
    if existing:
        return existing
    # A player can only be in one crew at a time - leave their old one first.
    old_crew_name = get_crew_for_player(founder_name)
    if old_crew_name:
        leave_crew(old_crew_name, founder_name)
    crew = {"name": crew_name, "members": [founder_name], "boss_kills": 0}
    _save_crew(crew)
    index = _load_members_index()
    index[founder_name] = crew_name
    _save_members_index(index)
    return crew


def join_crew(crew_name: str, player_name: str) -> dict:
    """Adds player_name to an existing crew. No-op if the crew doesn't
    exist. A player already in another crew leaves it first."""
    crew = load_crew(crew_name)
    if not crew:
        return {}
    old_crew_name = get_crew_for_player(player_name)
    if old_crew_name and old_crew_name != crew_name:
        leave_crew(old_crew_name, player_name)
    if player_name not in crew["members"]:
        crew["members"].append(player_name)
        _save_crew(crew)
    index = _load_members_index()
    index[player_name] = crew_name
    _save_members_index(index)
    return crew


def leave_crew(crew_name: str, player_name: str) -> dict:
    """Removes player_name from the crew and the reverse index. Deletes
    the crew file if it becomes empty."""
    crew = load_crew(crew_name)
    if crew and player_name in crew["members"]:
        crew["members"].remove(player_name)
        if crew["members"]:
            _save_crew(crew)
        else:
            path = _path(crew_name)
            if os.path.exists(path):
                os.remove(path)
    index = _load_members_index()
    if index.get(player_name) == crew_name:
        del index[player_name]
        _save_members_index(index)
    return crew


def increment_boss_kills(crew_name: str, amount: int = 1) -> int:
    """Adds amount to the crew's shared boss-kill counter. Returns the new
    total, or 0 if the crew doesn't exist."""
    crew = load_crew(crew_name)
    if not crew:
        return 0
    crew["boss_kills"] += amount
    _save_crew(crew)
    return crew["boss_kills"]

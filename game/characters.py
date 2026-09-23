"""
Per-account character-progress persistence - same idiom as accounts/vault/
achievements: one small JSON file per name, atomic tmp+os.replace writes.

Stores exactly what Player.full_state() already produces (level, xp, kills,
stats, equipped gear, backpack, pet, title) - no separate serialization scheme
to maintain, since that's the same payload shape already used for co-op network
sync. Position isn't meaningful to persist; a resumed character always spawns at
the current Nexus spawn point.

Permadeath still means what it always meant: dying deletes this file (see
delete_character), so hitting 0 HP genuinely ends that character for good, even
though a session now survives a graceful quit/disconnect in between.
"""
import json
import os

CHAR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "characters")


def _sanitize(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_") or "player"


def _path(name: str) -> str:
    return os.path.join(CHAR_DIR, f"{_sanitize(name)}.json")


def load_character(name: str):
    """Returns a full_state()-shaped dict, or None if there's no saved character
    (or it's corrupt/missing fields) - callers should fall back to a fresh Player."""
    path = _path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def save_character(name: str, player) -> None:
    """player: a live Player, saved via its existing full_state(). Never call this
    for a dead player - see delete_character; permadeath means gone, not saved."""
    os.makedirs(CHAR_DIR, exist_ok=True)
    path = _path(name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(player.full_state(), f)
    os.replace(tmp, path)


def delete_character(name: str) -> None:
    """Called on permadeath. The whole point of the mechanic is that this is
    permanent, so the next login (or the very next respawn) starts completely
    fresh - exactly like every session used to start before this file existed."""
    try:
        os.remove(_path(name))
    except OSError:
        pass

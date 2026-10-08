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

from game import paths as _paths

CHAR_DIR = _paths.data_path("characters")


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


# --- one character for single-player AND co-op (doc 42) -----------------------------------
# On the same PC they already share this folder (same name = same file). Joining a REMOTE
# server, the co-op client uploads its local save with the "join" message; the server checks it
# (validate) and keeps whichever copy has come further (pick_for_join). The client then mirrors
# the server's copy back into its own file while you play, so the next single-player run carries
# on from there - and a co-op death deletes it too: permadeath is the same everywhere.
UPLOAD_MAX_BYTES = 400_000


def progress(d):
    """How far a saved character has come: (level, xp, kills)."""
    try:
        return int(d.get("level", 1)), int(d.get("xp", 0)), int(d.get("kills", 0))
    except (TypeError, ValueError, AttributeError):
        return (0, 0, 0)


def validate(d, name):
    """A character a co-op client uploaded -> a clean full_state() dict, or None if it's malformed
    or impossible (level, stats, HP, tiers, bag sizes out of range)."""
    from game.entities import Player, LEVEL_CAP
    if not isinstance(d, dict):
        return None
    try:
        if len(json.dumps(d)) > UPLOAD_MAX_BYTES:
            return None
        p = Player.from_full_state(dict(d, pid="upload", name=name, x=0.0, y=0.0, alive=True))
    except Exception:
        return None
    if not (1 <= p.level <= LEVEL_CAP) or p.xp < 0 or p.kills < 0:
        return None
    if not all(0 <= getattr(p, s) <= 300 for s in ("att", "deF", "spd", "dex", "vit", "wis")):
        return None
    if not (0 < p.hp_max <= 10000 and 0 < p.mp_max <= 10000):
        return None
    if not (8 <= p.backpack_size <= 24) or len(p.backpack) > p.backpack_size or len(p.backpack2) > 12:
        return None
    gear = [p.weapon, p.armor, p.ring, p.ability] + list(p.backpack) + list(p.backpack2)
    if any(it is not None and not (0 <= int(getattr(it, "tier", 0)) <= 14) for it in gear):
        return None
    out = p.full_state()
    out.pop("pid", None)
    return out


def pick_for_join(server_saved, uploaded):
    """The copy a join should use: the one that has come further (the server's on a tie)."""
    if uploaded is None:
        return server_saved
    if server_saved is None or progress(uploaded) > progress(server_saved):
        return uploaded
    return server_saved

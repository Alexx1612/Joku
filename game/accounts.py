"""
Lightweight per-username accounts - USERNAME ONLY, NO PASSWORD/AUTH. This game is
explicitly no-auth/no-encryption (see README): the point of an "account" is just a
persistent identity for convenience (vault/achievement keying, a stable display name),
not access control. Persisted the same way the vault/achievements are: one small JSON
file per name, atomic tmp+os.replace writes, no database.
"""
import json
import os
from datetime import datetime, timezone

ACCOUNTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accounts")
_LAST_USED_PATH = os.path.join(ACCOUNTS_DIR, "_last_used.txt")


def sanitize_name(name: str) -> str:
    """Same sanitize rule as items._vault_path / achievements._path - kept identical
    (not imported cross-module) so accounts.py has zero import-order coupling to
    items.py/achievements.py. Candidate to become the one shared implementation those
    two adopt later; not worth the churn/risk to force that refactor now."""
    return "".join(c for c in name if c.isalnum() or c in "-_") or "player"


def _path(name: str) -> str:
    return os.path.join(ACCOUNTS_DIR, f"{sanitize_name(name)}.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_account(name: str):
    path = _path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def _save_account(name: str, record: dict) -> None:
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    path = _path(name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f)
    os.replace(tmp, path)


def touch_account(name: str) -> dict:
    """Creates the account (created_at == last_login == now) if it doesn't exist yet,
    or bumps last_login (and refreshes the stored display-case `username`) if it does.
    Idempotent - safe to call unconditionally on every login/join."""
    existing = load_account(name)
    now = _now()
    if existing is None:
        record = {"username": name, "created_at": now, "last_login": now}
    else:
        record = dict(existing)
        record["last_login"] = now
        record["username"] = name
    _save_account(name, record)
    return record


def get_last_used() -> str:
    """Best-effort convenience pointer for pre-filling the single-player name prompt -
    NOT part of the per-account JSON, just one small text file. Returns "" if missing."""
    try:
        with open(_LAST_USED_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def set_last_used(name: str) -> None:
    try:
        os.makedirs(ACCOUNTS_DIR, exist_ok=True)
        with open(_LAST_USED_PATH, "w", encoding="utf-8") as f:
            f.write(name)
    except OSError:
        pass

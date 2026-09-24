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


# ---------------------------------------------------------------- Echoes --
# "Echoes" are an account-wide, permadeath-softening currency (Batch 12) -
# earned on a character's death, spent at the Nexus's Echo Keeper on a
# small, fixed set of PERMANENT, POWER-NEUTRAL unlocks (never raw ATT/DEF/
# etc, so a run's skill challenge stays real). Stored as extra fields on the
# same per-account JSON record `touch_account` already maintains, same
# atomic tmp+os.replace save.
BACKPACK_SLOT_COST = 60          # echoes for the 1st extra backpack slot
BACKPACK_SLOT_COST_STEP = 60     # each further slot costs this much more
MAX_BACKPACK_BONUS_SLOTS = 2
STARTING_XP_COST = 30
# Deliberately small (well under xp_to_next(1), ~13-24 depending on rounding) -
# a visible head-start on the XP bar, not a free level-up. Handing out enough
# XP to actually level up would be a real stat/power gain (HP/MP/stat rolls
# happen on level-up, see Player.gain_xp), which contradicts this whole
# system's "permanent unlocks are power-neutral" design constraint.
STARTING_XP_BOOST_AMOUNT = 10


def get_echoes(name: str) -> int:
    rec = load_account(name)
    return int(rec.get("echoes", 0)) if rec else 0


def add_echoes(name: str, amount: int) -> int:
    """Adds `amount` echoes (no-op if <= 0) and returns the new balance."""
    if amount <= 0:
        return get_echoes(name)
    rec = dict(load_account(name) or touch_account(name))
    rec["echoes"] = int(rec.get("echoes", 0)) + amount
    _save_account(name, rec)
    return rec["echoes"]


def spend_echoes(name: str, amount: int) -> bool:
    """Deducts `amount` echoes if affordable and returns True; leaves the
    balance untouched and returns False otherwise."""
    if amount <= 0:
        return False
    rec = load_account(name)
    have = int(rec.get("echoes", 0)) if rec else 0
    if have < amount:
        return False
    rec = dict(rec)
    rec["echoes"] = have - amount
    _save_account(name, rec)
    return True


def award_echoes_for_death(name: str, level: int) -> int:
    """Called once per permadeath - the softer landing for the run that just
    ended. Scaled by how far the character got, never by anything spent."""
    amount = max(1, level // 2)
    add_echoes(name, amount)
    return amount


def get_unlocks(name: str) -> dict:
    rec = load_account(name)
    unlocks = rec.get("unlocks") if rec else None
    return dict(unlocks) if isinstance(unlocks, dict) else {}


def set_unlock(name: str, key: str, value) -> None:
    rec = dict(load_account(name) or touch_account(name))
    unlocks = dict(rec.get("unlocks")) if isinstance(rec.get("unlocks"), dict) else {}
    unlocks[key] = value
    rec["unlocks"] = unlocks
    _save_account(name, rec)


def buy_backpack_slot(name: str):
    """Returns (ok: bool, message: str)."""
    unlocks = get_unlocks(name)
    have = int(unlocks.get("backpack_slots", 0))
    if have >= MAX_BACKPACK_BONUS_SLOTS:
        return False, "Backpack slots already maxed."
    cost = BACKPACK_SLOT_COST + have * BACKPACK_SLOT_COST_STEP
    if not spend_echoes(name, cost):
        return False, f"Not enough Echoes (need {cost})."
    set_unlock(name, "backpack_slots", have + 1)
    return True, f"Backpack slot unlocked! ({have + 1}/{MAX_BACKPACK_BONUS_SLOTS})"


def buy_starting_xp_boost(name: str):
    """Returns (ok: bool, message: str)."""
    unlocks = get_unlocks(name)
    if unlocks.get("starting_xp_boost"):
        return False, "Already unlocked."
    if not spend_echoes(name, STARTING_XP_COST):
        return False, f"Not enough Echoes (need {STARTING_XP_COST})."
    set_unlock(name, "starting_xp_boost", True)
    return True, "Future characters will start with bonus XP!"


def apply_unlocks(player, name: str) -> None:
    """Applies this account's permanent unlocks to a FRESH character only -
    call exactly once, right after constructing a brand-new (never-saved)
    Player, at the same real entry points that already call load_title()
    (main.py's start_run, server.py's fresh-join branch) - never on a
    resumed/loaded character, whose backpack_size/xp are already whatever
    was persisted (re-applying here would double-grant the bonus)."""
    unlocks = get_unlocks(name)
    slots = int(unlocks.get("backpack_slots", 0))
    if slots:
        player.backpack_size += slots
    if unlocks.get("starting_xp_boost"):
        player.gain_xp(STARTING_XP_BOOST_AMOUNT)

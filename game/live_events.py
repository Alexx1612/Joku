"""Rotating live events.

The active event follows a fixed real-time schedule (EVENT_WINDOW seconds per
slot, cycling through SCHEDULE - "no event" slots included), so every process
that computes it - main.py (single-player) and server.py (the co-op host) -
agrees without any coordination. Co-op clients never compute it themselves:
server.py sends the active event in every snapshot and coop_client.py shows
that (see its `live_event` field).

RR_EVENT forces one event for hosts/tests (e.g. RR_EVENT=double_loot, or
RR_EVENT=none for no event at all); RR_EVENT_ROTATION=off disables the
schedule (tests/run_all_checks.py sets it so a rotating event can never make
a baseline test flaky).

Only the process that actually rolls loot/xp/blood-moon chance applies the
multiplier - in co-op that's the server (it owns RealmSim).
"""
import os
import time

EVENTS = {
    "double_loot": {
        "label": "Double Loot Weekend",
        "loot_rolls": 2.0,
        "blood_moon_chance": 1.0,
    },
    "blood_moon_week": {
        "label": "Blood Moon Week",
        "loot_rolls": 1.0,
        "blood_moon_chance": 2.5,
    },
    "happy_hour": {
        "label": "Happy Hour (+50% XP)",
        "xp": 1.5,
    },
    "two_for_one": {
        "label": "Two-for-One Tuesday (double loot, +25% XP)",
        "loot_rolls": 2.0,
        "xp": 1.25,
    },
}

EVENT_WINDOW = 25 * 60  # seconds per schedule slot
SCHEDULE = [None, "double_loot", None, "happy_hour", None, "blood_moon_week", None, "two_for_one"]

_forced = os.environ.get("RR_EVENT") or None
_rotation = os.environ.get("RR_EVENT_ROTATION", "on").lower() not in ("off", "0", "false", "no")
# ACTIVE_EVENT: the FORCED event (RR_EVENT), or None - kept for callers/tests that
# check the forced value; the live answer (schedule included) is current_event()
ACTIVE_EVENT = _forced if _forced in EVENTS else None


def current_event(now=None):
    """The active event key right now (or at `now`, a time.time() value), or None."""
    if _forced is not None:
        return ACTIVE_EVENT  # a forced unknown / "none" value means no event
    if not _rotation:
        return None
    t = time.time() if now is None else now
    return SCHEDULE[int(t // EVENT_WINDOW) % len(SCHEDULE)]


def get_multiplier(key: str) -> float:
    """1.0 (no-op) unless the active event defines a multiplier for `key`."""
    ev = current_event()
    if ev is None:
        return 1.0
    return EVENTS[ev].get(key, 1.0)


def multiplier_at(key, when):
    """Like get_multiplier, but for the event that will be active at time.time() value `when`."""
    ev = current_event(when)
    return 1.0 if ev is None else EVENTS[ev].get(key, 1.0)


def upcoming(n=4, now=None):
    """The next n schedule slots (including the current one): [(event_key or None, start, end)]
    as time.time() values. A forced event (RR_EVENT) is one open-ended slot; rotation off = []."""
    t = time.time() if now is None else now
    if _forced is not None:
        return [(ACTIVE_EVENT, t, None)]
    if not _rotation:
        return []
    slot = int(t // EVENT_WINDOW)
    return [(SCHEDULE[(slot + i) % len(SCHEDULE)], (slot + i) * EVENT_WINDOW, (slot + i + 1) * EVENT_WINDOW)
            for i in range(n)]


def label_for(event_key):
    return EVENTS[event_key]["label"] if event_key in EVENTS else None


def active_label():
    """The display label for the active event, or None if none is active."""
    return label_for(current_event())

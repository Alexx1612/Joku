"""An optional, host-settable rotating live event, resolved once from the
RR_EVENT environment variable at import time.

Both main.py (single-player) and server.py (the co-op host) import this
module the same way - there's no separate CLI flag to parse in each. To run
an event, set RR_EVENT before launching either one, e.g.:

    RR_EVENT=double_loot python server.py
    RR_EVENT=blood_moon_week python main.py

Only the process that actually rolls loot/blood-moon chance applies the
multiplier - in co-op that's the server (it owns RealmSim). coop_client.py
only reads ACTIVE_EVENT/active_label() to show the Nexus banner; it never
re-applies a multiplier itself. Note this means a remote co-op client only
sees the banner if RR_EVENT is also set in *its own* process environment
(e.g. the host also launches their own coop_client.py from the same shell) -
relaying the active event to remote clients over the network protocol would
require a server.py snapshot-field change, which is out of scope here.
"""
import os

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
}

ACTIVE_EVENT = os.environ.get("RR_EVENT") or None
if ACTIVE_EVENT not in EVENTS:
    ACTIVE_EVENT = None


def get_multiplier(key: str) -> float:
    """1.0 (no-op) unless an active event defines a multiplier for `key`."""
    if ACTIVE_EVENT is None:
        return 1.0
    return EVENTS[ACTIVE_EVENT].get(key, 1.0)


def active_label():
    """The display label for the active event, or None if none is active."""
    if ACTIVE_EVENT is None:
        return None
    return EVENTS[ACTIVE_EVENT]["label"]

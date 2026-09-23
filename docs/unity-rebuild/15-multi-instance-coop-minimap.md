# 15 — Multi-instance co-op dungeons + minimap zoom parity (Batch 7)

Source: `memory/project_rotmg_batch3_bags_dungeons_bosses.md`, "## Batch 7"
section, corroborated by direct grep against the current codebase
(`server.py`, `game/realm_sim.py`, `game/minimap.py`).

---

## 1. Multi-instance co-op dungeons

**What it is:** Different groups of players entering the same dungeon
portal now get their own separate, independent dungeon instance instead of
all being dropped into one shared instance — so one group clearing a
dungeon doesn't affect (or get affected by) another group that entered the
same portal.

**Why:** Prior to this, the server's dungeon/bonus-zone simulation appears
to have assumed a single shared instance per dungeon type; with multiple
concurrent players/groups this meant unrelated parties could collide inside
what should have been "their" dungeon run.

**How it was implemented:** `server.py` gained a `portal_instance_map`
(confirmed present via grep) mapping a portal/dungeon entry to the specific
instance a given player/group is routed into, rather than a single fixed
target. On the simulation side, `game/realm_sim.py`'s model of bonus/dungeon
zones changed from a single `bonus_sim` object to a `bonus_sims` dict
(confirmed present via grep) keyed by instance, so multiple simultaneous
dungeon instances of the same type can run their own independent
`RealmSim`-equivalent state in parallel rather than sharing one.
Server-authoritative routing (which instance a given connecting player
lands in) lives in `server.py`; per-instance simulation ticking uses the
same core `RealmSim` machinery already used for the Realm and single-
instance bonus zones (see the "begin_tick()" ordering fix and lair-respawn/
active-radius logic described in earlier work), just instantiated multiple
times.

**Unity rebuild prompt:**
> Support multiple independent, concurrently-running instances of the same
> dungeon/level definition on the server, keyed by instance rather than by
> dungeon type alone — route each entering player/group to a specific
> instance (creating a fresh one if none of their party is already in one)
> and keep a keyed collection of live simulation states (one full
> simulation instance per active dungeon instance), reusing the exact same
> per-tick simulation/update logic already used for the single shared
> open-world simulation rather than forking a separate code path for
> instanced content.

---

## 2. Minimap zoom parity

**What it is:** The small always-visible corner minimap's own zoom cap
was brought in line with the full-map (M-key) overlay's zoom cap, which had
already been raised from 3x to 8x back in Batch 2 (doc 10, section F) but —
at the time — deliberately left the corner minimap's separate zoom
constant alone.

**Why:** The inconsistency between the two zoom caps (full-map at 8x, corner
minimap still at its old lower cap) was explicitly pointed out once both
existed side by side, and fixed here rather than being left as designed
behavior.

**How it was implemented:** `game/minimap.py`'s `CORNER_MAX_ZOOM`
(confirmed present via grep) raised to match the full-map overlay's
`MAX_ZOOM = 8.0`, so both minimap surfaces now share the same maximum zoom
level rather than one being capped lower than the other for no
functional reason.

**Unity rebuild prompt:**
> When a UI element exists in two forms (e.g. a small always-on corner
> widget and a full-screen overlay version of the same data), keep shared
> tunables like zoom range driven from one constant/config value rather
> than two independently-set ones — a fix or adjustment to one form should
> either automatically apply to the other, or the two constants should be
> checked for consistency any time either one changes, so they don't
> silently drift apart the way this project's minimap and full-map zoom
> caps did until it was explicitly noticed and reconciled here.

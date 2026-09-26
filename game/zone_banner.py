"""
"Where am I" for both clients: resolves the local player's place (zone, realm
biome, big named area, island, dungeon) into

* a zone-entry title card that fades in/holds/fades out, and
* the music track for that place (game/music.py),

with the anti-spam rules that keep A -> B -> A -> B wandering calm:

* a place is only accepted after the player has stayed in it for DWELL seconds
  (portal/zone changes use the much shorter ZONE_DWELL);
* the same place is never re-announced within REPEAT_S seconds;
* a new card arriving while another is still showing cross-fades into it
  (the old one fades out while the new one fades in) - no pop, no stacking;
* the music uses its own music.Hysteresis dwell so it doesn't thrash on a
  biome border either.
"""
from game import music

FADE_IN, HOLD, FADE_OUT = 0.4, 1.8, 0.6
CROSSFADE = 0.35
DWELL = 1.2
ZONE_DWELL = 0.25
REPEAT_S = 25.0
MUSIC_DWELL = 2.0
ISLAND_R_TILES = 52

_BIOME_TITLES = {b: b.title() for b in music.BIOMES}
_BIOME_TITLES.update({"ice": "Glacier", "cave": "Crystal Deep", "highlands": "Highlands"})


class Card:
    def __init__(self, title, subtitle):
        self.title, self.subtitle = title, subtitle
        self.t = 0.0
        self.out_at = FADE_IN + HOLD   # when this card starts fading out
        self.out_from = 1.0            # alpha at the moment the fade-out starts
        self.out_len = FADE_OUT
        self.dead = False

    def alpha(self):
        if self.t >= self.out_at:
            return max(0.0, self.out_from * (1.0 - (self.t - self.out_at) / self.out_len))
        return max(0.0, min(1.0, self.t / FADE_IN))

    def update(self, dt):
        self.t += dt
        if self.t >= self.out_at + self.out_len:
            self.dead = True

    def dismiss(self):
        """Cross-fade out: from whatever alpha it has right now down to 0 in CROSSFADE s."""
        a = self.alpha()
        self.out_at, self.out_from, self.out_len = self.t, a, max(0.05, CROSSFADE * a)


class ZoneTracker:
    def __init__(self):
        self.place = None          # accepted place key
        self._pending = None       # (key, title, subtitle, dwell_needed)
        self._pending_t = 0.0
        self._last_shown = {}      # key -> clock time it was last announced
        self.clock = 0.0
        self.cards = []            # at most 2: [fading-out old, current]
        self.music = music.Hysteresis(MUSIC_DWELL)
        self._zone_kind = None

    # ------------------------------------------------------------ places
    def observe(self, dt, zone_kind, key, title, subtitle, music_zone=None):
        """Call every frame with the place the player is in right now.
        Returns the music zone to play (hysteresis-stabilised)."""
        self.clock += dt
        for c in self.cards:
            c.update(dt)
        self.cards = [c for c in self.cards if not c.dead]
        zone_changed = zone_kind != self._zone_kind
        if zone_changed:
            self._zone_kind = zone_kind
            self.music.reset(music_zone)   # a portal switches music right away
        if key != self.place:
            if self._pending is None or self._pending[0] != key:
                self._pending = (key, title, subtitle, ZONE_DWELL if zone_changed else DWELL)
                self._pending_t = 0.0
            else:
                self._pending_t += dt
                if self._pending_t >= self._pending[3]:
                    self._accept(*self._pending[:3])
        else:
            self._pending = None
        return self.music.update(dt, music_zone) if music_zone else self.music.value

    def _accept(self, key, title, subtitle):
        self.place = key
        self._pending = None
        last = self._last_shown.get(key)
        if last is not None and self.clock - last < REPEAT_S:
            return  # visited moments ago - don't nag
        self._last_shown[key] = self.clock
        for c in self.cards:
            c.dismiss()
        self.cards = [c for c in self.cards if not c.dead][-1:] + [Card(title, subtitle)]

    def visible(self):
        """[(title, subtitle, alpha)] oldest first."""
        return [(c.title, c.subtitle, c.alpha()) for c in self.cards if c.alpha() > 0.01]


# ------------------------------------------------------------ resolvers

def hub_place(zone):
    """zone: 'nexus' | 'bazaar' | 'vault'."""
    title, sub = {"nexus": ("Nexus", "Safe zone"), "bazaar": ("The Bazaar", "Safe zone - trade & chests"),
                  "vault": ("Your Vault", "12 chests, all yours")}[zone]
    return zone, "hub:" + zone, title, sub, zone


def dungeon_place(label, difficulty, music_zone):
    label = label or "Dungeon"
    sub = "Finale" if label == "The Forge" else "Dungeon"
    if difficulty:
        sub += f" [{difficulty}]"
    return "dungeon", "dungeon:" + label, label, sub, music_zone


def biome_near(tilemap, wx, wy, radius_tiles=6):
    """The biome under (wx, wy), or - on a road/plaza/prop/water tile - the most
    common biome in a small ring around it (None if there's none nearby)."""
    from game import world
    b = world.TILE_TO_BIOME_NAME.get(tilemap.tile_at(wx, wy))
    if b is not None:
        return b
    counts = {}
    T = world.C.TILE
    for r in range(2, radius_tiles + 1, 2):
        for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r), (r, r), (-r, -r), (r, -r), (-r, r)):
            nb = world.TILE_TO_BIOME_NAME.get(tilemap.tile_at(wx + dx * T, wy + dy * T))
            if nb is not None:
                counts[nb] = counts.get(nb, 0) + 1
        if counts:
            return max(counts, key=counts.get)
    return None


def realm_place(areas, tile_x, tile_y, biome):
    """areas: game.codex.realm_areas() dict (tile space) or None; biome: the biome
    name under the player (None on non-biome tiles - keeps the previous biome)."""
    b_title = _BIOME_TITLES.get(biome, "The Realm") if biome else "The Realm"
    if areas:
        for pl in areas.get("places") or ():
            if abs(tile_x - pl["x"]) <= pl["w"] / 2 and abs(tile_y - pl["y"]) <= pl["h"] / 2:
                sub = f"Realm - {_BIOME_TITLES.get(pl.get('biome') or biome, b_title)}"
                return ("realm", "area:" + pl["key"], pl["name"], sub,
                        music.realm_zone(pl.get("biome") or biome))
        for isl in areas.get("islands") or ():
            dx, dy = tile_x - isl["x"], tile_y - isl["y"]
            if dx * dx + dy * dy <= ISLAND_R_TILES * ISLAND_R_TILES:
                return ("realm", f"island:{isl['idx']}", isl["label"], "Island",
                        music.realm_zone(island_idx=isl["idx"]))
    if biome is None:
        return None
    return "realm", "biome:" + biome, b_title, "Realm", music.realm_zone(biome)

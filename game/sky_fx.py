"""
Night realism pass 2 - the client side of game/night_sky.py: what each client draws from the
clock_info it gets (single-player reads RealmSim.clock_info, co-op the snapshot's copy).

- Lightning: a new strike (clock "bolt" sequence number) flashes the whole screen - the night
  darkness lifts for a moment and flickers back - and draws a jagged bolt down to the strike.
- Shooting stars: a bright streak with a fading tail crossing the top of the sky; one that
  "falls" dives toward the ground.
- Frost sparkle: on snow and ice at night, the frost glints in the moonlight around you.
- Rain: rainy / stormy nights rain everywhere (except deserts, the Ashlands and the snow).
One SkyFX per client; call update() once per frame, light_boost() when drawing the darkness,
and draw() after it.
"""
import math
import random

import pygame

FLASH_DECAY = 2.2         # per second
STAR_TIME = 1.15          # seconds a shooting star is on screen
FROST_CELL = 26           # px grid for frost glints
FROST_RANGE = 320         # px around the player
NO_RAIN_WEATHER = ("snow", "sand", "ash")


class SkyFX:
    def __init__(self):
        self._bolt_seq = None
        self._star_seq = None
        self.flash = 0.0
        self._flick = 0.0
        self.bolt = None   # {"pos": (x, y), "t": secs, "pts": [...] (relative)}
        self.star = None   # {"t", "ang", "fall", "x0", "y0"}

    def update(self, dt, clock):
        clock = clock or {}
        b = clock.get("bolt")
        if "bolt" in clock:  # (None = no strike yet tonight: sequence 0)
            seq = b[0] if b else 0
            if self._bolt_seq is not None and b and seq != self._bolt_seq:
                from game import access
                calm = access.reduced_flashing()  # Options > Accessibility: no strobe, a soft glow
                self.flash, self._flick = (0.3, 0.0) if calm else (1.0, 0.16)
                rng = random.Random(b[0])
                pts, x, y = [], 0.0, 0.0
                for i in range(9):
                    pts.append((x, y))
                    x += rng.uniform(-26, 26)
                    y += rng.uniform(55, 95)
                self.bolt = {"pos": (b[1], b[2]), "t": 0.22, "pts": pts, "len": y}
            self._bolt_seq = seq
        s = clock.get("star")
        if "star" in clock:
            seq = s[0] if s else 0
            if self._star_seq is not None and s and seq != self._star_seq:
                rng = random.Random(s[0] * 7 + 3)
                self.star = {"t": 0.0, "ang": s[1], "fall": bool(s[2]), "x0": rng.uniform(0.15, 0.85),
                             "y0": rng.uniform(0.04, 0.22)}
            self._star_seq = seq
        if self._flick > 0:  # lightning flickers: a second, weaker flash right after the first
            self._flick -= dt
            if self._flick <= 0:
                self.flash = max(self.flash, 0.75)
        self.flash = max(0.0, self.flash - FLASH_DECAY * dt)
        if self.bolt is not None:
            self.bolt["t"] -= dt
            if self.bolt["t"] <= 0:
                self.bolt = None
        if self.star is not None:
            self.star["t"] += dt
            if self.star["t"] >= STAR_TIME:
                self.star = None

    def light_boost(self, light_level):
        """The light level to draw the darkness with: lightning lifts it for a moment."""
        return max(light_level, 0.92 * self.flash)

    def rain_kind(self, clock, biome_weather):
        """The weather particles to show: a rainy / stormy night rains wherever it can."""
        if (clock or {}).get("sky") in ("rain", "storm") and biome_weather not in NO_RAIN_WEATHER:
            return "rain"
        return biome_weather

    def draw(self, surf, cam):
        w, h = surf.get_size()
        if self.bolt is not None:
            sx, sy = cam(self.bolt["pos"])
            top = sy - self.bolt["len"]
            pts = [(sx + px, top + py) for (px, py) in self.bolt["pts"]] + [(sx, sy)]
            a = max(0.0, self.bolt["t"] / 0.22)
            glow = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.lines(glow, (150, 160, 255, int(120 * a)), False, pts, 9)
            pygame.draw.lines(glow, (210, 215, 255, int(200 * a)), False, pts, 4)
            pygame.draw.lines(glow, (255, 255, 255, int(255 * a)), False, pts, 2)
            surf.blit(glow, (0, 0))
        if self.flash > 0.05:  # a cold white wash on top of the lifted darkness
            wash = pygame.Surface((w, h))
            v = int(70 * self.flash)
            wash.fill((v, v, int(v * 1.1)))
            surf.blit(wash, (0, 0), special_flags=pygame.BLEND_ADD)
        if self.star is not None:
            st = self.star
            f = st["t"] / STAR_TIME
            ang = math.radians(st["ang"] + (40 * f if st["fall"] else 0))
            d = pygame.Vector2(math.cos(ang), abs(math.sin(ang)) + (0.6 * f if st["fall"] else 0.15))
            d = d.normalize() * (1 if st["ang"] >= 0 else 1)
            if st["ang"] < 0:
                d.x = -d.x
            head = pygame.Vector2(st["x0"] * w, st["y0"] * h) + d * (w * 0.55 * f)
            fade = math.sin(math.pi * min(1.0, f * 1.05))
            n, tail = 18, 260
            layer = pygame.Surface((w, h), pygame.SRCALPHA)
            for i in range(n):  # a soft blue glow under a white-hot core, both fading down the tail
                k = i / n
                p0 = head - d * (k * tail)
                p1 = head - d * ((k + 1 / n) * tail)
                a = int(255 * (1 - k) ** 1.4 * fade)
                pygame.draw.line(layer, (150, 180, 255, a // 3), p0, p1, max(1, int(9 * (1 - k))))
                pygame.draw.line(layer, (235, 240, 255, a), p0, p1, max(1, int(4 * (1 - k))))
            for r, a in ((9, 18), (5, 40), (3, 110)):  # a small soft halo (BLEND_ADD stacks them)
                pygame.draw.circle(layer, (200, 215, 255, int(a * fade)), head, r)
            pygame.draw.circle(layer, (255, 255, 245, int(230 * fade)), head, 1)
            surf.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)

    @staticmethod
    def draw_frost_sparkle(surf, cam, player_pos, tile_at, frost_tiles, light_level):
        """Frost glinting on snow and ice around you at night (drawn after the darkness)."""
        dark = 1.0 - light_level
        if dark < 0.3:
            return
        t = pygame.time.get_ticks() / 1000.0
        px, py = player_pos
        c0x, c0y = int((px - FROST_RANGE) // FROST_CELL), int((py - FROST_RANGE) // FROST_CELL)
        c1x, c1y = int((px + FROST_RANGE) // FROST_CELL), int((py + FROST_RANGE) // FROST_CELL)
        for cy in range(c0y, c1y + 1):
            for cx in range(c0x, c1x + 1):
                hsh = (cx * 73856093 ^ cy * 19349663) & 0xFFFF
                if hsh % 5:
                    continue
                wx = cx * FROST_CELL + (hsh >> 4) % FROST_CELL
                wy = cy * FROST_CELL + (hsh >> 8) % FROST_CELL
                if (wx - px) ** 2 + (wy - py) ** 2 > FROST_RANGE ** 2:
                    continue
                tw = math.sin(t * (1.6 + (hsh % 7) * 0.35) + hsh)
                if tw < 0.86:
                    continue
                if tile_at(wx, wy) not in frost_tiles:
                    continue
                b = (tw - 0.86) / 0.14 * dark
                sx, sy = cam((wx, wy))
                c = (int(200 * b), int(225 * b), int(255 * b))
                r = 2 + (hsh % 3 == 0)
                pygame.draw.line(surf, c, (sx - r, sy), (sx + r, sy))
                pygame.draw.line(surf, c, (sx, sy - r), (sx, sy + r))
                surf.set_at((int(sx), int(sy)), (min(255, c[0] + 55), min(255, c[1] + 30), 255))

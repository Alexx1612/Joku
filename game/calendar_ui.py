"""
The in-game Calendar (K, or Options > Journal > Calendar): the coming nights - when each falls,
the moon's phase, whether it's a BLOOD MOON, the weather and the night's event - plus the
live-event schedule (Double Loot, Happy Hour, Blood Moon Week...).

The nights come from RealmSim.forecast_view() (riding in clock_info["forecast"], so co-op
clients show the server's calendar); the live events from game.live_events.upcoming(), the same
fixed real-time schedule every process agrees on.

The window (CalendarWindow) is fully opaque, framed like the other dock windows, dragged by its
title bar (position saved with the other panels in settings.panel_offsets["calendar"] via
game/panel_drag.py) and explains what everything does: hover or click a row and the detail
card on the right spells out that night's event, weather and moon, or that live event. The
explanations are built from the game's own constants (like game/codex_extra.py), so they can't
drift from what the game does. Filter chips (Nights / Blood Moons only / Live events) are
remembered in settings.calendar_filter.
"""
import math
import time

import pygame

from game import constants as C

W, H = 960, 640
ROW_H = 38
LIVE_ROW_H = 22
TITLE_H = 40
LEFT_W = 628          # the nights table + live list; the detail card fills the rest
WEATHER_LABEL = {"clear": "Clear", "cloudy": "Cloudy", "rain": "Rain", "storm": "Storm"}
EVENT_HINT = {
    "fog": "light shrinks, stalkers x2",
    "hunter": "a Stalker hunts one of you",
    "lanterns_out": "every lamp is dark",
    "market": "the Ghost Merchant trades",
    "lamplighter": "guard Old Wick: Light of RDV",
    "blood_moon": "hordes, Red Harvester, loot!",
}
FILTERS = (("nights", "Nights"), ("blood", "Blood Moons only"), ("live", "Live events"))
BG = (18, 17, 25)
GOLD = (196, 160, 90)
_FONTS = {}


def _font(size, bold=False):
    k = (size, bold)
    if k not in _FONTS:
        _FONTS[k] = pygame.font.SysFont("consolas", size, bold=bold)
    return _FONTS[k]


def fmt_eta(s):
    s = max(0, int(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}:{sec:02d}"


# ------------------------------------------------------------ explanations --
def event_text(key):
    """What a night event does, with the game's real numbers."""
    from game import night as nm, realm_sim as rs, items
    if key == "fog":
        return (f"The Fog: your light shrinks to x{nm.FOG_LIGHT_MULT} of its size, and Shade Stalkers (invisible "
                "outside any light) come out twice as often. Stay near lamps and keep moving.")
    if key == "hunter":
        return (f"Something Is Hunting: a Shade Stalker with x{nm.HUNTER_HP_MULT} HP picks ONE player and tracks "
                "them until dawn. Kill it and it drops boss-grade loot. Shelter (a house with every door shut) "
                "hides you from it.")
    if key == "lanterns_out":
        return ("The Lanterns Go Out: every lamp post and every window in the Realm is dark tonight, and "
                "Lantern-Eaters come out twice as often. Your own light, campfires and fallen stars still work.")
    if key == "market":
        return ("Midnight Market: the Ghost Merchant opens shop in one of the named areas (the feed says where). "
                "He takes your 3 lowest-tier gear items and gives 1 mystery item a tier higher than the best of "
                "them. Gone at dawn.")
    if key == "lamplighter":
        return (f"The Lamplighter: Old Wick ({nm.LAMPLIGHTER_HP} HP) lights lamps in a named area and the dark "
                f"sends a wave at him every {int(nm.LAMPLIGHTER_WAVE_EVERY)} s. Keep him alive until dawn: "
                f"everyone who came within {int(nm.LAMPLIGHTER_HELP_RADIUS)} px gets the Light of RDV (monsters "
                "near its wearer lose their nerve).")
    if key == "blood_moon":
        return (f"BLOOD MOON: the night goes red and runs x{rs.BLOOD_MOON_NIGHT_SPEED} faster. Every "
                f"{int(nm.BLOOD_HORDE_EVERY)} s a horde of {nm.BLOOD_HORDE_SIZE[0]}-{nm.BLOOD_HORDE_SIZE[1]} "
                "moonlit monsters closes in on everyone who isn't sheltered, and halfway through THE RED "
                f"HARVESTER rises. Kills roll the best night loot (Weapon Shards "
                f"x{items.RUNE_SOURCE_MULT['blood_moon']}). Survive to dawn: +{nm.BLOOD_SURVIVOR_XP} XP.")
    return "A quiet night. Nothing special planned - which is exactly what something special would say."


def weather_text(kind):
    from game import night_sky as ns
    if kind == "clear":
        return (f"Clear: the moon lights the night and shooting stars cross the sky ({int(ns.STAR_CHANCE * 100)}% "
                f"every {int(ns.STAR_EVERY)} s; ~{int(ns.STAR_FALL_CHANCE * 100)}% of them land as a Star "
                "Fragment you can pick up for bonus loot).")
    if kind == "cloudy":
        return f"Cloudy: the moon is hidden; the night is x{ns.CLOUD_DARK['cloudy']} as bright."
    if kind == "rain":
        return (f"Rain: x{ns.CLOUD_DARK['rain']} as bright, and every light reaches only "
                f"x{ns.WEATHER_LIGHT_MULT['rain']} as far.")
    if kind == "storm":
        return (f"Storm: rain (x{ns.CLOUD_DARK['storm']} as bright, lights x{ns.WEATHER_LIGHT_MULT['storm']}) plus "
                f"lightning every {int(ns.LIGHTNING_EVERY[0])}-{int(ns.LIGHTNING_EVERY[1])} s - each strike lights "
                "the whole screen for a moment. Look around!")
    return f"{WEATHER_LABEL.get(kind, kind)}."


def moon_text(phase):
    from game import realm_sim as rs
    name = rs.MOON_PHASES[phase]
    if phase == 4:
        return (f"{name}: the brightest night, and a Blood Moon is x{rs.FULL_MOON_BLOOD_MULT} as likely. "
                "Clouds still hide it.")
    if phase == 0:
        return f"{name}: no moonlight at all - the darkest night of the cycle."
    lit = 1.0 - abs(4 - phase) / 4.0
    return f"{name}: about {int(round(lit * 100))}% lit. The moon moves one phase a night (8 in all)."


def live_text(key):
    """What a live event does, read from live_events.EVENTS."""
    from game import live_events
    if key not in live_events.EVENTS:
        return "No live event in this slot - the Realm's normal rates."
    d = live_events.EVENTS[key]
    bits = []
    if d.get("loot_rolls", 1.0) != 1.0:
        bits.append(f"every kill rolls loot x{d['loot_rolls']:g}")
    if d.get("xp", 1.0) != 1.0:
        bits.append(f"+{int(round((d['xp'] - 1) * 100))}% XP")
    if d.get("blood_moon_chance", 1.0) != 1.0:
        bits.append(f"Blood Moon chance x{d['blood_moon_chance']:g}")
    return (f"{d['label']}: " + ", ".join(bits) + f". Each slot lasts {live_events.EVENT_WINDOW // 60} minutes "
            "of real time, on the same schedule for everyone.")


# ------------------------------------------------------------------ icons --
def _moon(surf, cx, cy, r, phase, blood, bg=BG):
    dark = (52, 56, 74)
    pygame.draw.circle(surf, dark, (cx, cy), r)
    lit = 1.0 - abs(4 - phase) / 4.0
    if lit > 0.02:
        pygame.draw.circle(surf, (235, 70, 70) if blood else (236, 240, 252), (cx, cy), r)
        if lit < 0.98:
            off = int(round(2 * r * lit)) * (1 if phase < 4 else -1)
            pygame.draw.circle(surf, dark, (cx - off, cy), r)
    pygame.draw.circle(surf, (150, 155, 180), (cx, cy), r, 1)


def _weather_icon(surf, x, y, kind):
    if kind == "clear":
        for i in range(8):
            a = i * math.pi / 4
            pygame.draw.line(surf, (210, 220, 255), (x + 9 + 4 * math.cos(a), y + 9 + 4 * math.sin(a)),
                             (x + 9 + 8 * math.cos(a), y + 9 + 8 * math.sin(a)), 1)
        pygame.draw.circle(surf, (235, 238, 255), (x + 9, y + 9), 3)
        return
    cloud = (175, 180, 200) if kind == "cloudy" else (135, 140, 165)
    for (dx, dy, r) in ((5, 8, 5), (11, 6, 6), (15, 9, 4)):
        pygame.draw.circle(surf, cloud, (x + dx, y + dy), r)
    pygame.draw.rect(surf, cloud, (x + 2, y + 9, 16, 4))
    if kind in ("rain", "storm"):
        for dx in (4, 9, 14):
            pygame.draw.line(surf, (130, 185, 255), (x + dx, y + 15), (x + dx - 2, y + 20), 2)
    if kind == "storm":
        pygame.draw.lines(surf, (255, 240, 120), False, [(x + 11, y + 12), (x + 8, y + 17), (x + 12, y + 17),
                                                         (x + 9, y + 23)], 2)


def _event_icon(surf, cx, cy, key, blood=False):
    """A small badge per night event (so the list reads at a glance, not by colour alone)."""
    col = (255, 90, 90) if blood or key == "blood_moon" else {
        "fog": (175, 185, 205), "hunter": (210, 120, 255), "lanterns_out": (255, 170, 90),
        "market": (140, 230, 210), "lamplighter": (255, 214, 120)}.get(key, (160, 160, 175))
    pygame.draw.circle(surf, (30, 28, 40), (cx, cy), 9)
    pygame.draw.circle(surf, col, (cx, cy), 9, 1)
    if key == "fog":
        for dy in (-3, 0, 3):
            pygame.draw.line(surf, col, (cx - 5, cy + dy), (cx + 5, cy + dy), 1)
    elif key == "hunter":
        pygame.draw.circle(surf, col, (cx, cy), 4, 1)
        pygame.draw.circle(surf, col, (cx, cy), 1)
    elif key == "lanterns_out":
        pygame.draw.rect(surf, col, (cx - 3, cy - 4, 6, 8), 1)
        pygame.draw.line(surf, col, (cx - 5, cy + 5), (cx + 5, cy - 5), 1)
    elif key == "market":
        pygame.draw.circle(surf, col, (cx, cy), 4)
        pygame.draw.line(surf, (30, 28, 40), (cx, cy - 3), (cx, cy + 3), 1)
    elif key == "lamplighter":
        pygame.draw.polygon(surf, col, [(cx, cy - 6), (cx + 3, cy + 1), (cx, cy + 5), (cx - 3, cy + 1)])
    elif key == "blood_moon" or blood:
        pygame.draw.circle(surf, col, (cx, cy), 5)
    else:
        pygame.draw.circle(surf, col, (cx, cy), 2)


# ----------------------------------------------------------------- window --
def base_rect():
    """Where the window sits before any drag: centred over the play area, clamped to the screen."""
    from game import ui
    play_w = ui._panel_block_x0()
    w, h = min(W, C.SCREEN_W - 20), min(H, C.SCREEN_H - 20)
    return pygame.Rect(max(10, min(C.SCREEN_W - w - 10, play_w // 2 - w // 2)), max(10, C.SCREEN_H // 2 - h // 2), w, h)


def rect():
    """The window's screen rect (dragged offset applied, kept on-screen)."""
    from game import ui
    return ui._offset_rect("calendar", base_rect())


def title_rect(r=None):
    r = r or rect()
    return pygame.Rect(r.x, r.y, r.w - 44, TITLE_H)


def close_rect(r=None):
    r = r or rect()
    return pygame.Rect(r.right - 36, r.y + 8, 26, 24)


def chip_rects(r=None):
    r = r or rect()
    f = _font(13, True)
    out, x = [], r.x + 16
    for key, label in FILTERS:
        w = f.size(label)[0] + 30
        out.append((key, pygame.Rect(x, r.y + TITLE_H + 10, w, 24)))
        x += w + 6
    return out


class CalendarWindow:
    """One per client: open state, the selected row, the filter chips, the hovered row."""

    def __init__(self):
        from game import settings
        self.open = False
        self.sel = ("night", 0)  # ("night", i) / ("live", i)
        self.hover = None
        self.filter = {k for k in settings.get("calendar_filter") if k in dict(FILTERS)}

    def toggle(self):
        self.open = not self.open

    def close(self):
        self.open = False

    def toggle_filter(self, key):
        from game import settings
        self.filter ^= {key}
        if key == "blood" and "blood" in self.filter:
            self.filter.add("nights")  # "Blood Moons only" narrows the nights - it needs them shown
        if key == "nights" and "nights" not in self.filter:
            self.filter.discard("blood")
        settings.change("calendar_filter", sorted(self.filter))

    # -- layout (screen coords), shared by draw and the hit-tests --
    def rows(self, clock, now=None, r=None):
        """[(("night", i) | ("live", i), rect)] for every visible row."""
        from game import live_events
        r = r or rect()
        now = time.time() if now is None else now
        out = []
        y = r.y + TITLE_H + 10 + 24 + 12 + 26 + 22  # chips, the "now" line, the column heads
        fc = (clock or {}).get("forecast") or []
        if "nights" in self.filter:
            for i, f in enumerate(fc):
                if "blood" in self.filter and not f[3]:
                    continue
                out.append((("night", i), pygame.Rect(r.x + 10, y, LEFT_W - 10, ROW_H - 4)))
                y += ROW_H
            if not fc or ("blood" in self.filter and not any(f[3] for f in fc)):
                y += ROW_H
        if "live" in self.filter:
            y += 34
            for i, _slot in enumerate(live_events.upcoming(5, now)):
                out.append((("live", i), pygame.Rect(r.x + 10, y, LEFT_W - 10, LIVE_ROW_H - 2)))
                y += LIVE_ROW_H
        return out

    def handle_event(self, event, panel_drag, clock=None):
        """True if the event belonged to the open window. Only its own keys (Esc, Up/Down) are
        swallowed - WASD still walks you around with the calendar up."""
        if not self.open:
            return False
        r = rect()
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
                return True
            if event.key in (pygame.K_UP, pygame.K_DOWN):
                keys = [k for k, _r in self.rows(clock, r=r)]
                if keys:
                    i = keys.index(self.sel) if self.sel in keys else 0
                    self.sel = keys[max(0, min(len(keys) - 1, i + (1 if event.key == pygame.K_DOWN else -1)))]
                return True
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and r.collidepoint(event.pos):
            if close_rect(r).collidepoint(event.pos):
                self.close()
            elif title_rect(r).collidepoint(event.pos):
                panel_drag.down("calendar", event.pos)
            else:
                for key, cr in chip_rects(r):
                    if cr.collidepoint(event.pos):
                        self.toggle_filter(key)
                        return True
                for key, rr in self.rows(clock, r=r):
                    if rr.collidepoint(event.pos):
                        self.sel = key
                        break
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (3, 4, 5) and r.collidepoint(event.pos):
            return True
        if event.type == pygame.MOUSEMOTION:
            self.hover = next((k for k, rr in self.rows(clock, r=r) if rr.collidepoint(event.pos)), None)
            if panel_drag.name == "calendar":
                panel_drag.motion(event.pos)
                return True
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and panel_drag.name == "calendar":
            panel_drag.up()
            return True
        if event.type == pygame.MOUSEWHEEL and r.collidepoint(pygame.mouse.get_pos()):
            return True
        return False

    # -- drawing --
    def draw(self, surf, clock, mouse=(-1, -1), now=None):
        from game import live_events, realm_sim, ui
        now = time.time() if now is None else now
        r = rect()
        # solid backing first: _ornate_panel's rounded corners are transparent, nothing may show through
        pygame.draw.rect(surf, (8, 8, 12), r, border_radius=8)
        panel, _ = ui._ornate_panel(r.w, r.h)
        surf.blit(panel, r.topleft)
        # title bar: drag grip + title + close X
        tb = title_rect(r)
        bar = pygame.Rect(r.x + 3, r.y + 3, r.w - 6, TITLE_H - 3)
        pygame.draw.rect(surf, (48, 40, 28), bar, border_top_left_radius=6, border_top_right_radius=6)
        pygame.draw.line(surf, ui.CHROME_GOLD, (r.x + 3, r.y + TITLE_H), (r.right - 4, r.y + TITLE_H))
        for gx in range(3):
            for gy in range(3):
                pygame.draw.circle(surf, (150, 130, 90), (r.x + 16 + gx * 5, r.y + 14 + gy * 5), 1)
        surf.blit(_font(22, True).render("Calendar", True, (240, 228, 200)), (r.x + 34, r.y + 8))
        hint = _font(12).render("drag the title bar to move - K / Esc closes", True,
                                (205, 190, 150) if tb.collidepoint(mouse) else (150, 140, 120))
        surf.blit(hint, (close_rect(r).x - hint.get_width() - 12, r.y + 14))
        cr = close_rect(r)
        ui._bevel_button(surf, cr, (140, 55, 55), hovered=cr.collidepoint(mouse))
        x_t = ui._FONT_S.render("X", True, (255, 225, 225))
        surf.blit(x_t, (cr.centerx - x_t.get_width() // 2, cr.centery - x_t.get_height() // 2))
        # filter chips
        for key, chip in chip_rects(r):
            on = key in self.filter
            pygame.draw.rect(surf, (88, 72, 42) if on else ((40, 38, 50) if chip.collidepoint(mouse) else (28, 27, 36)),
                             chip, border_radius=12)
            pygame.draw.rect(surf, ui.CHROME_GOLD if on else (90, 86, 100), chip, 1, border_radius=12)
            box = pygame.Rect(chip.x + 8, chip.centery - 5, 10, 10)
            pygame.draw.rect(surf, (230, 210, 150) if on else (110, 106, 120), box, 1)
            if on:
                pygame.draw.lines(surf, (255, 235, 170), False, [(box.x + 2, box.y + 5), (box.x + 4, box.bottom - 2),
                                                                (box.right - 2, box.y + 2)], 2)
            t = _font(13, True).render(dict(FILTERS)[key], True, (255, 245, 220) if on else (170, 168, 182))
            surf.blit(t, (chip.x + 22, chip.centery - t.get_height() // 2))
        y = r.y + TITLE_H + 10 + 24 + 12
        fc = (clock or {}).get("forecast")
        if not fc:
            now_txt, now_col = "The sky can only be read out in the Realm.", (190, 190, 205)
        elif clock.get("until") == "dawn":
            now_txt = (f"Now: night {clock.get('night_no', 0)} - " + ("BLOOD MOON" if clock.get("blood") else "night")
                       + f" - dawn in {fmt_eta(clock['left'])}")
            now_col = (240, 95, 95) if clock.get("blood") else (220, 215, 190)
        else:
            now_txt, now_col = f"Now: day - night #{fc[0][0]} falls in {fmt_eta(clock['left'])}", (220, 215, 190)
        surf.blit(_font(15, True).render(now_txt, True, now_col), (r.x + 18, y))
        y += 26
        cols = (r.x + 18, r.x + 88, r.x + 164, r.x + 304, r.x + 384)
        rows = self.rows(clock, now, r)
        focus = self.hover or self.sel
        keys = [k for k, _rr in rows]
        if focus not in keys:
            focus = keys[0] if keys else None
            if self.hover is None:
                self.sel = focus or self.sel
        if "nights" in self.filter:
            for x, head in zip(cols, ("Night", "Falls in", "Moon", "Sky", "Event")):
                surf.blit(_font(13, True).render(head, True, GOLD), (x, y))
            pygame.draw.line(surf, (90, 78, 54), (r.x + 14, y + 19), (r.x + LEFT_W, y + 19))
            if fc and "blood" in self.filter and not any(f[3] for f in fc):
                surf.blit(_font(14).render(f"No Blood Moon in the next {len(fc)} nights. Phew?", True,
                                           (190, 180, 180)), (r.x + 18, y + 32))
        for key, rr in rows:
            if key[0] != "night":
                continue
            n, eta, phase, blood, weather, event = fc[key[1]]
            on = key == focus
            if blood:
                pygame.draw.rect(surf, (96, 18, 22), rr, border_radius=4)
                pygame.draw.rect(surf, (230, 70, 70), rr, 1, border_radius=4)
            elif on:
                pygame.draw.rect(surf, (52, 48, 72), rr, border_radius=4)
            elif key[1] % 2 == 0:
                pygame.draw.rect(surf, (28, 27, 37), rr, border_radius=4)
            if on:
                pygame.draw.rect(surf, (255, 225, 150), rr, 2, border_radius=4)
            cy = rr.centery
            txt_col = (255, 215, 215) if blood else (232, 232, 240)
            label = "Tonight" if key[1] == 0 and clock.get("until") == "night" else f"#{n}"
            surf.blit(_font(15, True).render(label, True, txt_col), (cols[0], cy - 9))
            surf.blit(_font(15).render(fmt_eta(eta), True, txt_col), (cols[1], cy - 9))
            _moon(surf, cols[2] + 9, cy, 8, phase, bool(blood))
            surf.blit(_font(13).render(realm_sim.MOON_PHASES[phase], True, txt_col), (cols[2] + 24, cy - 8))
            _weather_icon(surf, cols[3], cy - 12, weather)
            surf.blit(_font(13).render(WEATHER_LABEL.get(weather, weather), True, txt_col), (cols[3] + 24, cy - 8))
            _event_icon(surf, cols[4] + 9, cy, event, bool(blood))
            old_clip = surf.get_clip()
            surf.set_clip(rr.clip(old_clip))
            ev_label = realm_sim.NIGHT_EVENT_LABELS.get(event, event or "-")
            surf.blit(_font(14, True).render(ev_label, True, (255, 110, 110) if blood else (245, 220, 155)),
                      (cols[4] + 24, cy - 15))
            surf.blit(_font(12).render(EVENT_HINT.get(event, ""), True, (205, 185, 185) if blood else (175, 168, 160)),
                      (cols[4] + 24, cy + 2))
            surf.set_clip(old_clip)
        live_rows = [(k, rr) for k, rr in rows if k[0] == "live"]
        slots = live_events.upcoming(5, now)
        if "live" in self.filter:
            night_bottom = max([rr.bottom for k, rr in rows if k[0] == "night"] or [y + 24])
            ly = (live_rows[0][1].y - 30) if live_rows else night_bottom + 8
            pygame.draw.line(surf, (90, 78, 54), (r.x + 14, ly), (r.x + LEFT_W, ly))
            surf.blit(_font(15, True).render("Live events", True, GOLD), (r.x + 18, ly + 6))
            if not slots:
                surf.blit(_font(13).render("The live-event rotation is off on this game.", True, (170, 170, 185)),
                          (r.x + 18, ly + 30))
        for key, rr in live_rows:
            ev, start, end = slots[key[1]]
            on = key == focus
            if on:
                pygame.draw.rect(surf, (52, 48, 72), rr, border_radius=3)
                pygame.draw.rect(surf, (255, 225, 150), rr, 1, border_radius=3)
            name = live_events.label_for(ev) or "No event"
            if key[1] == 0:
                when = f"now - ends in {fmt_eta(end - now)}" if end else "now (fixed)"
            else:
                when = f"starts in {fmt_eta(start - now)}"
            col = (150, 235, 165) if ev and key[1] == 0 else (232, 232, 240) if ev else (140, 140, 155)
            nm_t = _font(14, key[1] == 0).render(name, True, col)
            while nm_t.get_width() > 380 and len(name) > 6:
                name = name[:-2]
                nm_t = _font(14, key[1] == 0).render(name.rstrip() + ".", True, col)
            surf.blit(nm_t, (rr.x + 8, rr.y + 2))
            wt = _font(13).render(when, True, (180, 180, 195))
            surf.blit(wt, (rr.right - wt.get_width() - 8, rr.y + 3))
        self._draw_detail(surf, r, focus, fc, slots, clock, now)
        foot = _font(12).render("Hover or click a row for what it does.  The Realm keeps to its schedule - "
                                "what you see is what you get.", True, (150, 148, 160))
        if foot.get_width() > r.w - 28:
            foot = _font(12).render("Hover or click a row for what it does.", True, (150, 148, 160))
        surf.blit(foot, (r.x + 18, r.bottom - 24))

    def _draw_detail(self, surf, r, focus, fc, slots, clock, now):
        from game import realm_sim, ui
        card = pygame.Rect(r.x + LEFT_W + 14, r.y + TITLE_H + 10, r.right - (r.x + LEFT_W + 14) - 14,
                           r.h - TITLE_H - 10 - 36)
        if card.w < 120:
            return
        pygame.draw.rect(surf, (30, 28, 38), card, border_radius=6)
        pygame.draw.rect(surf, ui.CHROME_GOLD_DIM, card, 1, border_radius=6)
        x, y, w = card.x + 12, card.y + 10, card.w - 24
        fs = _font(13)

        def head(text, col=(245, 215, 130)):
            nonlocal y
            surf.blit(_font(15, True).render(text, True, col), (x, y))
            y += 22

        def para(text, col=(222, 220, 230)):
            nonlocal y
            for line in ui._wrap_text(text, fs, w):
                if y > card.bottom - 70:
                    return
                surf.blit(fs.render(line, True, col), (x, y))
                y += fs.get_height() + 2
            y += 8

        if focus is None:
            head("Nothing to show")
            para("Turn a filter chip back on (top left).")
        elif focus[0] == "night" and fc and focus[1] < len(fc):
            n, eta, phase, blood, weather, event = fc[focus[1]]
            head(("Tonight" if focus[1] == 0 and clock.get("until") == "night" else f"Night #{n}")
                 + f" - falls in {fmt_eta(eta)}", (255, 120, 120) if blood else (245, 215, 130))
            _event_icon(surf, x + 9, y + 8, event, bool(blood))
            surf.blit(_font(14, True).render(realm_sim.NIGHT_EVENT_LABELS.get(event, event or "-"), True,
                                             (255, 110, 110) if blood else (240, 220, 160)), (x + 24, y))
            y += 22
            para(event_text(event))
            _weather_icon(surf, x, y - 2, weather)
            surf.blit(_font(14, True).render("Sky: " + WEATHER_LABEL.get(weather, weather), True, (200, 215, 255)),
                      (x + 24, y))
            y += 22
            para(weather_text(weather) if not blood else "A Blood Moon is always clear - and red.")
            _moon(surf, x + 9, y + 8, 8, phase, bool(blood))
            surf.blit(_font(14, True).render("Moon: " + realm_sim.MOON_PHASES[phase], True, (225, 228, 245)),
                      (x + 24, y))
            y += 22
            para(moon_text(phase))
        elif focus[0] == "live" and focus[1] < len(slots):
            ev, start, end = slots[focus[1]]
            if focus[1] == 0:
                when = f"Running now - ends in {fmt_eta(end - now)}" if end else "Running now (fixed by the server)"
            else:
                when = f"Starts in {fmt_eta(start - now)}"
            head("Live event")
            para(when, (170, 230, 180))
            para(live_text(ev))
        # legend (three short lines so it never runs past the card)
        ly = card.bottom - 76
        pygame.draw.line(surf, (70, 64, 50), (card.x + 8, ly - 6), (card.right - 8, ly - 6))
        surf.blit(_font(12, True).render("Legend", True, GOLD), (x, ly))
        lab = (190, 188, 200)
        ly += 18
        _moon(surf, x + 7, ly + 7, 6, 4, False)
        _moon(surf, x + 23, ly + 7, 6, 4, True)
        surf.blit(_font(12).render("moon / blood moon", True, lab), (x + 138, ly))
        ly += 18
        for i, kind in enumerate(("clear", "cloudy", "rain", "storm")):
            _weather_icon(surf, x + i * 24, ly - 3, kind)
        surf.blit(_font(12).render("weather", True, lab), (x + 138, ly + 2))
        ly += 22
        for i, ev in enumerate(("fog", "hunter", "lanterns_out", "market", "lamplighter", "blood_moon")):
            _event_icon(surf, x + 9 + i * 21, ly + 7, ev)
        surf.blit(_font(12).render("night events", True, lab), (x + 138, ly + 1))


_DEFAULT = None


def draw(surf, clock, now=None, window=None, mouse=(-1, -1)):
    """Draws the calendar window (a fresh default one if none is given - tests use this).
    clock = RealmSim.clock_info() (or the co-op snapshot's copy) or None."""
    global _DEFAULT
    if window is None:
        if _DEFAULT is None:
            _DEFAULT = CalendarWindow()
        window = _DEFAULT
    window.draw(surf, clock, mouse, now)

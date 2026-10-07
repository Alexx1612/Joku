"""
The in-game Calendar (K): the coming nights - when each falls, the moon's phase, whether it's
a BLOOD MOON, the weather and the night's event - plus the live-event schedule (Double Loot,
Happy Hour, Blood Moon Week...). The nights come from RealmSim.forecast_view() (riding in
clock_info["forecast"], so co-op clients show the server's calendar); the live events from
game.live_events.upcoming(), the same fixed real-time schedule every process agrees on.
"""
import math
import time

import pygame

from game import constants as C

W, H = 760, 560
ROW_H = 40
WEATHER_LABEL = {"clear": "Clear", "cloudy": "Cloudy", "rain": "Rain", "storm": "Storm"}
EVENT_HINT = {
    "fog": "light shrinks, stalkers x2",
    "hunter": "a Stalker hunts one of you",
    "lanterns_out": "every lamp is dark",
    "market": "the Ghost Merchant trades",
    "lamplighter": "protect Old Wick -> Light of RDV",
    "blood_moon": "hordes, the Red Harvester, best loot",
}
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


def _moon(surf, cx, cy, r, phase, blood):
    pygame.draw.circle(surf, (40, 44, 60), (cx, cy), r)
    lit = 1.0 - abs(4 - phase) / 4.0
    if lit > 0.02:
        pygame.draw.circle(surf, (235, 70, 70) if blood else (232, 236, 250), (cx, cy), r)
        if lit < 0.98:
            off = int(round(2 * r * lit)) * (1 if phase < 4 else -1)
            pygame.draw.circle(surf, (40, 44, 60), (cx - off, cy), r)
    pygame.draw.circle(surf, (90, 95, 120), (cx, cy), r, 1)


def _weather_icon(surf, x, y, kind):
    if kind == "clear":
        for i in range(8):
            a = i * math.pi / 4
            pygame.draw.line(surf, (200, 210, 255), (x + 9 + 4 * math.cos(a), y + 9 + 4 * math.sin(a)),
                             (x + 9 + 8 * math.cos(a), y + 9 + 8 * math.sin(a)), 1)
        pygame.draw.circle(surf, (225, 230, 255), (x + 9, y + 9), 3)
        return
    cloud = (150, 155, 175) if kind == "cloudy" else (110, 115, 140)
    for (dx, dy, r) in ((5, 8, 5), (11, 6, 6), (15, 9, 4)):
        pygame.draw.circle(surf, cloud, (x + dx, y + dy), r)
    pygame.draw.rect(surf, cloud, (x + 2, y + 9, 16, 4))
    if kind in ("rain", "storm"):
        for dx in (4, 9, 14):
            pygame.draw.line(surf, (120, 170, 255), (x + dx, y + 15), (x + dx - 2, y + 20), 1)
    if kind == "storm":
        pygame.draw.lines(surf, (255, 240, 120), False, [(x + 11, y + 12), (x + 8, y + 17), (x + 12, y + 17),
                                                         (x + 9, y + 23)], 2)


def rect():
    from game import ui
    play_w = ui._panel_block_x0()
    return pygame.Rect(max(10, play_w // 2 - W // 2), max(10, C.SCREEN_H // 2 - H // 2), min(W, play_w - 20), H)


def draw(surf, clock, now=None):
    """The calendar window. clock = RealmSim.clock_info() (or the co-op snapshot's copy) or None."""
    from game import live_events, realm_sim
    now = time.time() if now is None else now
    r = rect()
    panel = pygame.Surface(r.size, pygame.SRCALPHA)
    panel.fill((14, 14, 22, 238))
    gold = (196, 160, 90)
    pygame.draw.rect(panel, gold, panel.get_rect(), 2, border_radius=6)
    title = _font(22, True).render("Calendar", True, (240, 228, 200))
    panel.blit(title, (18, 12))
    hint = _font(13).render("K or Esc to close", True, (150, 150, 165))
    panel.blit(hint, (r.w - hint.get_width() - 16, 18))
    y = 46
    fc = (clock or {}).get("forecast")
    if not fc:
        msg = _font(15).render("The sky can only be read out in the Realm.", True, (190, 190, 205))
        panel.blit(msg, (18, y + 6))
        y += 40
    else:
        now_txt = (f"Night {clock.get('night_no', 0)} - " +
                   ("BLOOD MOON" if clock.get("blood") else "night") + f", dawn in {fmt_eta(clock['left'])}"
                   if clock.get("until") == "dawn" else
                   f"Day - night {fc[0][0]} falls in {fmt_eta(clock['left'])}")
        panel.blit(_font(15, True).render(now_txt, True, (235, 90, 90) if clock.get("blood") else (220, 215, 190)),
                   (18, y))
        y += 28
        cols = (18, 108, 210, 400, 500)
        for x, head in zip(cols, ("Night", "Falls in", "Moon", "Sky", "Event")):
            panel.blit(_font(13, True).render(head, True, gold), (x, y))
        y += 20
        pygame.draw.line(panel, (80, 70, 50), (14, y), (r.w - 14, y))
        y += 4
        for i, (n, eta, phase, blood, weather, event) in enumerate(fc):
            row = pygame.Rect(10, y, r.w - 20, ROW_H - 4)
            if blood:
                pygame.draw.rect(panel, (90, 14, 18, 200), row, border_radius=4)
                pygame.draw.rect(panel, (220, 60, 60), row, 1, border_radius=4)
            elif i % 2 == 0:
                pygame.draw.rect(panel, (255, 255, 255, 10), row, border_radius=4)
            cy = y + (ROW_H - 4) // 2
            txt_col = (255, 210, 210) if blood else (225, 225, 235)
            label = "Tonight" if i == 0 and clock.get("until") == "night" else f"#{n}"
            panel.blit(_font(15, True).render(label, True, txt_col), (cols[0], cy - 9))
            panel.blit(_font(15).render(fmt_eta(eta), True, txt_col), (cols[1], cy - 9))
            _moon(panel, cols[2] + 9, cy, 8, phase, bool(blood))
            panel.blit(_font(13).render(realm_sim.MOON_PHASES[phase], True, txt_col), (cols[2] + 24, cy - 8))
            _weather_icon(panel, cols[3], cy - 12, weather)
            panel.blit(_font(13).render(WEATHER_LABEL.get(weather, weather), True, txt_col), (cols[3] + 24, cy - 8))
            ev_label = realm_sim.NIGHT_EVENT_LABELS.get(event, event or "-")
            panel.blit(_font(14, True).render(ev_label, True, (255, 90, 90) if blood else (240, 215, 150)),
                       (cols[4], cy - 15))
            panel.blit(_font(12).render(EVENT_HINT.get(event, ""), True, (170, 160, 150)), (cols[4], cy + 2))
            y += ROW_H
    # live events
    y += 8
    pygame.draw.line(panel, (80, 70, 50), (14, y), (r.w - 14, y))
    y += 8
    panel.blit(_font(15, True).render("Live events", True, gold), (18, y))
    y += 24
    slots = live_events.upcoming(5, now)
    if not slots:
        panel.blit(_font(13).render("The live-event rotation is off on this game.", True, (170, 170, 185)), (18, y))
    for i, (key, start, end) in enumerate(slots):
        name = live_events.label_for(key) or "No event"
        if i == 0:
            when = f"now - ends in {fmt_eta(end - now)}" if end else "now (fixed)"
        else:
            when = f"in {fmt_eta(start - now)}"
        col = (150, 230, 160) if key and i == 0 else (225, 225, 235) if key else (140, 140, 155)
        panel.blit(_font(14, i == 0).render(name, True, col), (18, y))
        panel.blit(_font(13).render(when, True, (170, 170, 185)), (420, y + 1))
        y += 20
    foot = _font(12).render("A full moon makes a Blood Moon twice as likely. The Realm keeps to its schedule - "
                            "what you see here is what you get.", True, (140, 140, 155))
    if foot.get_width() > r.w - 28:
        foot = _font(11).render("Full moon = Blood Moon x2 likely. The Realm keeps to its schedule.", True,
                                (140, 140, 155))
    panel.blit(foot, (18, r.h - 24))
    surf.blit(panel, r.topleft)

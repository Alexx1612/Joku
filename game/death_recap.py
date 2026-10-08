"""
The death recap: permadeath is only fair if you can see what killed you.

Player.take_damage(..., source=(who, what, telegraphed)) keeps the last hits in Player.hit_log
(every hit source tags itself: enemy bullets carry Bullet.src_info, ground zones carry
zone["info"], contact hits / embers pass their own). build() turns that log into a small
JSON-safe dict that rides in death_info (single-player and the co-op server's snapshot), and
draw() puts it under "YOU DIED": the killing blow, the last 5 hits, damage by source, and one
(goofy, but useful) tip.
"""
import pygame

LAST_N = 5


def build(player):
    """{killer, attack, dmg, tele, last: [hit...], by_source: [[who, dmg]...], tip} or None."""
    log = list(getattr(player, "hit_log", None) or [])
    if not log:
        return None
    last = log[-1]
    by = {}
    for h in log:
        by[h["who"]] = by.get(h["who"], 0) + h["dmg"]
    return {"killer": last["who"], "attack": last["what"], "dmg": last["dmg"], "tele": last["tele"],
            "last": [dict(h) for h in log[-LAST_N:][::-1]],
            "by_source": [[w, d] for w, d in sorted(by.items(), key=lambda kv: -kv[1])[:4]],
            "tip": tip_for(log)}


def tip_for(log):
    last = log[-1]
    what = last["what"].lower()
    if "contact" in what:
        return "It walked right into you. Keep your distance - most things that hug you hit hard."
    if last["who"] == "The Ashlands":
        return "The Ashlands floor burns. Stand on stone or keep moving through it."
    if last["tele"]:
        return ("That one was telegraphed: a red lane or an orange zone shows where it lands. "
                "Step out sideways the moment you see it.")
    if len({h["who"] for h in log}) >= 3:
        return "Lots of things were shooting at once. Pull one group at a time - the dash (Shift) has i-frames."
    return "Plain shots add up. Strafe, use your dash (Shift) and drink a potion before it's too late."


def draw(surf, recap, top, center_x, font_s, font_m):
    """The recap panel, centred at center_x from y=top. Returns its rect (or None)."""
    if not recap:
        return None
    from game import ui
    w, h = 660, 236
    r = pygame.Rect(center_x - w // 2, top, w, h)
    panel, _ = ui._ornate_panel(w, h, border=(200, 70, 70))
    surf.blit(panel, r.topleft)
    x, y = r.x + 16, r.y + 12
    head = f"Killed by {recap['killer']} - {recap['attack']} ({recap['dmg']} dmg)"
    surf.blit(font_m.render(head, True, (255, 120, 110)), (x, y))
    y += 24
    tele = "Telegraphed: yes - it was marked before it landed" if recap["tele"] else "Telegraphed: no"
    surf.blit(font_s.render(tele, True, (230, 200, 150) if recap["tele"] else (170, 170, 180)), (x, y))
    y += 24
    col2 = r.x + w // 2 + 20
    surf.blit(font_s.render("Last hits (newest first)", True, ui.CHROME_GOLD), (x, y))
    surf.blit(font_s.render("Damage by source", True, ui.CHROME_GOLD), (col2, y))
    y += 20
    for i, hit in enumerate(recap["last"][:LAST_N]):
        line = f"-{hit['dmg']:>3}  {hit['who']}: {hit['what']}"
        while font_s.size(line)[0] > w // 2 - 24 and len(line) > 10:
            line = line[:-2]
        surf.blit(font_s.render(line, True, (235, 225, 225) if i == 0 else (200, 196, 205)), (x, y + i * 18))
    total = sum(d for _w, d in recap["by_source"]) or 1
    for i, (who, dmg) in enumerate(recap["by_source"]):
        yy = y + i * 18
        label = f"{who if font_s.size(who)[0] < 120 else who[:13] + '.'} {dmg}"
        room = r.right - 14 - col2 - font_s.size(label)[0] - 8
        bar_w = max(2, int(max(10, min(140, room)) * dmg / total))
        pygame.draw.rect(surf, (150, 50, 50), (col2, yy + 3, bar_w, 11), border_radius=3)
        surf.blit(font_s.render(label, True, (225, 220, 225)), (col2 + bar_w + 6, yy))
    y += LAST_N * 18 + 8
    for k, line in enumerate(ui._wrap_text("Tip: " + recap["tip"], font_s, w - 32)[:2]):
        surf.blit(font_s.render(line, True, (170, 220, 170)), (x, y + k * 17))
    return r

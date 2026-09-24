"""HUD, inventory bar and menu screens."""
import math
import pygame
from game import constants as C
from game import sprites
from game.items import VAULT_CHEST_SIZE, VAULT_CHEST_COUNT
from game.entities import BAG_CAPACITY

pygame.font.init()
_FONT_S = pygame.font.SysFont("consolas", 14)
_FONT_M = pygame.font.SysFont("consolas", 18, bold=True)
_FONT_L = pygame.font.SysFont("consolas", 30, bold=True)
_FONT_XL = pygame.font.SysFont("consolas", 54, bold=True)


# --------------------------------------------------------------- HUD chrome --
# One shared visual language (gold-trimmed dark panels with a carved-bevel
# inset look for anything that "holds" something - bars, slots) reused by
# every panel/slot/bar in this file instead of each one drawing its own flat
# rect+border. Redraw-only: no hit-test geometry here changes - every rect_
# for()/hit-test function elsewhere in this file is untouched.
CHROME_GOLD = (196, 162, 94)
CHROME_GOLD_DIM = (120, 100, 60)
CHROME_BG_TOP = (26, 24, 34)
CHROME_BG_BOTTOM = (14, 13, 19)
CHROME_INSET_SHADOW = (0, 0, 0)
CHROME_INSET_HILITE = (255, 255, 255)


def _vgrad(surf, rect, top_color, bottom_color):
    """Vertical gradient fill inside `rect` (local surf coords) - cheap (one
    draw.rect per row-band, not per-pixel), used for every panel/bar body so
    flat colors never look like a plain programmer-art block."""
    x, y, w, h = rect
    if h <= 0 or w <= 0:
        return
    bands = max(1, min(h, 24))
    band_h = h / bands
    for i in range(bands):
        t = i / max(1, bands - 1)
        col = tuple(int(top_color[c] + (bottom_color[c] - top_color[c]) * t) for c in range(3))
        yy = int(y + i * band_h)
        hh = max(1, int(band_h) + 1)
        pygame.draw.rect(surf, col, (x, yy, w, hh))


def _ornate_panel(w, h, border=CHROME_GOLD, title=None, title_font=None):
    """A framed panel Surface: gradient body, a bright/dim double-line gold
    border (outer dim, inner bright - a carved-frame look, not a flat line),
    small corner accent ticks, and an optional inset title bar. Callers blit
    their own content on top starting below the title bar (see `content_y0`
    on the returned tuple) - geometry/placement of that content is unchanged
    from before, only the chrome underneath it is new."""
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    _vgrad(panel, (0, 0, w, h), CHROME_BG_TOP, CHROME_BG_BOTTOM)
    pygame.draw.rect(panel, (*border, 90), (0, 0, w, h), width=1, border_radius=7)
    pygame.draw.rect(panel, border, (1, 1, w - 2, h - 2), width=2, border_radius=6)
    pygame.draw.rect(panel, (*CHROME_INSET_HILITE, 18), (2, 2, w - 4, h - 4), width=1, border_radius=5)
    tick = 5
    for cx, cy, dx, dy in ((0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)):
        pygame.draw.line(panel, border, (cx + dx * 3, cy + dy * 3), (cx + dx * (3 + tick), cy + dy * 3), 2)
        pygame.draw.line(panel, border, (cx + dx * 3, cy + dy * 3), (cx + dx * 3, cy + dy * (3 + tick)), 2)
    content_y0 = 4
    if title:
        font = title_font or _FONT_S
        bar_h = font.get_height() + 8
        pygame.draw.rect(panel, (*border, 50), (2, 2, w - 4, bar_h), border_radius=5)
        pygame.draw.line(panel, border, (2, 2 + bar_h), (w - 2, 2 + bar_h), 1)
        t = font.render(title, True, (240, 228, 200))
        panel.blit(t, (w // 2 - t.get_width() // 2, 2 + bar_h // 2 - t.get_height() // 2))
        content_y0 = 2 + bar_h + 4
    return panel, content_y0


def _slot_frame(surf, rect, filled=False, hovered=False, accent=None, border=True):
    """A single item-slot frame: recessed bevel (dark top/left edge, bright
    bottom/right edge - reads as "carved into the panel", the opposite bevel
    direction from a raised button) plus a soft gold glow when it holds an
    item. Same one visual language for equip/backpack/bag/vault/trade slots -
    every slot call site below just calls this instead of its own two-line
    flat rect+border. `border=False` (item slots only, per user feedback that
    the border didn't help identify items and made them harder to see) skips
    the two outline rects but keeps the background gradient, so a slot with
    nothing in it still reads as a slot."""
    x, y, w, h = rect
    base_top = (20, 19, 24) if not filled else (30, 27, 22)
    base_bot = (11, 10, 14) if not filled else (18, 16, 13)
    _vgrad(surf, (x, y, w, h), base_top, base_bot)
    if not border:
        return
    col = accent or (CHROME_GOLD if filled else (80, 78, 88))
    if hovered:
        col = tuple(min(255, c + 40) for c in col)
    pygame.draw.rect(surf, CHROME_INSET_SHADOW, (x, y, w, h), width=1, border_radius=4)
    pygame.draw.rect(surf, col, (x + 1, y + 1, w - 2, h - 2), width=1, border_radius=4)
    pygame.draw.line(surf, (*CHROME_INSET_HILITE, 25), (x + 2, y + h - 2), (x + w - 2, y + h - 2), 1)
    if filled:
        for cx, cy in ((x + 2, y + 2), (x + w - 2, y + 2), (x + 2, y + h - 2), (x + w - 2, y + h - 2)):
            pygame.draw.circle(surf, col, (cx, cy), 1)


def _tier_badge(surf, rect, item):
    """Small tier number (or "UT" for untiered) in a slot's bottom-right corner -
    lets you tell an item's tier at a glance in the inventory grid, not just from
    the hover tooltip."""
    if item is None:
        return
    label = "UT" if item.is_ut else (str(item.tier) if item.tier else None)
    if not label:
        return
    txt = _FONT_S.render(label, True, (255, 225, 140) if item.is_ut else (225, 225, 230))
    bx = rect.x + rect.w - txt.get_width() - 3
    by = rect.y + rect.h - txt.get_height() - 1
    shadow = _FONT_S.render(label, True, (0, 0, 0))
    surf.blit(shadow, (bx + 1, by + 1))
    surf.blit(txt, (bx, by))


def _bar(surf, x, y, w, h, frac, fg, bg, gloss=True):
    """A framed stat bar: gradient fill (lighter top / true color bottom) +
    a thin gloss highlight band + a gold-ish outer frame instead of a flat
    single-color fill with a black 1px border."""
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=3)
    fill_w = max(0, int(w * max(0, min(1, frac))))
    if fill_w > 0:
        top = tuple(min(255, int(c * 1.35 + 20)) for c in fg)
        _vgrad(surf, (x, y, fill_w, h), top, fg)
        if gloss and h >= 6:
            gloss_h = max(1, h // 3)
            gloss_layer = pygame.Surface((fill_w, gloss_h), pygame.SRCALPHA)
            gloss_layer.fill((255, 255, 255, 40))
            surf.blit(gloss_layer, (x, y + 1))
    pygame.draw.rect(surf, CHROME_GOLD_DIM, (x, y, w, h), width=1, border_radius=3)


def _bevel_button(surf, rect, base_color, hovered=False, enabled=True, border_radius=5):
    """A small raised-bevel action button (bright top/left edge, dark bottom/
    right edge - the opposite direction from _slot_frame's recessed socket
    look, since a button reads as "pressable", not "a container") - shared
    look for every small labeled button (trade accept/cancel, friends-panel
    TP/Trade/Remove, nearby-players TP) instead of each drawing its own flat
    fill+border pair."""
    x, y, w, h = rect
    col = base_color if enabled else tuple(c // 2 for c in base_color)
    top = tuple(min(255, int(c * 1.3 + 15)) for c in col)
    _vgrad(surf, (x, y, w, h), top if hovered else col, col if hovered else tuple(int(c * 0.75) for c in col))
    pygame.draw.rect(surf, CHROME_INSET_SHADOW, (x, y, w, h), width=1, border_radius=border_radius)
    pygame.draw.line(surf, (*CHROME_INSET_HILITE, 60), (x + 2, y + 1), (x + w - 2, y + 1), 1)


def draw_portal_prompt(surf):
    """Bottom-right "press ENTER" prompt - shown while standing on/near a
    portal (see main.py/coop_client.py's _portal_prompt state). Entering a
    portal is now a deliberate key press, not an automatic walk-over
    trigger, so the player always sees this before anything happens."""
    label = _FONT_M.render("Press ENTER to enter", True, (240, 230, 190))
    pad_x, pad_y = 14, 10
    w, h = label.get_width() + pad_x * 2, label.get_height() + pad_y * 2
    x, y = C.SCREEN_W - w - 16, C.SCREEN_H - h - 16
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(panel, (20, 18, 14, 210), (0, 0, w, h), border_radius=6)
    pygame.draw.rect(panel, (200, 170, 90, 230), (0, 0, w, h), width=2, border_radius=6)
    panel.blit(label, (pad_x, pad_y))
    surf.blit(panel, (x, y))


def fps_counter_rect():
    """Bottom-left, clear of the centered bottom hint text (draw_hud below) and
    of the Vault's own backpack row (that's a separate full-page view, not the
    live HUD dock, so it never coexists with this)."""
    return pygame.Rect(12, C.SCREEN_H - 22, 70, 18)


_FPS_WARN_THRESHOLD = 30  # below this, tint the readout to flag a real slowdown


def draw_fps_counter(surf, fps):
    """A live FPS readout for the corner of the screen - green when healthy,
    amber once it drops below a real "this is starting to feel choppy"
    threshold, so a slowdown is visible at a glance instead of only showing
    up in a headless benchmark."""
    color = (140, 220, 140) if fps >= _FPS_WARN_THRESHOLD else (230, 180, 90)
    txt = _FONT_S.render(f"FPS: {fps:.0f}", True, color)
    surf.blit(txt, fps_counter_rect().topleft)


def draw_hud(surf, zone_name, kill_count, boss_alive):
    """Top-of-screen zone banner - HP/MP/stats live in the right-docked player
    panel now (see draw_player_panel), matching the "everything on the right"
    layout, so this is just the zone name/kill counter above the minimap."""
    pad = 12
    zone_surf = _FONT_M.render(zone_name, True, C.COL_WHITE)
    surf.blit(zone_surf, (C.SCREEN_W - zone_surf.get_width() - pad, pad))
    kc = _FONT_S.render(f"kills: {kill_count}" + ("  [BOSS ACTIVE]" if boss_alive else ""), True, (220, 180, 80) if boss_alive else (190, 190, 200))
    surf.blit(kc, (C.SCREEN_W - kc.get_width() - pad, pad + 24))
    hint = _FONT_S.render("WASD move | mouse aim+click fire | Space ability | Enter chat", True, (150, 150, 160))
    surf.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, C.SCREEN_H - 26))


PLAYER_PANEL_WIDTH = 226  # matches the width of a 4-wide, 52px equip/backpack slot row (SLOT_SIZE below)
PLAYER_PANEL_HEIGHT = 150


def _panel_block_x0():
    """Left edge of the wider right-docked info block (name/HP/MP/stats) -
    right-aligned to the same edge as the minimap and the equip/backpack grid."""
    return _dock_right_x() - PLAYER_PANEL_WIDTH


def draw_player_panel(surf, player, auto_fire=False):
    """The right-docked 'who am I' block: name/class/level, HP, MP, XP, and full
    stat spread, directly below the minimap and directly above the equip grid -
    RotMG-style, everything about your character in one place on the right."""
    x0 = _panel_block_x0()
    w = PLAYER_PANEL_WIDTH
    y = _dock_top_y() - PLAYER_PANEL_HEIGHT

    panel, _ = _ornate_panel(w + 12, PLAYER_PANEL_HEIGHT + 8)
    surf.blit(panel, (x0 - 6, y - 4))

    name = f"{player.cls_name.title()} Lv{player.level}" + (f" {player.title}" if player.title else "")
    name_surf = _FONT_S.render(name, True, (230, 220, 190) if not player.title else (230, 210, 140))
    surf.blit(name_surf, (x0 + w // 2 - name_surf.get_width() // 2, y))
    y += 18

    bar_h = 13
    _bar(surf, x0, y, w, bar_h, player.hp / player.hp_max, C.COL_HP, C.COL_HP_BG)
    hp_txt = _FONT_S.render(f"{int(player.hp)}/{player.hp_max}", True, C.COL_WHITE)
    surf.blit(hp_txt, (x0 + w // 2 - hp_txt.get_width() // 2, y - 1))
    y += bar_h + 4

    _bar(surf, x0, y, w, bar_h, player.mp / player.mp_max, C.COL_MP, C.COL_MP_BG)
    mp_txt = _FONT_S.render(f"{int(player.mp)}/{player.mp_max}", True, C.COL_WHITE)
    surf.blit(mp_txt, (x0 + w // 2 - mp_txt.get_width() // 2, y - 1))
    y += bar_h + 5

    xp_need = C.xp_to_next(player.level)
    xp_bar_h = 10
    _bar(surf, x0, y, w, xp_bar_h, player.xp / xp_need, C.COL_XP, (60, 50, 15))
    xp_txt = _FONT_S.render(f"XP {int(player.xp)}/{xp_need}", True, (235, 230, 200))
    surf.blit(xp_txt, (x0 + w // 2 - xp_txt.get_width() // 2, y - 2))
    y += xp_bar_h + 7

    stats = [("ATT", player.total_stat("att")), ("DEF", player.total_stat("deF")),
             ("SPD", player.total_stat("spd")), ("DEX", player.total_stat("dex")),
             ("VIT", player.total_stat("vit")), ("WIS", player.total_stat("wis"))]
    for i in range(0, 6, 2):
        row = f"{stats[i][0]} {stats[i][1]:<3}{stats[i + 1][0]} {stats[i + 1][1]}"
        rs = _FONT_S.render(row, True, (190, 190, 205))
        surf.blit(rs, (x0 + w // 2 - rs.get_width() // 2, y))
        y += 16
    if auto_fire:
        af = _FONT_S.render("[AUTO-FIRE]", True, (140, 210, 255))
        surf.blit(af, (x0 + w // 2 - af.get_width() // 2, y))
        y += 16
    if getattr(player, "pet", None) is not None:
        from game.items import PET_KINDS
        pet_name = PET_KINDS.get(player.pet.kind, {}).get("name", player.pet.kind.title())
        pt = _FONT_S.render(f"Pet: {pet_name}", True, (170, 220, 255))
        surf.blit(pt, (x0 + w // 2 - pt.get_width() // 2, y))


PET_PANEL_W = 200
PET_PANEL_ROW_H = 22


def pet_panel_rect(player):
    """Top-left dock (the old HP/stat readout spot before it moved into the
    right-docked player panel - see draw_nearby_loot_panel's own note) for the
    compact pet-info panel. None when the player has no hatched pet, so
    callers (draw + the drag-and-drop feed hit-test) can both no-op cleanly."""
    if getattr(player, "pet", None) is None:
        return None
    h = 30 + PET_PANEL_ROW_H * 3 + 20
    return pygame.Rect(12, 90, PET_PANEL_W, h)


def pet_feed_target_rect(player):
    """Same rect as the pet panel body - dragging any backpack item onto it
    feeds the pet (see entities.Player.feed_pet), the same drag-and-drop-onto-
    a-target convention every other slot in this file already uses."""
    return pet_panel_rect(player)


def draw_pet_panel(surf, player, dragging=False):
    """Compact pet-info HUD panel: the pet's 3 independently-leveled ability
    slots (heal/magic/attack - see entities.Pet) each with a level and a
    progress-to-next-level bar, plus a feed hint. `dragging`: a backpack item
    is currently being dragged, so the panel's border lights up as a valid
    drop target, matching how equip slots highlight during a drag."""
    from game.items import PET_KINDS, PET_RARITY_MAX_LEVEL, PET_LEVEL_XP_STEP
    pet = getattr(player, "pet", None)
    if pet is None:
        return
    rect = pet_panel_rect(player)
    panel, _ = _ornate_panel(rect.w, rect.h, border=CHROME_GOLD if dragging else CHROME_GOLD_DIM)
    d = PET_KINDS.get(pet.kind, {})
    name = d.get("name", pet.kind.title())
    title = _FONT_S.render(f"Pet: {name} ({pet.rarity})", True, (230, 210, 150))
    panel.blit(title, (8, 6))
    max_level = PET_RARITY_MAX_LEVEL.get(pet.rarity, 10)
    labels = {"heal": ("Heal", (110, 230, 140)), "magic": ("Magic", (120, 170, 255)),
              "attack": ("Attack", (255, 170, 90))}
    y = 28
    for key in ("heal", "magic", "attack"):
        st = pet.abilities[key]
        label, color = labels[key]
        lvl = st["level"]
        txt = _FONT_S.render(f"{label} Lv{lvl}", True, (200, 200, 215))
        panel.blit(txt, (8, y))
        if lvl < max_level:
            frac = min(1.0, st["xp"] / PET_LEVEL_XP_STEP)
            _bar(panel, 8, y + 15, rect.w - 16, 5, frac, color, (40, 40, 46), gloss=False)
        else:
            maxed = _FONT_S.render("MAX", True, (255, 220, 120))
            panel.blit(maxed, (rect.w - 8 - maxed.get_width(), y))
        y += PET_PANEL_ROW_H
    hint = _FONT_S.render("Drag an item here to feed", True, (150, 150, 165))
    panel.blit(hint, (rect.w // 2 - hint.get_width() // 2, y + 2))
    surf.blit(panel, (rect.x, rect.y))


SLOT_SIZE = 52  # bumped from 40 - user said item icons were too hard to see
SLOT_GAP = 6

EQUIP_LABELS = ["WP", "AB", "AR", "RG"]
EQUIP_SLOT_ORDER = ["weapon", "ability", "armor", "ring"]
BACKPACK_COLS = 4

# RotMG docks its inventory in a panel on the right of the screen, map above it -
# this mirrors that: a 2-wide equip grid + 2-wide backpack grid stacked directly
# below the corner minimap, all right-aligned to the same edge. Computed per-call
# (not frozen module constants) so it stays anchored correctly if C.SCREEN_W/H
# change at runtime (fullscreen/resize).
DOCK_PAD = 14


def _dock_right_x():
    return C.SCREEN_W - DOCK_PAD


def _dock_top_y():
    """Top of the equip grid - below the minimap block AND the player info panel."""
    from game import minimap
    return 74 + minimap.corner_block_height() + 14 + PLAYER_PANEL_HEIGHT + 14


def equip_slot_rects():
    """Returns [(rect, slot_type), ...] in WP/AB/AR/RG order - slot_type matches Item.slot,
    used both to draw the bar and to validate/hit-test drag-and-drop drops. A single row
    of 4, right-docked, the same width as the backpack grid below it - a wide-but-short
    layout so the whole right dock (minimap + panel + equip + backpack) fits comfortably
    within the screen height instead of running off the bottom."""
    x1 = _dock_right_x()
    y0 = _dock_top_y()
    n = len(EQUIP_SLOT_ORDER)
    rects = []
    for i, slot_type in enumerate(EQUIP_SLOT_ORDER):
        x = x1 - (n - i) * (SLOT_SIZE + SLOT_GAP) + SLOT_GAP
        rects.append((pygame.Rect(x, y0, SLOT_SIZE, SLOT_SIZE), slot_type))
    return rects


def draw_inventory(surf, player, mouse_pos, dragging_from=None):
    """dragging_from: the (kind, index_or_slot) currently being dragged, if any - so its
    origin slot can be dimmed instead of showing the item twice (once in-place, once
    following the cursor)."""
    equip_items = {"weapon": player.weapon, "ability": player.ability,
                    "armor": player.armor, "ring": player.ring}
    hovered = None
    for i, (rect, slot_type) in enumerate(equip_slot_rects()):
        it = equip_items[slot_type]
        show = it and dragging_from != ("equip", slot_type)
        _slot_frame(surf, rect, filled=bool(show), hovered=rect.collidepoint(mouse_pos), border=False)
        if show:
            icon = sprites.item_icon(it.color, it.shape)
            surf.blit(pygame.transform.smoothscale(icon, (SLOT_SIZE - 6, SLOT_SIZE - 6)), (rect.x + 3, rect.y + 3))
            _tier_badge(surf, rect, it)
            if rect.collidepoint(mouse_pos):
                hovered = it
        elif not it:
            lbl = _FONT_S.render(EQUIP_LABELS[i], True, (70, 70, 78))
            surf.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.centery - lbl.get_height() // 2))

    for i, rect in enumerate(backpack_slot_rects(player)):
        show = i < len(player.backpack) and dragging_from != ("backpack", i)
        _slot_frame(surf, rect, filled=show, hovered=rect.collidepoint(mouse_pos), border=False)
        if show:
            it = player.backpack[i]
            icon = sprites.item_icon(it.color, it.shape)
            surf.blit(pygame.transform.smoothscale(icon, (SLOT_SIZE - 6, SLOT_SIZE - 6)), (rect.x + 3, rect.y + 3))
            num = _FONT_S.render(str(i + 1), True, (140, 140, 150))
            surf.blit(num, (rect.x + 2, rect.y + 2))
            _tier_badge(surf, rect, it)
            if rect.collidepoint(mouse_pos):
                hovered = it
    if hovered and dragging_from is None:
        _tooltip(surf, mouse_pos, hovered)


def draw_dragged_item(surf, item, mouse_pos):
    """The floating icon that follows the cursor while dragging an item."""
    icon = pygame.transform.smoothscale(sprites.item_icon(item.color, item.shape), (SLOT_SIZE - 6, SLOT_SIZE - 6))
    holder = icon.copy()
    holder.set_alpha(230)
    surf.blit(holder, (mouse_pos[0] - (SLOT_SIZE - 6) // 2, mouse_pos[1] - (SLOT_SIZE - 6) // 2))


def draw_ground_item_tooltip(surf, cam, mouse_pos, ground_items, radius=40):
    """Hover a dropped bag to see a summary of what's inside before walking over to
    open it - works from a distance (mouse-hover, not proximity-to-player).
    `ground_items` may be real Bags (which carry the full `items` list, e.g.
    single-player) or network "ghost" ones that only know the top item's name/
    tier colour + a count (a co-op peer's loot, from the server snapshot)."""
    hovered, best_d2 = None, None
    r2 = radius * radius
    for g in ground_items:
        sx, sy = cam(g.pos)
        d2 = (sx - mouse_pos[0]) ** 2 + (sy - mouse_pos[1]) ** 2
        if d2 <= r2 and (best_d2 is None or d2 < best_d2):
            hovered, best_d2 = g, d2
    if hovered is None:
        return
    items = getattr(hovered, "items", None)
    if items:
        if len(items) == 1:
            _tooltip(surf, mouse_pos, items[0])
            return
        name = f"Bag ({len(items)} items)"
        color = hovered.bag_color
    else:
        name = getattr(hovered, "name", None)
        if name is None:
            return
        count = getattr(hovered, "count", 1)
        if count > 1:
            name = f"{name} +{count - 1} more"
        color = getattr(hovered, "tier_color", (200, 200, 200))
    w = _FONT_S.size(name)[0] + 16
    h = 26
    x = min(mouse_pos[0] + 12, C.SCREEN_W - w - 4)
    y = min(mouse_pos[1] - h - 8, C.SCREEN_H - h - 4)
    box, _ = _ornate_panel(w, h, border=color)
    surf.blit(box, (x, y))
    surf.blit(_FONT_S.render(name, True, color), (x + 8, y + 6))


def _wrap_text(text, font, max_width):
    words = text.split()
    lines, line = [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if font.size(trial)[0] > max_width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


TOOLTIP_WRAP_WIDTH = 240


def _tooltip(surf, pos, item):
    lines = [item.display_name]
    stat_line_count = 0
    if item.min_dmg or item.max_dmg:
        lines.append(f"Damage: {item.min_dmg}-{item.max_dmg}")
        stat_line_count += 1
    for k, v in item.stat_bonus.items():
        lines.append(f"+{v} {k.upper()}")
        stat_line_count += 1
    if item.effect:
        lines.append(f"{item.effect.title()}: {item.magnitude} dmg/hp, {item.mp_cost} MP")
        stat_line_count += 1
    if item.proc:
        lines.append(item.proc)
        stat_line_count += 1
    desc_lines = _wrap_text(item.description, _FONT_S, TOOLTIP_WRAP_WIDTH) if item.description else []
    lines.extend(desc_lines)
    w = max(max(_FONT_S.size(l)[0] for l in lines) + 16, 120)
    w = min(w, TOOLTIP_WRAP_WIDTH + 16)
    h = 20 * len(lines) + 10
    x = min(pos[0] + 12, C.SCREEN_W - w - 4)
    y = min(pos[1] - h - 8, C.SCREEN_H - h - 4)
    box, _ = _ornate_panel(w, h, border=item.color)
    surf.blit(box, (x, y))
    for i, line in enumerate(lines):
        is_desc = i >= 1 + stat_line_count
        color = item.color if i == 0 else (150, 150, 165) if is_desc else (210, 210, 215)
        surf.blit(_FONT_S.render(line, True, color), (x + 8, y + 6 + i * 20))


def draw_peer_tooltip(surf, pos, peer, crew_name=""):
    """A co-op peer's gear/stats on hover - mirrors RotMG showing a nearby
    player's level/equipment/HP when you hover their name. `peer.net_totals`
    is required (i.e. peer must come from Player.from_net_state).
    `crew_name` is a client-local best-effort lookup (see game/crews.py) -
    empty unless the peer happens to resolve in this client's own crew
    membership index."""
    title_suffix = f" {peer.title}" if peer.title else ""
    lines = [f"{peer.name}{title_suffix} - {peer.cls_name.title()} Lv{peer.level}"]
    line_colors = [(230, 220, 160)]
    if crew_name:
        lines.append(f"Crew: {crew_name}")
        line_colors.append((150, 210, 255))
    slot_labels = [("weapon", "Weapon"), ("armor", "Armor"), ("ring", "Ring"), ("ability", "Ability")]
    for attr, label in slot_labels:
        it = getattr(peer, attr)
        if it:
            lines.append(f"{label}: {it.display_name}")
            line_colors.append(it.color)
        else:
            lines.append(f"{label}: -")
            line_colors.append((120, 120, 128))
    totals = getattr(peer, "net_totals", {})
    stat_line = "  ".join(f"{k.upper() if k != 'deF' else 'DEF'} {v}" for k, v in totals.items())
    if stat_line:
        lines.append(stat_line)
        line_colors.append((190, 190, 200))
    hp_line = f"HP {int(peer.hp)}/{peer.hp_max}"
    lines.append(hp_line)
    line_colors.append((220, 130, 130))

    w = max(_FONT_S.size(l)[0] for l in lines) + 16
    h = 20 * len(lines) + 10
    x = min(pos[0] + 14, C.SCREEN_W - w - 4)
    y = max(4, min(pos[1] - h - 10, C.SCREEN_H - h - 4))
    box, _ = _ornate_panel(w, h)
    surf.blit(box, (x, y))
    for i, (line, color) in enumerate(zip(lines, line_colors)):
        surf.blit(_FONT_S.render(line, True, color), (x + 8, y + 6 + i * 20))


def draw_center_text(surf, text, sub=None, color=C.COL_WHITE):
    t = _FONT_L.render(text, True, color)
    surf.blit(t, (C.SCREEN_W // 2 - t.get_width() // 2, C.SCREEN_H // 2 - 60))
    if sub:
        s = _FONT_M.render(sub, True, (200, 200, 205))
        surf.blit(s, (C.SCREEN_W // 2 - s.get_width() // 2, C.SCREEN_H // 2 - 20))


def death_screen_button_rect():
    w, h = 220, 44
    return pygame.Rect(C.SCREEN_W // 2 - w // 2, C.SCREEN_H // 2 + 30, w, h)


def draw_death_screen_button(surf, mouse_pos=(-1, -1)):
    """A real clickable "New Character" button on the death screen, alongside
    the existing Enter-key shortcut - draw_center_text (also used for the
    co-op connecting/error/syncing screens) stays generic; this is layered on
    top only for the actual death state."""
    rect = death_screen_button_rect()
    hovered = rect.collidepoint(mouse_pos)
    _bevel_button(surf, rect, (150, 50, 50), hovered=hovered)
    label = _FONT_M.render("New Character", True, (240, 230, 225))
    surf.blit(label, (rect.centerx - label.get_width() // 2, rect.centery - label.get_height() // 2))


INTRO_DURATION = 3.0
INTRO_FADE_IN = 0.9
INTRO_FADE_OUT = 0.6      # last N seconds of the intro fade to black before phasing
                          # into the name-entry screen (see draw_name_entry's own
                          # fade-in) - skipped entirely if the player presses a key/
                          # clicks to skip, so impatient players never wait on it
NAME_ENTRY_FADE_IN = 0.4  # first N seconds of the name-entry screen fade from black,
                          # completing the phase-transition INTRO_FADE_OUT starts
INTRO_JOKES = [
    "Loading more bags than sense.",
    "Wizards: ranged cowards, proudly.",
    "Permadeath. No backsies.",
    "Warriors read slower.",
    "The fountain lies sometimes.",
    "Oryx sends his regrets.",
    "Your pet judges you.",
    "Purple bags, purple prose.",
    "Fish first, ask questions later.",
    "Blood Moons: bring a friend.",
    "Loot rolls, not dice rolls.",
    "Trust the Guide. Mostly.",
    "Void Rod sold separately.",
    "Achievements: fancy tombstones.",
    "Rogues: sneaky, not subtle.",
]


def draw_intro_screen(surf, elapsed, joke, duration=INTRO_DURATION, fade_in=INTRO_FADE_IN, fade_out=INTRO_FADE_OUT):
    """A short fade-in title card shown once at launch - an "epic" title with a
    randomly-picked joke/quote under it, skippable with any key/click (see
    main.py's handle_events). Not a menu, just atmosphere before the name-entry
    screen (draw_name_entry) - the two fade to/from black across the state change
    (INTRO_FADE_OUT here, NAME_ENTRY_FADE_IN there) so it reads as one continuous
    "phase" rather than a hard cut, when the player lets the timer run its course."""
    surf.fill((8, 8, 14))
    alpha = max(0, min(255, int(255 * (elapsed / fade_in))))

    title_text = C.TITLE.split(" - ")[0] if " - " in C.TITLE else C.TITLE
    title = _FONT_XL.render(title_text.upper(), True, (255, 215, 110))
    shadow = _FONT_XL.render(title_text.upper(), True, (60, 40, 10))
    tx = C.SCREEN_W // 2 - title.get_width() // 2
    ty = C.SCREEN_H // 2 - 70
    pulse = 1.0 + 0.03 * math.sin(elapsed * 6.0)
    title_scaled = pygame.transform.smoothscale(
        title, (max(1, int(title.get_width() * pulse)), max(1, int(title.get_height() * pulse))))
    shadow_scaled = pygame.transform.smoothscale(
        shadow, (max(1, int(shadow.get_width() * pulse)), max(1, int(shadow.get_height() * pulse))))

    holder = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    sr = shadow_scaled.get_rect(center=(C.SCREEN_W // 2 + 3, ty + title.get_height() // 2 + 3))
    holder.blit(shadow_scaled, sr)
    tr = title_scaled.get_rect(center=(C.SCREEN_W // 2, ty + title.get_height() // 2))
    holder.blit(title_scaled, tr)

    joke_surf = _FONT_M.render(joke, True, (190, 190, 205))
    holder.blit(joke_surf, (C.SCREEN_W // 2 - joke_surf.get_width() // 2, ty + title.get_height() + 20))

    holder.set_alpha(alpha)
    surf.blit(holder, (0, 0))

    if elapsed > fade_in + 0.2:
        hint_alpha = max(0, min(255, int(255 * (elapsed - fade_in - 0.2) / 0.4)))
        hint = _FONT_S.render("press any key to continue", True, (140, 140, 155))
        hint_holder = pygame.Surface(hint.get_size(), pygame.SRCALPHA)
        hint_holder.blit(hint, (0, 0))
        hint_holder.set_alpha(hint_alpha)
        surf.blit(hint_holder, (C.SCREEN_W // 2 - hint.get_width() // 2, C.SCREEN_H - 60))

    if elapsed > duration - fade_out:
        t = min(1.0, (elapsed - (duration - fade_out)) / fade_out)
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
        overlay.set_alpha(int(255 * t))
        surf.blit(overlay, (0, 0))


def draw_name_entry(surf, buffer, elapsed=0.0, fade_in=NAME_ENTRY_FADE_IN):
    """The "what should we call you?" prompt shown once at launch, right after the
    intro card - reuses draw_chat_box's exact type-in-box look (one text-input visual
    language in the whole game) as a full screen rather than a bottom-of-screen
    overlay. Fades in from black to complete the intro's own fade-out (INTRO_FADE_OUT),
    so the two screens read as one continuous phase transition, not a hard cut."""
    surf.fill((8, 8, 14))
    prompt = _FONT_L.render("WHAT SHOULD WE CALL YOU?", True, (255, 215, 110))
    surf.blit(prompt, (C.SCREEN_W // 2 - prompt.get_width() // 2, C.SCREEN_H // 2 - 90))

    w, h = 340, 34
    x, y = C.SCREEN_W // 2 - w // 2, C.SCREEN_H // 2 - h // 2
    box = pygame.Surface((w, h), pygame.SRCALPHA)
    box.fill((14, 14, 20, 235))
    pygame.draw.rect(box, (180, 170, 220, 255), (0, 0, w, h), width=2, border_radius=6)
    cursor = "_" if (pygame.time.get_ticks() // 400) % 2 == 0 else ""
    txt = _FONT_M.render("> " + buffer + cursor, True, (235, 235, 245))
    box.blit(txt, (10, h // 2 - txt.get_height() // 2))
    surf.blit(box, (x, y))

    hint = _FONT_S.render('Enter to confirm  |  leave blank for "You"', True, (160, 160, 175))
    surf.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, y + h + 10))

    if elapsed < fade_in:
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
        overlay.set_alpha(int(255 * (1.0 - elapsed / fade_in)))
        surf.blit(overlay, (0, 0))


PLAYER_LIGHT_RADIUS = 130
_LIGHT_SPRITE_CACHE = {}


def _get_light_sprite(radius):
    """A pre-baked radial-gradient 'light' sprite, cached by radius - built
    once per distinct radius and reused every frame (never rebuilt per-frame).
    Painted from the outside in with progressively smaller, higher-alpha
    filled circles: pygame.draw overwrites pixels rather than alpha-blending
    them, so the last (smallest) circle to cover a given pixel wins, which
    produces a true radial falloff from ~255 alpha at the center down to 0 at
    the edge using only cheap filled-circle draws, no per-pixel Python loop."""
    cached = _LIGHT_SPRITE_CACHE.get(radius)
    if cached is not None:
        return cached
    size = radius * 2
    sprite = pygame.Surface((size, size), pygame.SRCALPHA)
    center = (radius, radius)
    for r in range(radius, 0, -1):
        alpha = int(255 * (1.0 - r / radius))
        pygame.draw.circle(sprite, (0, 0, 0, alpha), center, r)
    _LIGHT_SPRITE_CACHE[radius] = sprite
    return sprite


TORCH_LIGHT_RADIUS = 70


def draw_day_night_overlay(surf, light_level, blood_moon=False, torch_screen_positions=None):
    """A translucent full-screen tint - deep blue at night, tinted red during a
    Blood Moon, nothing at high noon - with a soft lightmap cutout around the
    player's own position so standing still doesn't plunge you into total
    dark. The player is always exactly at screen-center: the camera follows
    the player every frame (Camera.follow), and Camera.__call__/cam(cam.pos)
    always maps to (screen_w/2, screen_h/2) regardless of Q/E rotation (see
    game/world.py's Camera class) - so the cutout needs no extra position
    argument threaded through every call site. Implemented by blitting a
    cached radial-gradient sprite onto the SRCALPHA overlay with
    BLEND_RGBA_SUB: the light sprite's color is pure black, so subtracting it
    only reduces the overlay's alpha channel where it lands (more transparent
    = brighter), leaving the tint color itself untouched everywhere else.
    light_level: 1.0 (noon) .. 0.0 (midnight). torch_screen_positions is an
    optional iterable of (x, y) SCREEN-space positions (already run through
    the caller's camera) for nearby torch props - each gets a smaller
    TORCH_LIGHT_RADIUS cutout of its own, same technique as the player's."""
    dark = 1.0 - light_level
    if dark <= 0.02:
        return
    alpha = int(150 * dark)
    tint = (120, 20, 20) if blood_moon else (10, 15, 45)
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((*tint, alpha))
    light = _get_light_sprite(PLAYER_LIGHT_RADIUS)
    lx = C.SCREEN_W // 2 - PLAYER_LIGHT_RADIUS
    ly = C.SCREEN_H // 2 - PLAYER_LIGHT_RADIUS
    overlay.blit(light, (lx, ly), special_flags=pygame.BLEND_RGBA_SUB)
    if torch_screen_positions:
        torch_light = _get_light_sprite(TORCH_LIGHT_RADIUS)
        for tx, ty in torch_screen_positions:
            overlay.blit(torch_light, (tx - TORCH_LIGHT_RADIUS, ty - TORCH_LIGHT_RADIUS),
                         special_flags=pygame.BLEND_RGBA_SUB)
    surf.blit(overlay, (0, 0))


DAY_NIGHT_CLOCK_W, DAY_NIGHT_CLOCK_H = 200, 60


def day_night_clock_rect():
    """Top-left, clear of the pet panel below it (pet_panel_rect starts at
    y=90 - this ends at y=72, an 18px gap) and clear of the right-docked
    minimap/quest-panel stack entirely - see Batch 10's overlap-avoidance
    discipline for why this is a real function, not just a hardcoded blit."""
    return pygame.Rect(12, 12, DAY_NIGHT_CLOCK_W, DAY_NIGHT_CLOCK_H)


def draw_day_night_clock(surf, light_level, blood_moon=False):
    """Sun fixed on the left (noon), moon fixed on the right (midnight), a
    marker sliding smoothly between them as light_level falls/rises - not a
    literal 24h clock hand, but a direct, honest visualization of the exact
    same light_level (1.0 noon .. 0.0 midnight) the game's own lighting
    overlay already uses (see draw_day_night_overlay), so the marker's
    position always matches what the screen actually looks like right now -
    and needs no new network field, since every caller already has this
    value for the overlay anyway. Recolors red during a Blood Moon."""
    rect = day_night_clock_rect()
    panel, _ = _ornate_panel(rect.w, rect.h, border=CHROME_GOLD if not blood_moon else (170, 50, 50))
    track_y = rect.h // 2 + 4
    track_x0, track_x1 = 30, rect.w - 30
    pygame.draw.line(panel, (90, 90, 105), (track_x0, track_y), (track_x1, track_y), 2)

    sun_color = (255, 215, 90) if not blood_moon else (200, 120, 60)
    pygame.draw.circle(panel, sun_color, (track_x0, track_y), 10)
    for i in range(8):
        ang = i * math.pi / 4
        x0 = track_x0 + math.cos(ang) * 13
        y0 = track_y + math.sin(ang) * 13
        x1 = track_x0 + math.cos(ang) * 17
        y1 = track_y + math.sin(ang) * 17
        pygame.draw.line(panel, sun_color, (x0, y0), (x1, y1), 2)

    moon_color = (220, 60, 60) if blood_moon else (200, 205, 220)
    pygame.draw.circle(panel, moon_color, (track_x1, track_y), 10)
    pygame.draw.circle(panel, CHROME_BG_TOP, (track_x1 + 4, track_y - 3), 8)

    marker_x = track_x0 + (1 - light_level) * (track_x1 - track_x0)
    marker_color = (230, 90, 90) if blood_moon else (240, 230, 180)
    pygame.draw.polygon(panel, marker_color, [(marker_x, track_y - 12), (marker_x - 5, track_y - 4),
                                               (marker_x + 5, track_y - 4)])

    label = "Blood Moon" if blood_moon else ("Night" if light_level < 0.35 else "Day")
    label_color = (255, 140, 140) if blood_moon else (200, 200, 215)
    txt = _FONT_S.render(label, True, label_color)
    panel.blit(txt, (rect.w // 2 - txt.get_width() // 2, rect.h - 20))
    surf.blit(panel, (rect.x, rect.y))


DAMAGE_POPUP_LIFETIME = 0.7


def draw_damage_popups(surf, cam, popups):
    """popups: list of dicts {x, y, amount, color, age} - caller owns aging/expiry."""
    for pop in popups:
        frac = pop["age"] / DAMAGE_POPUP_LIFETIME
        alpha = max(0, int(255 * (1 - frac)))
        rise = frac * 26
        txt = _FONT_M.render(str(pop["amount"]), True, pop["color"])
        holder = pygame.Surface(txt.get_size(), pygame.SRCALPHA)
        holder.blit(txt, (0, 0))
        holder.set_alpha(alpha)
        px, py = cam((pop["x"], pop["y"]))
        surf.blit(holder, (px - txt.get_width() // 2, py - 24 - rise))


HELP_LINES = [
    ("Move", "WASD / Arrows"),
    ("Aim", "Mouse"),
    ("Fire", "Left click"),
    ("Auto-fire toggle", "I"),
    ("Use/equip item", "1-8"),
    ("Interact", "Enter"),
    ("Nexus", "R"),
    ("Rotate camera", "Q / E"),
    ("Reset camera", "X"),
    ("Fullscreen (wider view)", "F11"),
    ("Full map / zoom", "M, scroll or +/-"),
    ("This menu", "O"),
    ("Quit / close menu", "Esc"),
]
HELP_NOTE = "Aim gets a soft assist near enemies. Click a backpack slot works too."


def _help_panel_geometry(menu_items=None):
    """Computes the help/options panel's (x, y, w, h, col_w, rows_per_col,
    menu_h, note_lines) - factored out of draw_help_overlay so
    help_close_button_rect() can hit-test the exact same rect the panel is
    actually drawn at, instead of duplicating/guessing the size math."""
    pad = 16
    menu_items = menu_items or []

    cols = 2
    rows_per_col = math.ceil(len(HELP_LINES) / cols)
    col_w = 0
    for label, keys in HELP_LINES:
        label_w = _FONT_S.size(label)[0]
        keys_w = _FONT_S.size(keys)[0]
        col_w = max(col_w, label_w + keys_w + 28)
    controls_w = col_w * cols + pad * (cols - 1)

    menu_w = max((_FONT_S.size(label)[0] for label, _ in menu_items), default=0) + 40
    title_w = _FONT_M.size("Controls")[0]
    w = max(controls_w, menu_w, title_w) + pad * 2

    menu_h = (26 * len(menu_items) + 30) if menu_items else 0
    controls_h = 26 + rows_per_col * 20
    note_lines = _wrap_lines(_FONT_S, HELP_NOTE, w - pad * 2) or [""]
    h = menu_h + (14 if menu_items else 0) + controls_h + 6 + len(note_lines) * 16 + pad * 2

    x = C.SCREEN_W // 2 - w // 2
    y = min(max(20, C.SCREEN_H // 2 - h // 2), max(20, C.SCREEN_H - h - 20))
    return x, y, w, h, col_w, rows_per_col, menu_h, note_lines


def help_close_button_rect(menu_items=None):
    """Absolute screen rect of the help overlay's X close button, top-right
    corner of the panel - same click-to-close pattern as the bag window/
    friends panel, so the options menu doesn't rely on O/Esc alone."""
    x, y, w, h, *_ = _help_panel_geometry(menu_items)
    return pygame.Rect(x + w - 26, y + 6, 18, 18)


def help_menu_item_rects(menu_items=None):
    """Absolute screen rects for each row of the options overlay's
    interactive menu list (menu_items, (label, action) pairs), mirroring
    the local-space rect draw_help_overlay highlights for the selected row
    - lets the mouse-down handler hit-test a click the same way it already
    does for every other panel's *_rects() helper."""
    menu_items = menu_items or []
    if not menu_items:
        return []
    pad = 16
    x, y, w, h, col_w, rows_per_col, menu_h, note_lines = _help_panel_geometry(menu_items)
    body_y0 = pad
    rects = []
    for i in range(len(menu_items)):
        ly = body_y0 + 30 + i * 26
        rects.append(pygame.Rect(x + pad - 4, y + ly - 2, w - pad * 2 + 8, 24))
    return rects


def draw_help_overlay(surf, menu_items=None, selected_idx=0, mouse_pos=(-1, -1)):
    """A real, centered options menu - RotMG has an actual O-key options screen with
    real settings on it, not just a controls reference; this shows both: an
    interactive Up/Down-navigable list of toggles/actions (menu_items, a list of
    (label, action) pairs) in its own two-column layout, then the full controls
    reference below it in its own two-column grid. Every dimension here is measured
    from the actual text (not a guessed fixed width) and the whole panel is centered
    and clamped to fit the screen, so nothing is ever cut off or runs off-screen
    regardless of resolution or how many menu items are showing that frame - the
    previous version used a fixed 300px-wide side panel that both didn't reliably
    fit its own text and could overflow past the bottom of the screen."""
    pad = 16
    menu_items = menu_items or []
    section_gap = 14
    x, y, w, h, col_w, rows_per_col, menu_h, note_lines = _help_panel_geometry(menu_items)
    panel, _ = _ornate_panel(w, h)

    close = pygame.Rect(w - 26, 6, 18, 18)
    hovered_close = close.collidepoint(mouse_pos[0] - x, mouse_pos[1] - y)
    pygame.draw.rect(panel, (170, 70, 70) if hovered_close else (110, 55, 60), close, border_radius=3)
    pygame.draw.rect(panel, (230, 200, 200), close, width=1, border_radius=3)
    m = 4
    pygame.draw.line(panel, (255, 235, 235), (close.x + m, close.y + m),
                      (close.x + close.w - m, close.y + close.h - m), width=2)
    pygame.draw.line(panel, (255, 235, 235), (close.x + close.w - m, close.y + m),
                      (close.x + m, close.y + close.h - m), width=2)

    body_y0 = pad
    if menu_items:
        mtitle = _FONT_M.render("Menu (Up/Down, Enter)", True, (230, 220, 180))
        panel.blit(mtitle, (pad, body_y0))
        local_mouse = (mouse_pos[0] - x, mouse_pos[1] - y)
        for i, (label, _action) in enumerate(menu_items):
            ly = body_y0 + 30 + i * 26
            row_rect = pygame.Rect(pad - 4, ly - 2, w - pad * 2 + 8, 24)
            selected = i == selected_idx
            hovered = row_rect.collidepoint(local_mouse)
            if selected or hovered:
                fill = (90, 80, 130, 220) if selected else (70, 65, 95, 180)
                pygame.draw.rect(panel, fill, row_rect, border_radius=4)
            color = (255, 235, 170) if selected else (220, 220, 230) if hovered else (200, 200, 215)
            prefix = "> " if selected else "  "
            panel.blit(_FONT_S.render(prefix + label, True, color), (pad, ly))
        body_y0 += menu_h + section_gap
        pygame.draw.line(panel, (90, 90, 105), (pad, body_y0 - section_gap // 2),
                          (w - pad, body_y0 - section_gap // 2), 1)

    title = _FONT_M.render("Controls (O to close)", True, (230, 220, 180))
    panel.blit(title, (pad, body_y0))
    for i, (label, keys) in enumerate(HELP_LINES):
        col, row = divmod(i, rows_per_col)
        lx = pad + col * (col_w + pad)
        ly = body_y0 + 26 + row * 20
        panel.blit(_FONT_S.render(label, True, (190, 190, 205)), (lx, ly))
        keytxt = _FONT_S.render(keys, True, (150, 210, 170))
        panel.blit(keytxt, (lx + col_w - keytxt.get_width(), ly))
    note_y = body_y0 + 26 + rows_per_col * 20 + 6
    for i, line in enumerate(note_lines):
        panel.blit(_FONT_S.render(line, True, (140, 140, 155)), (pad, note_y + i * 16))
    surf.blit(panel, (x, y))


# ------------------------------------------------------------ Echo Keeper --
# The Batch-12 permadeath-currency shop panel - same "Up/Down navigable list,
# geometry factored into its own function so a *_rects() helper can hit-test
# the exact same layout" pattern as the O-key options overlay above.
def _echo_shop_geometry(menu_items=None):
    pad = 16
    menu_items = menu_items or []
    title_bar_h = _FONT_S.get_height() + 8
    content_y0 = 2 + title_bar_h + 4
    menu_w = max((_FONT_S.size(label)[0] for label, _ in menu_items), default=0) + 40
    title_w = _FONT_M.size("Echo Keeper")[0]
    w = max(menu_w, title_w, 260) + pad * 2
    h = content_y0 + 24 + len(menu_items) * 26 + pad
    x = (C.SCREEN_W - w) // 2
    y = (C.SCREEN_H - h) // 2
    return x, y, w, h, content_y0


def echo_shop_close_button_rect(menu_items=None):
    x, y, w, h, _content_y0 = _echo_shop_geometry(menu_items)
    return pygame.Rect(x + w - 26, y + 6, 18, 18)


def echo_shop_menu_item_rects(menu_items=None):
    menu_items = menu_items or []
    x, y, w, h, content_y0 = _echo_shop_geometry(menu_items)
    pad = 16
    body_y0 = content_y0 + 24
    rects = []
    for i in range(len(menu_items)):
        ly = body_y0 + i * 26
        rects.append(pygame.Rect(x + pad - 4, y + ly - 2, w - pad * 2 + 8, 24))
    return rects


def draw_echo_shop_overlay(surf, echoes, menu_items=None, selected_idx=0, mouse_pos=(-1, -1)):
    """menu_items: list of (label, action) pairs, same shape draw_help_overlay
    uses - a static "already owned"/"maxed" row just passes a no-op action."""
    pad = 16
    menu_items = menu_items or []
    x, y, w, h, content_y0 = _echo_shop_geometry(menu_items)
    panel, content_y0 = _ornate_panel(w, h, title="Echo Keeper")

    close = pygame.Rect(w - 26, 6, 18, 18)
    hovered_close = close.collidepoint(mouse_pos[0] - x, mouse_pos[1] - y)
    pygame.draw.rect(panel, (170, 70, 70) if hovered_close else (110, 55, 60), close, border_radius=3)
    pygame.draw.rect(panel, (230, 200, 200), close, width=1, border_radius=3)
    m = 4
    pygame.draw.line(panel, (255, 235, 235), (close.x + m, close.y + m),
                      (close.x + close.w - m, close.y + close.h - m), width=2)
    pygame.draw.line(panel, (255, 235, 235), (close.x + close.w - m, close.y + m),
                      (close.x + m, close.y + close.h - m), width=2)

    balance = _FONT_S.render(f"Echoes: {echoes}", True, (170, 230, 220))
    panel.blit(balance, (pad, content_y0))
    body_y0 = content_y0 + 24
    local_mouse = (mouse_pos[0] - x, mouse_pos[1] - y)
    for i, (label, _action) in enumerate(menu_items):
        ly = body_y0 + i * 26
        row_rect = pygame.Rect(pad - 4, ly - 2, w - pad * 2 + 8, 24)
        selected = i == selected_idx
        hovered = row_rect.collidepoint(local_mouse)
        if selected or hovered:
            fill = (90, 80, 130, 220) if selected else (70, 65, 95, 180)
            pygame.draw.rect(panel, fill, row_rect, border_radius=4)
        color = (255, 235, 170) if selected else (220, 220, 230) if hovered else (200, 200, 215)
        prefix = "> " if selected else "  "
        panel.blit(_FONT_S.render(prefix + label, True, color), (pad, ly))
    surf.blit(panel, (x, y))


def draw_item_feed(surf, messages):
    y = 90
    for msg, color, t in messages:
        alpha = min(255, int(255 * min(1.0, t)))
        txt = _FONT_M.render(msg, True, color)
        shadow = _FONT_M.render(msg, True, (0, 0, 0))
        holder = pygame.Surface((txt.get_width() + 2, txt.get_height() + 2), pygame.SRCALPHA)
        holder.blit(shadow, (1, 2))
        holder.blit(txt, (0, 0))
        holder.set_alpha(alpha)
        surf.blit(holder, (C.SCREEN_W // 2 - txt.get_width() // 2, y))
        y += 26


NEARBY_LOOT_MAX = 5


def draw_nearby_loot_panel(surf, ground_items):
    """RotMG's "proximity menu": while a bag is nearby, show what's actually inside
    it - instead of finding out only after an automatic pickup - bottom-right,
    above the movement hint line. No auto-collect: right-click to open one."""
    items = ground_items[:NEARBY_LOOT_MAX]
    if not items:
        return
    pad = 8
    line_h = 20
    w = 250
    h = 22 + line_h * len(items) + pad
    # bottom-LEFT, not the right dock - the right side is fully occupied by the
    # player panel/equip/backpack grid now, so the proximity-loot panel goes where
    # the old top-left HP/stat readout used to be
    x = 12
    y = C.SCREEN_H - h - 34
    panel, _ = _ornate_panel(w, h)
    title = _FONT_S.render("Nearby (right-click to open)", True, (220, 200, 150))
    panel.blit(title, (pad, 6))
    for i, g in enumerate(items):
        ly = 22 + i * line_h
        pygame.draw.rect(panel, g.bag_color, (pad, ly + 3, 10, 10), border_radius=2)
        bag_items = getattr(g, "items", None)
        if bag_items is not None:
            count = len(bag_items)
            name = bag_items[0].display_name if count == 1 else f"Bag ({count} items)"
            color = bag_items[0].color if count == 1 else g.bag_color
        else:
            count = getattr(g, "count", 1)
            base_name = getattr(g, "name", "Item")
            name = base_name if count == 1 else f"{base_name} +{count - 1} more"
            color = getattr(g, "tier_color", (210, 210, 210))
        txt = _FONT_S.render(name, True, color)
        panel.blit(txt, (pad + 16, ly))
    surf.blit(panel, (x, y))


BAG_WINDOW_COLS = 4
BAG_WINDOW_PAD = 10


def bag_slot_rects(bag_screen_pos):
    """Slot rects for an open bag's window, anchored near the bag's on-screen
    position (clamped to stay fully on-screen) - up to BAG_CAPACITY (8) slots,
    4 wide x 2 tall, matching the Vault's per-chest grid layout."""
    rows = (BAG_CAPACITY + BAG_WINDOW_COLS - 1) // BAG_WINDOW_COLS
    w = BAG_WINDOW_COLS * (SLOT_SIZE + SLOT_GAP) - SLOT_GAP + BAG_WINDOW_PAD * 2
    h = rows * (SLOT_SIZE + SLOT_GAP) - SLOT_GAP + BAG_WINDOW_PAD * 2 + 26
    x = min(max(0, bag_screen_pos[0] - w // 2), C.SCREEN_W - w)
    y = min(max(0, bag_screen_pos[1] - h - 20), C.SCREEN_H - h)
    rects = []
    for i in range(BAG_CAPACITY):
        col, row = i % BAG_WINDOW_COLS, i // BAG_WINDOW_COLS
        rects.append(pygame.Rect(x + BAG_WINDOW_PAD + col * (SLOT_SIZE + SLOT_GAP),
                                  y + BAG_WINDOW_PAD + 26 + row * (SLOT_SIZE + SLOT_GAP), SLOT_SIZE, SLOT_SIZE))
    return rects


def bag_window_close_button_rect(bag_screen_pos):
    rects = bag_slot_rects(bag_screen_pos)
    x0, y0 = rects[0].x - BAG_WINDOW_PAD, rects[0].y - BAG_WINDOW_PAD - 26
    w = BAG_WINDOW_COLS * (SLOT_SIZE + SLOT_GAP) - SLOT_GAP + BAG_WINDOW_PAD * 2
    return pygame.Rect(x0 + w - 22, y0 + 4, 18, 18)


def draw_bag_window(surf, bag_screen_pos, items, mouse_pos, dragging_from=None):
    """A small floating drag-and-drop window for an opened ground Bag - modeled on
    the Vault's slot-grid layout but anchored near the bag itself, not a full-page
    takeover. `dragging_from` matches main.py's drag_from convention: skip drawing
    whichever ("bag", idx) slot is currently being dragged so it isn't shown twice.
    Bag -> backpack/equip only (you can't drag items back into someone's loot bag) -
    a plain click still does a quick take, matching the backpack's own convenience click."""
    rects = bag_slot_rects(bag_screen_pos)
    rows = (BAG_CAPACITY + BAG_WINDOW_COLS - 1) // BAG_WINDOW_COLS
    w = BAG_WINDOW_COLS * (SLOT_SIZE + SLOT_GAP) - SLOT_GAP + BAG_WINDOW_PAD * 2
    h = rows * (SLOT_SIZE + SLOT_GAP) - SLOT_GAP + BAG_WINDOW_PAD * 2 + 26
    x0, y0 = rects[0].x - BAG_WINDOW_PAD, rects[0].y - BAG_WINDOW_PAD - 26
    panel, _ = _ornate_panel(w, h)
    label = _FONT_S.render(f"Bag - {len(items)}/{BAG_CAPACITY}", True, (220, 200, 160))
    panel.blit(label, (BAG_WINDOW_PAD, 6))
    close = pygame.Rect(w - 22, 4, 18, 18)
    hovered_close = close.collidepoint(mouse_pos[0] - x0, mouse_pos[1] - y0)
    pygame.draw.rect(panel, (170, 70, 70) if hovered_close else (110, 55, 60), close, border_radius=3)
    pygame.draw.rect(panel, (230, 200, 200), close, width=1, border_radius=3)
    m = 4
    pygame.draw.line(panel, (255, 235, 235), (close.x + m, close.y + m),
                      (close.x + close.w - m, close.y + close.h - m), width=2)
    pygame.draw.line(panel, (255, 235, 235), (close.x + close.w - m, close.y + m),
                      (close.x + m, close.y + close.h - m), width=2)
    surf.blit(panel, (x0, y0))

    hovered = None
    for i, rect in enumerate(rects):
        show = i < len(items) and dragging_from != ("bag", i)
        _slot_frame(surf, rect, filled=show, hovered=rect.collidepoint(mouse_pos), border=False)
        if show:
            it = items[i]
            icon = sprites.item_icon(it.color, it.shape)
            surf.blit(pygame.transform.smoothscale(icon, (SLOT_SIZE - 6, SLOT_SIZE - 6)), (rect.x + 3, rect.y + 3))
            _tier_badge(surf, rect, it)
            if rect.collidepoint(mouse_pos):
                hovered = it
    if hovered is not None:
        _tooltip(surf, mouse_pos, hovered)


CHAT_BOX_MAX_VISIBLE = 40


def draw_chat_box(surf, buffer, selected=False):
    """The Enter-to-type chat input pop-up - a small, self-contained box near the
    bottom of the screen rather than a full-width bar, so it stays out of the way
    of the play area above it. `selected`: Ctrl+A was pressed - the whole buffer is
    "selected" (this input has no partial-selection model), shown the same way a
    real text field would: an inverted highlight bar behind the text, so Ctrl+C/X
    or typing-to-replace has a visible "yes, this is what's selected" cue."""
    w, h = 340, 34
    x = C.SCREEN_W // 2 - w // 2
    y = C.SCREEN_H - h - 46
    box, _ = _ornate_panel(w, h)
    shown = buffer[-CHAT_BOX_MAX_VISIBLE:]
    cursor = "_" if (pygame.time.get_ticks() // 400) % 2 == 0 else ""
    prefix = _FONT_M.render("> ", True, (235, 235, 245))
    text_x = 10 + prefix.get_width()
    text_y = h // 2 - prefix.get_height() // 2
    box.blit(prefix, (10, text_y))
    if selected and shown:
        body = _FONT_M.render(shown, True, (20, 20, 28))
        highlight = pygame.Rect(text_x - 2, text_y - 1, body.get_width() + 4, body.get_height() + 2)
        pygame.draw.rect(box, (180, 200, 255, 255), highlight, border_radius=2)
        box.blit(body, (text_x, text_y))
        cursor_x = text_x + body.get_width()
    else:
        body = _FONT_M.render(shown, True, (235, 235, 245))
        box.blit(body, (text_x, text_y))
        cursor_x = text_x + body.get_width()
    if cursor:
        box.blit(_FONT_M.render(cursor, True, (235, 235, 245)), (cursor_x, text_y))
    surf.blit(box, (x, y))
    hint_text = ("Selected - Ctrl+C copy, Ctrl+X cut, or type to replace" if selected else
                 "Enter to send  |  /nexus /realm /vault /bazaar /trade  |  Esc to cancel")
    hint = _FONT_S.render(hint_text, True, (200, 210, 255) if selected else (160, 160, 175))
    surf.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, y + h + 4))


CHAT_LOG_STORE_CAP = 60   # how many messages are kept in memory at all (2 minutes of expiry
                           # naturally bounds this further - see CHAT_LOG_LIFETIME in main.py/coop_client.py)
CHAT_LOG_VISIBLE_LINES = 14  # how many wrapped lines fit in the panel without scrolling
CHAT_LOG_WRAP_WIDTH = 300
CHAT_LOG_FADE_IN = 0.35  # seconds - only the newest line fades in, older ones sit static
CHAT_LOG_SCROLLBAR_W = 8


def _chat_log_flatten(messages):
    """[(name_surf_or_None, line_text, msg_idx), ...] - one entry per WRAPPED line
    across every stored message; a message's own name label only renders on its
    first wrapped line, later ones get None (no repeated name)."""
    flat = []
    for i, m in enumerate(messages):
        name_surf = _FONT_S.render(f"{m['name']}:", True, (150, 200, 255))
        lines = _wrap_lines(_FONT_S, m["text"], CHAT_LOG_WRAP_WIDTH - name_surf.get_width() - 6) or [""]
        for j, line in enumerate(lines):
            flat.append((name_surf if j == 0 else None, line, i))
    return flat


def chat_log_max_scroll(messages):
    """How far (in wrapped-line units) the log can be scrolled up - 0 means
    everything already fits without scrolling."""
    return max(0, len(_chat_log_flatten(messages)) - CHAT_LOG_VISIBLE_LINES)


def chat_log_rect(messages):
    """Screen rect of the chat log panel, for click-to-open/scroll hit-testing -
    mirrors draw_chat_log's own geometry exactly, including a minimal clickable
    zone when there are no messages yet, so clicking the log opens chat even
    before anyone's said anything."""
    pad = 8
    line_h = 18
    n = min(len(_chat_log_flatten(messages)), CHAT_LOG_VISIBLE_LINES) if messages else 1
    h = pad * 2 + max(1, n) * line_h
    w = CHAT_LOG_WRAP_WIDTH + pad * 2 + CHAT_LOG_SCROLLBAR_W
    x, y = 12, C.SCREEN_H // 2 - h // 2
    return pygame.Rect(x, y, w, h)


def draw_chat_log(surf, messages, scroll=0):
    """Persistent left-side chat history, separate from the top-of-screen item feed
    (which is pickups/equips/errors, not chat) and from in-world speech bubbles
    (which are ephemeral and per-speaker). Time-based expiry (CHAT_LOG_LIFETIME,
    2 minutes) plus a generous CHAT_LOG_STORE_CAP happen upstream in main.py/
    coop_client.py; this only ever shows a CHAT_LOG_VISIBLE_LINES-tall window of
    whatever's currently stored, scrollable via `scroll` (a line-count offset
    from the newest line, 0 = pinned to the bottom) with a scrollbar when there's
    more history than fits."""
    if not messages:
        return
    pad = 8
    line_h = 18
    flat = _chat_log_flatten(messages)
    total_lines = len(flat)
    max_scroll = max(0, total_lines - CHAT_LOG_VISIBLE_LINES)
    scroll = max(0, min(scroll, max_scroll))
    visible_n = min(total_lines, CHAT_LOG_VISIBLE_LINES)
    start = total_lines - visible_n - scroll
    window = flat[start:start + visible_n]

    h = pad * 2 + visible_n * line_h
    w = CHAT_LOG_WRAP_WIDTH + pad * 2 + CHAT_LOG_SCROLLBAR_W
    x, y = 12, C.SCREEN_H // 2 - h // 2
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    panel.fill((12, 12, 18, 140))
    pygame.draw.rect(panel, (*CHROME_GOLD, 140), (0, 0, w, h), width=1, border_radius=6)
    pygame.draw.rect(panel, (*CHROME_INSET_HILITE, 12), (1, 1, w - 2, h - 2), width=1, border_radius=5)

    newest_idx = len(messages) - 1
    cy = pad
    for name_surf, line, msg_idx in window:
        alpha = 235
        if msg_idx == newest_idx and scroll == 0:
            frac = min(1.0, messages[msg_idx].get("age", 999.0) / CHAT_LOG_FADE_IN)
            alpha = int(235 * frac)
        line_x = pad
        if name_surf is not None:
            holder = name_surf.copy()
            holder.set_alpha(alpha)
            panel.blit(holder, (line_x, cy))
            line_x += name_surf.get_width() + 6
        txt = _FONT_S.render(line, True, (225, 225, 235))
        holder2 = pygame.Surface(txt.get_size(), pygame.SRCALPHA)
        holder2.blit(txt, (0, 0))
        holder2.set_alpha(alpha)
        panel.blit(holder2, (line_x, cy))
        cy += line_h

    if max_scroll > 0:
        track_x = w - CHAT_LOG_SCROLLBAR_W - 2
        track_rect = pygame.Rect(track_x, pad, CHAT_LOG_SCROLLBAR_W, h - pad * 2)
        pygame.draw.rect(panel, (40, 40, 50, 180), track_rect, border_radius=3)
        thumb_h = max(14, int(track_rect.h * visible_n / total_lines))
        scroll_frac = scroll / max_scroll
        thumb_y = track_rect.y + int((track_rect.h - thumb_h) * (1 - scroll_frac))
        pygame.draw.rect(panel, (*CHROME_GOLD, 220), (track_x, thumb_y, CHAT_LOG_SCROLLBAR_W, thumb_h),
                          border_radius=3)
    surf.blit(panel, (x, y))


# ------------------------------------------------------------------ trading --
# RotMG-style trade window: type /trade near another player, drag items from
# your backpack into your side, both hit Accept, then a short confirmation
# countdown (any change resets it) before the swap actually happens - see
# server.py's Trade/_tick_trades for the authoritative side of this.
TRADE_PANEL_W, TRADE_PANEL_H = 520, 280
TRADE_SLOT_SIZE = 32
TRADE_SLOT_GAP = 4
TRADE_MAX_SLOTS = 8


def _trade_panel_origin():
    return (C.SCREEN_W // 2 - TRADE_PANEL_W // 2, C.SCREEN_H // 2 - TRADE_PANEL_H // 2)


def trade_offer_slot_rects(mine=True):
    """Screen-space rects for one side's offered-item grid (up to 8 slots) -
    used both to draw and to hit-test clicks (click an offered item to withdraw it)."""
    x0, y0 = _trade_panel_origin()
    col_x0 = x0 + 20 if mine else x0 + TRADE_PANEL_W // 2 + 20
    rects = []
    for i in range(TRADE_MAX_SLOTS):
        row, col = divmod(i, 4)
        rx = col_x0 + col * (TRADE_SLOT_SIZE + TRADE_SLOT_GAP)
        ry = y0 + 70 + row * (TRADE_SLOT_SIZE + TRADE_SLOT_GAP)
        rects.append(pygame.Rect(rx, ry, TRADE_SLOT_SIZE, TRADE_SLOT_SIZE))
    return rects


def trade_accept_button_rect():
    x0, y0 = _trade_panel_origin()
    return pygame.Rect(x0 + 20, y0 + TRADE_PANEL_H - 40, 130, 30)


def trade_cancel_button_rect():
    x0, y0 = _trade_panel_origin()
    return pygame.Rect(x0 + TRADE_PANEL_W - 150, y0 + TRADE_PANEL_H - 40, 130, 30)


def draw_trade_panel(surf, trade, you_name="You", mouse_pos=(-1, -1)):
    """trade: the server's per-viewer trade dict (see server._trade_info_for) -
    other_name/my_offer/their_offer/my_accept/their_accept/timer."""
    from game.items import Item
    x0, y0 = _trade_panel_origin()
    local_mouse = (mouse_pos[0] - x0, mouse_pos[1] - y0)
    panel, _ = _ornate_panel(TRADE_PANEL_W, TRADE_PANEL_H)
    title = _FONT_M.render(f"Trading with {trade['other_name']}", True, (230, 210, 150))
    panel.blit(title, (TRADE_PANEL_W // 2 - title.get_width() // 2, 10))
    pygame.draw.line(panel, (90, 90, 105), (TRADE_PANEL_W // 2, 40), (TRADE_PANEL_W // 2, TRADE_PANEL_H - 50), 1)

    mine_ok, their_ok = trade["my_accept"], trade["their_accept"]
    mine_label = _FONT_S.render(f"{you_name} ({'accepted' if mine_ok else 'offering'})", True,
                                 (140, 230, 150) if mine_ok else (200, 200, 210))
    panel.blit(mine_label, (20, 46))
    their_label = _FONT_S.render(f"{trade['other_name']} ({'accepted' if their_ok else 'offering'})", True,
                                  (140, 230, 150) if their_ok else (200, 200, 210))
    panel.blit(their_label, (TRADE_PANEL_W // 2 + 20, 46))

    hovered_item = None
    for items, mine in ((trade["my_offer"], True), (trade["their_offer"], False)):
        col_x0 = 20 if mine else TRADE_PANEL_W // 2 + 20
        for i in range(TRADE_MAX_SLOTS):
            row, col = divmod(i, 4)
            rx = col_x0 + col * (TRADE_SLOT_SIZE + TRADE_SLOT_GAP)
            ry = 70 + row * (TRADE_SLOT_SIZE + TRADE_SLOT_GAP)
            slot_rect = pygame.Rect(rx, ry, TRADE_SLOT_SIZE, TRADE_SLOT_SIZE)
            if i < len(items):
                # a staged/offered item gets a soft yellow background - visually
                # confirms "this is what will be traded," separate from the
                # green "accepted" label above (which is about the WHOLE offer)
                pygame.draw.rect(panel, (110, 95, 30), slot_rect.inflate(2, 2), border_radius=3)
            _slot_frame(panel, slot_rect, filled=i < len(items), border=False)
            if i < len(items):
                it = Item.from_json(items[i])
                icon = pygame.transform.smoothscale(sprites.item_icon(it.color, it.shape),
                                                     (TRADE_SLOT_SIZE - 6, TRADE_SLOT_SIZE - 6))
                panel.blit(icon, (rx + 3, ry + 3))
                _tier_badge(panel, pygame.Rect(rx, ry, TRADE_SLOT_SIZE, TRADE_SLOT_SIZE), it)
                if slot_rect.collidepoint(local_mouse):
                    hovered_item = it

    if trade.get("timer") is not None:
        t_txt = _FONT_M.render(f"Confirming in {trade['timer']:.1f}s...", True, (255, 220, 120))
        panel.blit(t_txt, (TRADE_PANEL_W // 2 - t_txt.get_width() // 2, TRADE_PANEL_H - 108))

    hint = _FONT_S.render("Click backpack to offer, an offered item to withdraw it", True, (150, 150, 165))
    panel.blit(hint, (TRADE_PANEL_W // 2 - hint.get_width() // 2, TRADE_PANEL_H - 80))

    accept_rect = pygame.Rect(20, TRADE_PANEL_H - 40, 130, 30)
    _bevel_button(panel, accept_rect, (60, 140, 70) if mine_ok else (45, 90, 55),
                  hovered=accept_rect.collidepoint(local_mouse))
    at = _FONT_S.render("Accepted" if mine_ok else "Accept", True, (230, 255, 230))
    panel.blit(at, (accept_rect.centerx - at.get_width() // 2, accept_rect.centery - at.get_height() // 2))

    cancel_rect = pygame.Rect(TRADE_PANEL_W - 150, TRADE_PANEL_H - 40, 130, 30)
    _bevel_button(panel, cancel_rect, (140, 55, 55), hovered=cancel_rect.collidepoint(local_mouse))
    ct = _FONT_S.render("Cancel", True, (255, 220, 220))
    panel.blit(ct, (cancel_rect.centerx - ct.get_width() // 2, cancel_rect.centery - ct.get_height() // 2))
    surf.blit(panel, (x0, y0))
    if hovered_item is not None:
        _tooltip(surf, mouse_pos, hovered_item)


SPEECH_BUBBLE_LIFETIME = 4.0
SPEECH_BUBBLE_MAX_LINES = 10   # long enough for effectively any normal chat message
SPEECH_BUBBLE_WRAP_WIDTH = 240  # px
MOB_SPEECH_COLOR = (200, 170, 20)  # yellow - mob flavor lines never show a name label,
                                    # this is the only visual cue that it's a mob talking


def _wrap_lines(font, text, max_width):
    """Greedy word-wrap - breaks on spaces, measuring real glyph width via
    font.size() rather than a fixed char-count guess (so it wraps correctly
    regardless of font/message content)."""
    words = text.split(" ")
    lines = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if not cur or font.size(trial)[0] <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_speech_bubble(surf, cam, world_pos, text, age, name=None, text_color=(20, 20, 24)):
    """A little chat bubble above a player's/mob's head - RotMG-style, so nearby
    chat (or a mob's flavor line) reads as something happening in the world, not
    just a scrolling log. Real word-wrap up to SPEECH_BUBBLE_MAX_LINES (previously
    a hard 48-char single-line cut - the tightest limit in the whole chat pipeline,
    well below even the old 140-char input cap) with a trailing "..." only in the
    pathological case of a message still overflowing that many lines. `name`, if
    given, renders as a small label above the message body - mob flavor lines pass
    name=None (never identify the speaker) and a yellow `text_color` instead."""
    frac = age / SPEECH_BUBBLE_LIFETIME
    if frac >= 1.0:
        return
    alpha = 255 if frac < 0.8 else max(0, int(255 * (1 - frac) / 0.2))
    px, py = cam(world_pos)
    lines = _wrap_lines(_FONT_S, text, SPEECH_BUBBLE_WRAP_WIDTH)
    if len(lines) > SPEECH_BUBBLE_MAX_LINES:
        lines = lines[:SPEECH_BUBBLE_MAX_LINES]
        lines[-1] = lines[-1].rstrip() + "..."
    line_surfs = [_FONT_S.render(line, True, text_color) for line in lines] or [_FONT_S.render("", True, (0, 0, 0))]
    name_surf = _FONT_S.render(name, True, (100, 70, 150)) if name else None
    pad = 6
    content_w = max(s.get_width() for s in line_surfs + ([name_surf] if name_surf else []))
    line_h = line_surfs[0].get_height()
    name_h = name_surf.get_height() + 2 if name_surf else 0
    w = content_w + pad * 2
    h = name_h + line_h * len(line_surfs) + pad * 2
    bx, by = px - w // 2, py - 46 - h
    bubble = pygame.Surface((w, h + 6), pygame.SRCALPHA)
    pygame.draw.rect(bubble, (240, 240, 235, alpha), (0, 0, w, h), border_radius=8)
    pygame.draw.polygon(bubble, (240, 240, 235, alpha), [(w // 2 - 6, h), (w // 2 + 6, h), (w // 2, h + 6)])
    holder = pygame.Surface((w, h), pygame.SRCALPHA)
    y = pad
    if name_surf:
        holder.blit(name_surf, (pad, y))
        y += name_h
    for s in line_surfs:
        holder.blit(s, (pad, y))
        y += line_h
    holder.set_alpha(alpha)
    bubble.blit(holder, (0, 0))
    surf.blit(bubble, (bx, by))


PORTAL_DIFFICULTY_COLORS = {"Easy": (120, 220, 120), "Medium": (230, 200, 80), "Hard": (230, 90, 90)}
# A readiness signpost so players self-select instead of guessing blind -
# echoes ROTMG's own real "Combat Power" rework, kept here as a simple
# static suggestion per BONUS_DIFFICULTIES tier rather than a live gear-score
# calculation (that's a much bigger system than a portal label needs).
PORTAL_DIFFICULTY_SUGGESTED_LEVEL = {"Easy": "Lv 1+", "Medium": "Lv 8+", "Hard": "Lv 15+"}


def draw_portal_label(surf, cam, portal):
    """A small floating label above a portal - either a Dungeon-Shard-opened
    portal's rolled difficulty (Easy/Medium/Hard, color-coded), or an island
    hub portal's name (see entities.Portal.label, "The Reforging" storyline) -
    so the player knows what they're stepping into before entering, instead
    of a hidden roll/destination on arrival. No-ops for a portal with
    neither (entrance/realm_exit/phase2 portals carry neither)."""
    text, color = None, (220, 220, 220)
    if getattr(portal, "difficulty", None):
        suggested = PORTAL_DIFFICULTY_SUGGESTED_LEVEL.get(portal.difficulty)
        text = f"{portal.difficulty} ({suggested})" if suggested else portal.difficulty
        color = PORTAL_DIFFICULTY_COLORS.get(portal.difficulty, color)
    elif getattr(portal, "label", None):
        text = portal.label
        color = (255, 225, 150)
    if not text:
        return
    px, py = cam(portal.pos)
    label = _FONT_S.render(text, True, color)
    shadow = _FONT_S.render(text, True, (0, 0, 0))
    lx, ly = px - label.get_width() // 2, py - 34
    surf.blit(shadow, (lx + 1, ly + 1))
    surf.blit(label, (lx, ly))


def _portal_label_text(portal):
    if getattr(portal, "difficulty", None):
        suggested = PORTAL_DIFFICULTY_SUGGESTED_LEVEL.get(portal.difficulty)
        text = f"{portal.difficulty} ({suggested})" if suggested else portal.difficulty
        return text, PORTAL_DIFFICULTY_COLORS.get(portal.difficulty, (220, 220, 220))
    if getattr(portal, "label", None):
        return portal.label, (255, 225, 150)
    return None, None


def draw_portal_labels(surf, cam, portals):
    """Draws every portal's floating label with greedy vertical-stagger
    collision avoidance between them. draw_portal_label() (singular, above)
    places every label at a fixed -34px offset with zero awareness of any
    OTHER portal's label - fine when portals are far apart, but confirmed to
    genuinely overlap at the island-hub portal ring (10 portals ~119px apart
    on screen, several island names render 130-155px wide at this font) and
    anywhere else portals happen to cluster. Portals are processed left-to-
    right (by screen x) for a deterministic frame-to-frame stagger order;
    each label that would collide with an already-placed one this frame gets
    pushed one more line-height higher, repeating until it's clear."""
    entries = []
    for pt in portals:
        text, color = _portal_label_text(pt)
        if text:
            entries.append((pt, text, color))
    entries.sort(key=lambda e: cam(e[0].pos)[0])
    placed_rects = []
    for pt, text, color in entries:
        px, py = cam(pt.pos)
        label = _FONT_S.render(text, True, color)
        w, h = label.get_size()
        base_y = py - 34
        rect = pygame.Rect(px - w // 2, base_y, w, h)
        step = 0
        while any(rect.colliderect(r) for r in placed_rects):
            step += 1
            rect.y = base_y - step * (h + 2)
        placed_rects.append(rect)
        shadow = _FONT_S.render(text, True, (0, 0, 0))
        surf.blit(shadow, (rect.x + 1, rect.y + 1))
        surf.blit(label, (rect.x, rect.y))


CLASS_ORDER = ["wizard", "archer", "warrior", "priest", "rogue", "necromancer", "paladin", "assassin"]
_CLASS_COLS = 4


STAT_KEYS = [("att", "ATT", (230, 90, 90)), ("deF", "DEF", (110, 170, 230)),
             ("spd", "SPD", (120, 220, 140)), ("dex", "DEX", (230, 200, 80)),
             ("vit", "VIT", (230, 130, 220)), ("wis", "WIS", (150, 130, 230))]
_STAT_MAX = 40  # normalization ceiling for the class-select comparison bars


def class_select_tile_rects():
    """[(rect, class_name), ...] for each class portrait tile - shared by
    draw_class_select's own rendering and main.py's/coop_client.py's mouse
    hit-testing, matching the same *_rects() pattern every other clickable
    panel in this file already uses (vault/friends/nearby-players/etc.)."""
    y0 = 110
    col_w = 170
    row_h = 110
    x0 = C.SCREEN_W // 2 - (col_w * _CLASS_COLS) // 2
    rects = []
    for i, cls in enumerate(CLASS_ORDER):
        col, row = i % _CLASS_COLS, i // _CLASS_COLS
        x = x0 + col * col_w
        y = y0 + row * row_h
        rects.append((pygame.Rect(x - 8, y - 8, 72, 72), cls))
    return rects


def draw_class_select(surf, selected_idx, mouse_pos=(-1, -1)):
    title = _FONT_L.render("CHOOSE YOUR CLASS", True, C.COL_WHITE)
    surf.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 24))
    sub = _FONT_S.render("Click or use arrow keys to pick, Enter/click to confirm", True, (190, 190, 200))
    surf.blit(sub, (C.SCREEN_W // 2 - sub.get_width() // 2, 60))
    from game.entities import CLASS_DESC, CLASS_BASE
    tile_rects = class_select_tile_rects()
    for i, (rect, cls) in enumerate(tile_rects):
        selected = i == selected_idx
        hovered = rect.collidepoint(mouse_pos)
        color = C.COL_XP if selected else (150, 150, 160)
        img = sprites.player_sprite(cls)
        _slot_frame(surf, rect, filled=True, accent=CHROME_GOLD if selected else None, hovered=hovered)
        surf.blit(pygame.transform.smoothscale(img, (56, 56)), (rect.x + 8, rect.y + 8))
        label = _FONT_M.render(cls.title(), True, color)
        surf.blit(label, (rect.x + 8 + 28 - label.get_width() // 2, rect.y + 8 + 60))

    sel_cls = CLASS_ORDER[selected_idx]
    base = CLASS_BASE[sel_cls]
    bar_w, bar_h, gap = 130, 12, 6
    total_w = len(STAT_KEYS) * (bar_w + gap) - gap
    panel_w = total_w + 32
    panel_y = max(r.bottom for r, _ in tile_rects) + 10
    panel_h = 100
    panel, _ = _ornate_panel(panel_w, panel_h)
    surf.blit(panel, (C.SCREEN_W // 2 - panel_w // 2, panel_y))

    desc = _FONT_S.render(CLASS_DESC[sel_cls], True, (200, 200, 210))
    surf.blit(desc, (C.SCREEN_W // 2 - desc.get_width() // 2, panel_y + 10))

    bx0 = C.SCREEN_W // 2 - total_w // 2
    by = panel_y + 38
    for i, (key, label, color) in enumerate(STAT_KEYS):
        bx = bx0 + i * (bar_w + gap)
        val = base[key]
        lbl = _FONT_S.render(f"{label} {val}", True, (200, 200, 210))
        surf.blit(lbl, (bx, by))
        _bar(surf, bx, by + 18, bar_w, bar_h, val / _STAT_MAX, color, (40, 40, 46))
    hp_mp = _FONT_S.render(f"HP {base['hp']}   MP {base['mp']}", True, (170, 170, 185))
    surf.blit(hp_mp, (C.SCREEN_W // 2 - hp_mp.get_width() // 2, by + 40))


# ---------------------------------------------------------------- vault --
def backpack_slot_rects(player):
    """4-wide grid right below the (single-row) equip grid, same right-docked column."""
    x1 = _dock_right_x()
    y0 = _dock_top_y() + (SLOT_SIZE + SLOT_GAP) + 14  # below the 1-row equip grid + a gap
    rects = []
    for i in range(player.backpack_size):
        col, row = i % BACKPACK_COLS, i // BACKPACK_COLS
        x = x1 - (BACKPACK_COLS - col) * (SLOT_SIZE + SLOT_GAP) + SLOT_GAP
        y = y0 + row * (SLOT_SIZE + SLOT_GAP)
        rects.append(pygame.Rect(x, y, SLOT_SIZE, SLOT_SIZE))
    return rects


def draw_quest_panel(surf, secret_quest, progress, timer, secret_quest_target=0, phase2_quest=None,
                      phase2_progress=0, phase2_timer=0.0, phase2_quest_target=0):
    """Top-right HUD tracker for a dungeon's active quests: the optional "???"
    secret quest (see realm_sim.SECRET_QUEST_KINDS) and the always-on phase-2-
    access quest (see realm_sim.PHASE2_QUEST_KIND) - stacked if both are
    active at once, each with its own progress bar (previous version was two
    bare lines of text, buried low in the right-docked minimap/player-panel/
    backpack stack; this now docks to its OWN slot immediately left of the
    corner minimap, top-aligned with it, so it can't collide with that stack
    regardless of how many quest rows are showing). Takes plain values (not a
    RealmSim) so co-op can feed it straight from the snapshot without needing
    a duck-typed stand-in object."""
    from game.realm_sim import SECRET_QUEST_KINDS, PHASE2_QUEST_LABEL
    from game import minimap as _mm

    entries = []  # [(title, progress_text, frac, bar_color)]
    if secret_quest:
        cfg = SECRET_QUEST_KINDS.get(secret_quest)
        if cfg is not None:
            if secret_quest == "boss_timer":
                target = cfg["time_limit"]
                frac = max(0.0, min(1.0, timer / target)) if target else 0.0
                prog_text = f"{max(0, int(timer))}s left"
            else:
                # kill_totems' target (TOTEM_COUNT) is a fixed dict value; kill_goons'
                # is per-instance dynamic (see _pick_achievable_goon_target) and passed
                # in explicitly since it can't be guessed from the quest kind alone
                target = cfg.get("target") or secret_quest_target or 1
                frac = max(0.0, min(1.0, progress / target)) if target else 0.0
                prog_text = f"{progress}/{target}"
            entries.append(("??? " + cfg["label"], prog_text, frac, (190, 130, 230)))
    if phase2_quest:
        target = phase2_quest_target or 1
        frac = max(0.0, min(1.0, phase2_progress / target))
        entries.append((PHASE2_QUEST_LABEL, f"{phase2_progress}/{target}", frac, (230, 130, 90)))
    if not entries:
        return

    pad, bar_h, row_gap = 10, 7, 8
    w = 230
    row_h = _FONT_S.get_height() + 4 + bar_h
    h = 8 + len(entries) * row_h + (len(entries) - 1) * row_gap + 8
    panel, content_y0 = _ornate_panel(w, h, border=(150, 100, 200))
    y = content_y0
    for title, prog_text, frac, color in entries:
        title_s = _FONT_S.render(title, True, (225, 215, 235))
        prog_s = _FONT_S.render(prog_text, True, (205, 200, 215))
        panel.blit(title_s, (pad, y))
        panel.blit(prog_s, (w - pad - prog_s.get_width(), y))
        _bar(panel, pad, y + title_s.get_height() + 4, w - pad * 2, bar_h, frac, color, (28, 24, 34))
        y += row_h + row_gap

    mm_x, mm_y = _mm.corner_origin()
    x = mm_x - w - 10
    surf.blit(panel, (x, mm_y))


def _vault_backpack_slot_rects(player):
    """The Vault screen is its own dedicated full-page view (not the live HUD dock),
    so it keeps a simple horizontal row along the bottom independent of wherever the
    in-game inventory dock lives."""
    x0, y0 = 12, C.SCREEN_H - 70
    return [pygame.Rect(x0 + i * (SLOT_SIZE + SLOT_GAP), y0, SLOT_SIZE, SLOT_SIZE) for i in range(player.backpack_size)]


def vault_chest_tab_rects():
    """One tab per chest (RotMG's real vault is a row of separate 8-slot chests you
    flip between, not one giant grid) - click a tab to page to that chest."""
    w, h, gap = 84, 30, 6
    x0, y0 = 12, 130
    return [pygame.Rect(x0 + i * (w + gap), y0, w, h) for i in range(VAULT_CHEST_COUNT)]


def vault_slot_rects(vault_items=None, vault_capacity=None):
    """The CURRENT chest's 8 slots only (4 wide x 2 tall) - always the same fixed
    layout regardless of which chest is selected; the caller offsets by
    selected_chest * VAULT_CHEST_SIZE to get the item's real index in vault_items."""
    x0, y0 = 12, 172
    rects = []
    for i in range(VAULT_CHEST_SIZE):
        col, row = i % 4, i // 4
        rects.append(pygame.Rect(x0 + col * (SLOT_SIZE + 6), y0 + row * (SLOT_SIZE + 6), SLOT_SIZE, SLOT_SIZE))
    return rects


def vault_close_button_rect():
    """A dedicated, always-visible click target to leave the Vault - deliberately NOT
    tied to Enter/Escape (both of those are heavily overloaded elsewhere - chat, menus,
    quitting - and could leave the Vault feeling "stuck" if one of those states lingers)."""
    return pygame.Rect(C.SCREEN_W - 132, 24, 110, 34)



# One distinct "skin" per chest (RotMG's own vault chests are all skinned
# differently) - reuses the exact same 3-rect chest glyph, just recolored,
# so no new art or drawing logic is needed for real visual identity per chest.
VAULT_CHEST_SKINS = [
    (120, 90, 50),    # 0 bronze/wood - the original default look
    (150, 150, 160),  # 1 silver
    (200, 170, 90),   # 2 gold
    (180, 60, 60),    # 3 ruby
    (60, 140, 90),    # 4 emerald
    (70, 100, 190),   # 5 sapphire
    (150, 90, 190),   # 6 amethyst
    (60, 60, 66),     # 7 onyx
    (210, 205, 190),  # 8 pearl
    (190, 110, 60),   # 9 copper
]


def _draw_chest_icon(surf, rect, filled_frac, skin_color=None):
    """A tiny drawn treasure-chest glyph for the vault tabs - RotMG's vault screen
    literally shows a row of chest icons you click between, each its own skin."""
    cx, cy = rect.x + 14, rect.centery
    base = skin_color or VAULT_CHEST_SKINS[0]
    body_col = base if filled_frac > 0 else tuple(max(0, c - 45) for c in base)
    lid_col = tuple(min(255, c + 70) for c in base)
    lock_col = tuple(min(255, c + 100) for c in base)
    pygame.draw.rect(surf, body_col, (cx - 9, cy - 4, 18, 9), border_radius=2)
    pygame.draw.rect(surf, lid_col, (cx - 9, cy - 6, 18, 5), border_radius=2)
    pygame.draw.rect(surf, lock_col, (cx - 2, cy - 5, 4, 3))


def draw_vault_screen(surf, player, vault_items, vault_capacity, mouse_pos, selected_chest=0, dragging_from=None):
    surf.fill((14, 14, 18))
    title = _FONT_L.render("VAULT", True, (220, 210, 240))
    surf.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 30))
    hint = _FONT_S.render("Click a chest tab to page through it - deposits fill the next open chest slot.",
                           True, (170, 170, 180))
    surf.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, 90))

    close_rect = vault_close_button_rect()
    hovered_close = close_rect.collidepoint(mouse_pos)
    pygame.draw.rect(surf, (90, 45, 50) if hovered_close else (70, 35, 40), close_rect, border_radius=6)
    pygame.draw.rect(surf, (220, 140, 140), close_rect, width=2, border_radius=6)
    ct = _FONT_S.render("Close Vault", True, (255, 220, 220))
    surf.blit(ct, (close_rect.centerx - ct.get_width() // 2, close_rect.centery - ct.get_height() // 2))

    hovered = None
    b_label = _FONT_S.render("Backpack", True, (150, 150, 160))
    surf.blit(b_label, (12, C.SCREEN_H - 92))
    for i, rect in enumerate(_vault_backpack_slot_rects(player)):
        _slot_frame(surf, rect, filled=i < len(player.backpack), hovered=rect.collidepoint(mouse_pos), border=False)
        if i < len(player.backpack) and dragging_from != ("backpack", i):
            it = player.backpack[i]
            icon = sprites.item_icon(it.color, it.shape)
            surf.blit(pygame.transform.smoothscale(icon, (SLOT_SIZE - 6, SLOT_SIZE - 6)), (rect.x + 3, rect.y + 3))
            _tier_badge(surf, rect, it)
            if rect.collidepoint(mouse_pos):
                hovered = it

    total_filled = sum(1 for it in vault_items if it is not None)
    v_label = _FONT_S.render(f"Vault - {total_filled}/{vault_capacity} across {VAULT_CHEST_COUNT} chests",
                              True, (150, 150, 160))
    surf.blit(v_label, (12, 108))

    for i, rect in enumerate(vault_chest_tab_rects()):
        lo, hi = i * VAULT_CHEST_SIZE, (i + 1) * VAULT_CHEST_SIZE
        count = sum(1 for it in vault_items[lo:hi] if it is not None)
        selected = i == selected_chest
        skin = VAULT_CHEST_SKINS[i % len(VAULT_CHEST_SKINS)]
        pygame.draw.rect(surf, (48, 40, 60) if selected else (28, 24, 34), rect, border_radius=5)
        pygame.draw.rect(surf, (180, 150, 90) if selected else (80, 70, 60), rect, width=2, border_radius=5)
        _draw_chest_icon(surf, rect, count, skin_color=skin)
        lbl = _FONT_S.render(f"{count}/{VAULT_CHEST_SIZE}", True, (220, 210, 180) if selected else (150, 145, 140))
        surf.blit(lbl, (rect.x + 30, rect.centery - lbl.get_height() // 2))

    lo = selected_chest * VAULT_CHEST_SIZE
    for i, rect in enumerate(vault_slot_rects()):
        idx = lo + i
        it = vault_items[idx] if idx < len(vault_items) else None
        _slot_frame(surf, rect, filled=it is not None, hovered=rect.collidepoint(mouse_pos), border=False)
        if it is not None and dragging_from != ("vault", idx):
            icon = sprites.item_icon(it.color, it.shape)
            surf.blit(pygame.transform.smoothscale(icon, (SLOT_SIZE - 6, SLOT_SIZE - 6)), (rect.x + 3, rect.y + 3))
            _tier_badge(surf, rect, it)
            if rect.collidepoint(mouse_pos):
                hovered = it
    if hovered:
        _tooltip(surf, mouse_pos, hovered)


# --------------------------------------------------------- context menus / social --
CONTEXT_MENU_ROW_H = 28
CONTEXT_MENU_WIDTH = 150
CONTEXT_MENU_TITLE_H = 20


def context_menu_rects(pos, labels):
    """Screen rects for a small vertical popup menu anchored at `pos` (clamped to
    stay fully on-screen) - one rect per label, in order. Used for the right-click
    "player nearby" menu (Chat/Trade/Add Friend)."""
    x = min(pos[0], C.SCREEN_W - CONTEXT_MENU_WIDTH - 4)
    total_h = CONTEXT_MENU_TITLE_H + CONTEXT_MENU_ROW_H * len(labels)
    y = min(pos[1], C.SCREEN_H - total_h - 4)
    return [pygame.Rect(x, y + CONTEXT_MENU_TITLE_H + i * CONTEXT_MENU_ROW_H, CONTEXT_MENU_WIDTH, CONTEXT_MENU_ROW_H)
            for i in range(len(labels))]


def draw_context_menu(surf, pos, title, labels, mouse_pos):
    rects = context_menu_rects(pos, labels)
    if not rects:
        return
    x, y = rects[0].x, rects[0].y - CONTEXT_MENU_TITLE_H
    w = CONTEXT_MENU_WIDTH
    h = CONTEXT_MENU_TITLE_H + CONTEXT_MENU_ROW_H * len(labels)
    panel, _ = _ornate_panel(w, h)
    if title:
        t = _FONT_S.render(title, True, (200, 200, 220))
        panel.blit(t, (8, 3))
    surf.blit(panel, (x, y))
    for rect, label in zip(rects, labels):
        hovered = rect.collidepoint(mouse_pos)
        pygame.draw.rect(surf, (55, 55, 70) if hovered else (32, 32, 42), rect)
        pygame.draw.rect(surf, (90, 90, 110), rect, width=1)
        txt = _FONT_S.render(label, True, (230, 230, 235))
        surf.blit(txt, (rect.x + 8, rect.centery - txt.get_height() // 2))


NEARBY_PLAYERS_MAX = 8


def draw_nearby_players_panel(surf, entries, mouse_pos):
    """`entries`: [(name, dist, pid), ...] sorted nearest-first, already filtered to
    NEARBY_PLAYER_RADIUS by the caller. Lists them with a one-click TP button per
    row. Returns [(row_rect, tp_rect, pid), ...] in absolute screen space, for the
    caller to hit-test clicks against without recomputing this layout."""
    entries = entries[:NEARBY_PLAYERS_MAX]
    if not entries:
        return []
    pad = 6
    row_h = 22
    w = 220
    h = 20 + row_h * len(entries) + pad
    x, y = 12, 150
    panel, _ = _ornate_panel(w, h)
    title = _FONT_S.render("Nearby players", True, (170, 210, 220))
    panel.blit(title, (pad, 4))
    surf.blit(panel, (x, y))
    rows = []
    for i, (name, dist, pid) in enumerate(entries):
        ry = y + 20 + i * row_h
        txt = _FONT_S.render(f"{name} ({int(dist)}px)", True, (220, 220, 225))
        surf.blit(txt, (x + pad, ry + 3))
        tp_rect = pygame.Rect(x + w - 46, ry, 40, row_h - 2)
        hovered = tp_rect.collidepoint(mouse_pos)
        _bevel_button(surf, tp_rect, (60, 90, 70), hovered=hovered, border_radius=3)
        tp_txt = _FONT_S.render("TP", True, (210, 250, 210))
        surf.blit(tp_txt, (tp_rect.centerx - tp_txt.get_width() // 2, tp_rect.centery - tp_txt.get_height() // 2))
        rows.append((pygame.Rect(x, ry, w, row_h), tp_rect, pid))
    return rows


FRIENDS_PANEL_W, FRIENDS_PANEL_H = 340, 380


def friends_panel_rect():
    return pygame.Rect(C.SCREEN_W // 2 - FRIENDS_PANEL_W // 2, C.SCREEN_H // 2 - FRIENDS_PANEL_H // 2,
                        FRIENDS_PANEL_W, FRIENDS_PANEL_H)


def friends_close_button_rect():
    r = friends_panel_rect()
    return pygame.Rect(r.right - 30, r.top + 6, 24, 24)


def draw_friends_panel(surf, friends_status, mouse_pos):
    """`friends_status`: [(name, online_bool, pid_or_None), ...]. TP/Trade only make
    sense while the friend is online (visible in your zone right now) - drawn dimmed
    but Remove always works. Returns [(row_rect, tp_rect, trade_rect, remove_rect,
    name, online), ...] for click hit-testing."""
    r = friends_panel_rect()
    panel, _ = _ornate_panel(r.w, r.h)
    title = _FONT_M.render("Friends", True, (220, 210, 240))
    panel.blit(title, (12, 10))
    close = friends_close_button_rect()
    hovered_close = close.collidepoint(mouse_pos)
    local_close = pygame.Rect(close.x - r.x, close.y - r.y, close.w, close.h)
    pygame.draw.rect(panel, (170, 70, 70) if hovered_close else (110, 55, 60), local_close, border_radius=4)
    m = 5
    pygame.draw.line(panel, (255, 235, 235), (local_close.x + m, local_close.y + m),
                      (local_close.x + local_close.w - m, local_close.y + local_close.h - m), width=2)
    pygame.draw.line(panel, (255, 235, 235), (local_close.x + local_close.w - m, local_close.y + m),
                      (local_close.x + m, local_close.y + local_close.h - m), width=2)
    surf.blit(panel, (r.x, r.y))

    rows = []
    row_h = 34
    y0 = r.y + 46
    if not friends_status:
        hint = _FONT_S.render("No friends yet - right-click a nearby player to add one.", True, (170, 170, 180))
        surf.blit(hint, (r.x + 12, y0))
    for name, online, pid in friends_status:
        ry = y0 + len(rows) * row_h
        if ry + row_h > r.bottom - 8:
            break
        row_rect = pygame.Rect(r.x + 8, ry, r.w - 16, row_h - 4)
        _vgrad(surf, row_rect, (34, 33, 42), (24, 23, 30))
        pygame.draw.rect(surf, (0, 0, 0), row_rect, width=1, border_radius=4)
        color = (150, 230, 150) if online else (150, 150, 155)
        txt = _FONT_S.render(name + (" (here)" if online else " (away)"), True, color)
        surf.blit(txt, (row_rect.x + 6, row_rect.centery - txt.get_height() // 2))
        bw = 48
        tp_rect = pygame.Rect(row_rect.right - bw * 3 - 12, row_rect.y + 2, bw, row_rect.h - 4)
        trade_rect = pygame.Rect(row_rect.right - bw * 2 - 8, row_rect.y + 2, bw, row_rect.h - 4)
        remove_rect = pygame.Rect(row_rect.right - bw - 4, row_rect.y + 2, bw, row_rect.h - 4)
        for rect, label, active_color in ((tp_rect, "TP", (60, 90, 70)), (trade_rect, "Trade", (70, 70, 100)),
                                           (remove_rect, "X", (100, 60, 60))):
            enabled = online or label == "X"
            _bevel_button(surf, rect, active_color, enabled=enabled, border_radius=3)
            t = _FONT_S.render(label, True, (230, 230, 230) if enabled else (100, 100, 105))
            surf.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))
        rows.append((row_rect, tp_rect, trade_rect, remove_rect, name, online))
    return rows

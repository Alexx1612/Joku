"""
The Quest Log, Dictionary and Quest Map windows (Batch 15 items 1.4 / 1.5 / 1.6),
shared verbatim by main.py (single-player) and coop_client.py.

One Journal object per client owns a small window stack (so "click a quest target"
-> Dictionary -> Esc goes back to the Quest Log, and a second Esc closes it). Each
client passes a plain `ctx` dict every call:

    story:      StoryProgress.quest_log() dict (or None)
    side:       SideQuestProgress.log() list
    side_done:  [titles of completed side quests]
    grid:       the open Realm's tile grid (or None if none is known yet)
    areas:      codex.realm_areas(...) dict for that grid (or None)
    player_tile:(x, y) tile coords when the player is in that Realm, else None

While a window is open the Journal consumes every key/mouse event, so typing in the
search bar never triggers game keys, and the clients block movement/firing too.
"""
import math

import pygame

from game import constants as C
from game import codex
from game import clipboard

QUEST_LOG, DICTIONARY, QUEST_MAP = "quest_log", "dictionary", "quest_map"

SEARCH_MAX = 40
ROW_H = 26
CAT_H = 30


def _ui():
    from game import ui
    return ui


# ------------------------------------------------------------- map render --
_MAP_CACHE = {}


def _tile_color(t):
    from game import minimap, world
    c = minimap.TILE_MM_COLORS.get(t) or world.TILE_COLORS.get(t) or (60, 60, 66)
    return c[:3]


def realm_surface(grid):
    """A fully-revealed 1px-per-tile render of `grid` (cached per grid object)."""
    key = id(grid)
    hit = _MAP_CACHE.get(key)
    if hit is not None and hit[0] is grid:
        return hit[1]
    h, w = len(grid), len(grid[0])
    lut = {}
    buf = bytearray(w * h * 3)
    i = 0
    for row in grid:
        for t in row:
            c = lut.get(t)
            if c is None:
                c = lut[t] = bytes(_tile_color(t))
            buf[i:i + 3] = c
            i += 3
    surf = pygame.image.frombuffer(bytes(buf), (w, h), "RGB").copy()
    if len(_MAP_CACHE) > 3:
        _MAP_CACHE.clear()
    _MAP_CACHE[key] = (grid, surf, {})
    return surf


def _scaled_map(grid, size):
    realm_surface(grid)
    _g, surf, scaled = _MAP_CACHE[id(grid)]
    if size not in scaled:
        scaled[size] = pygame.transform.smoothscale(surf, size)
    return scaled[size]


def _sprite_surface(sprite, size):
    """Preview image for a dictionary entry's sprite spec (or None)."""
    if not sprite:
        return None
    ui = _ui()
    src = sprite.get("src")
    try:
        if src in ("enemy", "player"):
            return ui._portrait_surface({"src": src, "key": sprite["key"], "tint": sprite.get("tint")}, size)
        if src == "item":
            from game import sprites
            img = sprites.item_icon(sprite.get("tint") or (220, 220, 230), sprite["key"])
            return pygame.transform.smoothscale(img, (size, size))
        if src == "portal":
            from game.entities import Portal
            surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            Portal(pygame.Vector2(size, size * 1.2), kind=sprite["key"]).draw(surf, lambda p: (int(p[0]), int(p[1])))
            return pygame.transform.smoothscale(surf, (size, size))
    except (KeyError, TypeError, ValueError):
        return None
    return None


class Journal:
    def __init__(self):
        self.stack = []
        self.ql_scroll = 0
        self.cat = codex.CATEGORIES[0][0]
        self.query = ""
        self.query_all = False  # Ctrl+A selected the whole search text
        self.sel = None
        self.list_scroll = 0
        self.text_scroll = 0
        self.map_where = None
        self.map_title = ""
        self.map_note = ""
        self.map_zoom = 1.0
        self.map_center = None  # tile coords at the map rect centre
        self._pan = None
        self.t = 0.0

    # -------------------------------------------------------------- state --
    @property
    def mode(self):
        return self.stack[-1] if self.stack else None

    def is_open(self):
        return bool(self.stack)

    def close_all(self):
        self.stack = []

    def back(self):
        if self.stack:
            self.stack.pop()

    def _push(self, mode):
        if self.mode == mode:
            return
        if mode in self.stack:
            self.stack.remove(mode)
        self.stack.append(mode)

    def open_quest_log(self):
        self.stack = [QUEST_LOG]
        self.ql_scroll = 0

    def open_dictionary(self, entry_id=None, stack=False):
        if not stack:
            self.stack = []
        self._push(DICTIONARY)
        if entry_id and codex.entry(entry_id):
            e = codex.entry(entry_id)
            self.query, self.query_all = "", False
            self.cat, self.sel = e["cat"], entry_id
            ids = [x["id"] for x in self._list()]
            self.list_scroll = max(0, ids.index(entry_id) - 5) if entry_id in ids else 0
            self.text_scroll = 0
        elif self.sel is None:
            lst = self._list()
            self.sel = lst[0]["id"] if lst else None

    def open_map(self, where=None, title="", note="", stack=True):
        if not stack:
            self.stack = []
        self._push(QUEST_MAP)
        self.map_where, self.map_title, self.map_note = where, title, note
        self.map_zoom, self.map_center = 1.0, None

    def _list(self):
        return codex.search(self.query, None if self.query.strip() else self.cat)

    # -------------------------------------------------------------- input --
    def handle_event(self, event, ctx):
        """True if the event belonged to an open window (i.e. the client should skip it)."""
        if not self.stack:
            return False
        if event.type == pygame.KEYDOWN:
            self._key(event, ctx)
            return True
        if event.type == pygame.MOUSEWHEEL:
            self._wheel(event.y, pygame.mouse.get_pos(), ctx)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self._click(event.pos, ctx)
            elif event.button in (4, 5):
                self._wheel(1 if event.button == 4 else -1, event.pos, ctx)
            elif event.button == 3 and self.mode == QUEST_MAP:
                self._pan = (event.pos, self.map_center)
            return True
        if event.type == pygame.MOUSEBUTTONUP:
            self._pan = None
            return True
        if event.type == pygame.MOUSEMOTION:
            if self._pan is not None and self.mode == QUEST_MAP and self._pan[1] is not None:
                (sx, sy), (cx, cy) = self._pan
                rect, scale = self._map_geom(ctx)
                if scale:
                    self.map_center = (cx - (event.pos[0] - sx) / scale, cy - (event.pos[1] - sy) / scale)
            return True
        return event.type in (pygame.TEXTINPUT, pygame.KEYUP)

    def _key(self, event, ctx):
        if event.key == pygame.K_ESCAPE:
            self.back()
            return
        mode = self.mode
        if mode == QUEST_LOG:
            if event.key in (pygame.K_UP, pygame.K_w):
                self._wheel(1, None, ctx)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self._wheel(-1, None, ctx)
            elif event.key == pygame.K_PAGEUP:
                self._wheel(8, None, ctx)
            elif event.key == pygame.K_PAGEDOWN:
                self._wheel(-8, None, ctx)
            elif event.key == pygame.K_j:
                self.back()
        elif mode == DICTIONARY:
            self._dict_key(event)
        elif mode == QUEST_MAP:
            if event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self._zoom(1, None, ctx)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self._zoom(-1, None, ctx)
            elif event.key == pygame.K_m:
                self.back()

    def _dict_key(self, event):
        ctrl = event.mod & pygame.KMOD_CTRL
        lst = self._list()
        ids = [e["id"] for e in lst]
        if ctrl and event.key == pygame.K_a:
            self.query_all = bool(self.query)
        elif ctrl and event.key == pygame.K_c:
            clipboard.set_text(self.query)
        elif ctrl and event.key == pygame.K_v:
            if self.query_all:
                self.query, self.query_all = "", False
            self._set_query(self.query + clipboard.get_text().replace("\n", " "))
        elif event.key == pygame.K_BACKSPACE:
            self._set_query("" if self.query_all else self.query[:-1])
        elif event.key in (pygame.K_UP, pygame.K_DOWN):
            if ids:
                i = ids.index(self.sel) if self.sel in ids else 0
                i = max(0, min(len(ids) - 1, i + (1 if event.key == pygame.K_DOWN else -1)))
                self.sel, self.text_scroll = ids[i], 0
                vis = self._list_rows_visible()
                if i < self.list_scroll:
                    self.list_scroll = i
                elif i >= self.list_scroll + vis:
                    self.list_scroll = i - vis + 1
        elif event.key in (pygame.K_TAB,):
            cats = [c for c, _l in codex.CATEGORIES]
            self.cat = cats[(cats.index(self.cat) + 1) % len(cats)]
            self._set_query("")
        elif event.unicode and event.unicode.isprintable() and not ctrl:
            base = "" if self.query_all else self.query
            self._set_query(base + event.unicode)

    def _set_query(self, q):
        self.query, self.query_all = q[:SEARCH_MAX], False
        self.list_scroll = 0
        lst = self._list()
        if lst and self.sel not in [e["id"] for e in lst]:
            self.sel, self.text_scroll = lst[0]["id"], 0

    def _wheel(self, dy, pos, ctx):
        mode = self.mode
        if mode == QUEST_LOG:
            _items, total = self._ql_layout(ctx)
            view = self._ql_rects()[1].h
            self.ql_scroll = max(0, min(max(0, total - view), self.ql_scroll - dy * 40))
        elif mode == DICTIONARY:
            r = self._dict_rects()
            if pos is not None and r["right"].collidepoint(pos):
                self.text_scroll = max(0, self.text_scroll - dy)
            else:
                n = len(self._list())
                self.list_scroll = max(0, min(max(0, n - self._list_rows_visible()), self.list_scroll - dy))
        elif mode == QUEST_MAP:
            self._zoom(dy, pos, ctx)

    def _zoom(self, dy, pos, ctx):
        rect, scale = self._map_geom(ctx)
        if not scale:
            return
        if self.map_center is None:
            self.map_center = self._default_center(ctx)
        old = self.map_zoom
        self.map_zoom = max(1.0, min(8.0, self.map_zoom * (1.25 if dy > 0 else 0.8)))
        if pos is not None and rect.collidepoint(pos):
            # keep the tile under the cursor fixed
            tx = self.map_center[0] + (pos[0] - rect.centerx) / scale
            ty = self.map_center[1] + (pos[1] - rect.centery) / scale
            k = old / self.map_zoom
            self.map_center = (tx - (tx - self.map_center[0]) * k, ty - (ty - self.map_center[1]) * k)

    def _click(self, pos, ctx):
        mode = self.mode
        if mode == QUEST_LOG:
            win, content = self._ql_rects()
            if self._close_rect(win).collidepoint(pos):
                self.back()
                return
            items, _t = self._ql_layout(ctx)
            for it in items:
                if it.get("action") and content.collidepoint(pos):
                    r = pygame.Rect(content.x + it["x"], content.y + it["y"] - self.ql_scroll, it["w"], it["h"])
                    if r.collidepoint(pos):
                        self._do(it["action"])
                        return
        elif mode == DICTIONARY:
            r = self._dict_rects()
            if self._close_rect(r["win"]).collidepoint(pos):
                self.back()
                return
            if r["search"].collidepoint(pos):
                self.query_all = bool(self.query)
                return
            for i, (cat, _label) in enumerate(codex.CATEGORIES):
                if self._cat_rect(r, i).collidepoint(pos):
                    self.cat = cat
                    self._set_query("")
                    lst = self._list()
                    self.sel, self.text_scroll = (lst[0]["id"] if lst else None), 0
                    return
            lst = self._list()
            for i in range(self._list_rows_visible()):
                idx = self.list_scroll + i
                if idx < len(lst) and self._row_rect(r, i).collidepoint(pos):
                    self.sel, self.text_scroll = lst[idx]["id"], 0
                    return
            e = codex.entry(self.sel) if self.sel else None
            if e is not None and self._where_has_points(e, ctx) and r["mapbtn"].collidepoint(pos):
                self.open_map(e["where"], e["title"])
        elif mode == QUEST_MAP:
            rect, _s = self._map_geom(ctx)
            if self._close_rect(pygame.Rect(0, 0, C.SCREEN_W, 40)).collidepoint(pos):
                self.back()

    def _do(self, action):
        if action[0] == "dict":
            self.open_dictionary(action[1], stack=True)
        elif action[0] == "map":
            self.open_map(action[1], action[2], action[3])

    # -------------------------------------------------------- quest log --
    def _ql_rects(self):
        w = min(780, C.SCREEN_W - 40)
        h = min(640, C.SCREEN_H - 40)
        win = pygame.Rect(C.SCREEN_W // 2 - w // 2, C.SCREEN_H // 2 - h // 2, w, h)
        content = pygame.Rect(win.x + 20, win.y + 52, w - 50, h - 52 - 34)
        return win, content

    @staticmethod
    def _close_rect(win):
        return pygame.Rect(win.right - 34, win.y + 8, 26, 24)

    def _ql_layout(self, ctx):
        """[{x, y, w, h, text, font, color, action?, kind}] in content space + total height."""
        ui = _ui()
        _win, content = self._ql_rects()
        W = content.w - 8
        fs, fm = ui._FONT_S, ui._FONT_M
        lh = fs.get_height() + 3
        items = []
        y = 0

        def text(s, color, x=0, font=fs, kind="text"):
            nonlocal y
            for line in ui._wrap_text(s, font, W - x) or [""]:
                items.append(dict(x=x, y=y, w=font.size(line)[0], h=font.get_height(), text=line,
                                  font=font, color=color, kind=kind))
                y += font.get_height() + 3

        def header(s):
            nonlocal y
            y += 6
            items.append(dict(x=0, y=y, w=W, h=fm.get_height(), text=s, font=fm, color=(245, 215, 130),
                              kind="header"))
            y += fm.get_height() + 6

        def target_line(label, target, extra=None, map_title=""):
            """'label: <link>' + optional more links + a [Map] button, on one line."""
            nonlocal y
            x = 16
            lab = fs.render(label, True, (160, 160, 175))
            items.append(dict(x=x, y=y, w=lab.get_width(), h=lh, text=label, font=fs,
                              color=(160, 160, 175), kind="text"))
            x += lab.get_width() + 6
            for tgt in [target] + list(extra or []):
                if not tgt:
                    continue
                eid = codex.entry_for_target(tgt)
                name = tgt.get("label") or "?"
                w = fs.size(name)[0]
                items.append(dict(x=x, y=y, w=w, h=lh, text=name, font=fs, color=(130, 200, 255),
                                  kind="link", action=("dict", eid) if eid and codex.entry(eid) else None))
                x += w + 14
            where = codex.where_for_target(target)
            if codex.markers_for(where, ctx.get("areas")) or codex.target_note(target):
                items.append(dict(x=W - 64, y=y - 2, w=64, h=lh + 2, text="Map", font=fs,
                                  color=(255, 240, 200), kind="button",
                                  action=("map", where, map_title, codex.target_note(target))))
            y += lh + 2

        story_log = ctx.get("story")
        if story_log:
            header(f"Story - {story_log.get('title', '')}")
            if story_log.get("hint"):
                text(story_log["hint"], (200, 198, 210))
            for o in story_log.get("objectives", []):
                done = o.get("have", 0) >= o.get("need", 1)
                text(f"{'[x]' if done else '[ ]'} {o['text']}  ({o.get('have', 0)}/{o.get('need', 1)})",
                     (140, 230, 150) if done else (230, 228, 238), x=8)
                if o.get("target") and not done:
                    target_line("Where:", o["target"], map_title=o["text"])
        side = ctx.get("side") or []
        header(f"Side quests ({len(side)} active)")
        if not side:
            text("No active side quests - talk to people around the Realm (F).", (170, 170, 185), x=8)
        for q in side:
            status = "READY - hand it in" if q.get("ready") and q.get("turn_in") else \
                ("DONE" if q.get("ready") else f"{q.get('have', 0)}/{q.get('need', 1)}")
            text(f"{q['title']}  -  {status}", (255, 230, 150) if q.get("ready") else (235, 232, 240), x=8)
            text(q.get("desc", ""), (190, 188, 200), x=16)
            extra = []
            for role in ("giver", "turn_in"):
                npc_id = q.get(role)
                if npc_id and (not extra or extra[-1]["key"] != npc_id):
                    from game import npcs
                    name = npcs.NPCS.get(npc_id, {}).get("name", npc_id)
                    extra.append({"kind": "npc", "key": npc_id, "label": name})
            target_line("Target:", q.get("target"), extra=[e for e in extra if e["key"] != (q.get("target") or {}).get("key")],
                        map_title=q["title"])
            y += 4
        done = ctx.get("side_done") or []
        header(f"Completed ({len(done)})")
        if done:
            text(", ".join(done), (150, 200, 150), x=8)
        else:
            text("Nothing yet.", (150, 150, 160), x=8)
        return items, y + 10

    def _draw_quest_log(self, surf, ctx, mouse):
        ui = _ui()
        win, content = self._ql_rects()
        panel, _ = ui._ornate_panel(win.w, win.h)
        title = ui._FONT_L.render("Quest Log", True, (240, 225, 180))
        panel.blit(title, (20, 10))
        surf.blit(panel, win.topleft)
        self._draw_close(surf, win, mouse)
        items, total = self._ql_layout(ctx)
        self.ql_scroll = max(0, min(max(0, total - content.h), self.ql_scroll))
        old = surf.get_clip()
        surf.set_clip(content)
        for it in items:
            y = content.y + it["y"] - self.ql_scroll
            if y + it["h"] < content.y or y > content.bottom:
                continue
            r = pygame.Rect(content.x + it["x"], y, it["w"], it["h"])
            hov = it.get("action") and r.collidepoint(mouse)
            if it["kind"] == "button":
                ui._bevel_button(surf, r, (60, 58, 90), hovered=hov)
                t = it["font"].render(it["text"], True, it["color"])
                surf.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))
                continue
            color = (200, 235, 255) if hov else it["color"]
            t = it["font"].render(it["text"], True, color)
            surf.blit(t, r.topleft)
            if it["kind"] == "link" and it.get("action"):
                pygame.draw.line(surf, color, (r.x, r.y + t.get_height()), (r.x + t.get_width(), r.y + t.get_height()))
            if it["kind"] == "header":
                pygame.draw.line(surf, (*ui.CHROME_GOLD, ), (r.x, r.y + it["h"] + 2), (content.right - 8, r.y + it["h"] + 2))
        surf.set_clip(old)
        self._scrollbar(surf, content, self.ql_scroll, total)
        hint = ui._FONT_S.render("Wheel/arrows scroll - click a blue name to look it up, Map to see where - Esc closes",
                                 True, (140, 138, 155))
        surf.blit(hint, (win.centerx - hint.get_width() // 2, win.bottom - 26))

    def _scrollbar(self, surf, rect, scroll, total):
        if total <= rect.h:
            return
        bar = pygame.Rect(rect.right + 6, rect.y, 6, rect.h)
        pygame.draw.rect(surf, (40, 38, 52), bar, border_radius=3)
        th = max(24, int(rect.h * rect.h / total))
        ty = rect.y + int((rect.h - th) * scroll / max(1, total - rect.h))
        pygame.draw.rect(surf, (170, 150, 100), (bar.x, ty, bar.w, th), border_radius=3)

    def _draw_close(self, surf, win, mouse):
        ui = _ui()
        r = self._close_rect(win)
        ui._bevel_button(surf, r, (140, 55, 55), hovered=r.collidepoint(mouse))
        t = ui._FONT_S.render("X", True, (255, 225, 225))
        surf.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))

    # ------------------------------------------------------- dictionary --
    def _dict_rects(self):
        w = min(1080, C.SCREEN_W - 30)
        h = min(680, C.SCREEN_H - 30)
        win = pygame.Rect(C.SCREEN_W // 2 - w // 2, C.SCREEN_H // 2 - h // 2, w, h)
        left = pygame.Rect(win.x + 16, win.y + 56, 200, h - 56 - 40)
        mid = pygame.Rect(left.right + 12, left.y, 250, left.h)
        right = pygame.Rect(mid.right + 14, left.y, win.right - 16 - (mid.right + 14), left.h)
        search = pygame.Rect(left.x, left.y, left.w, 30)
        mini = pygame.Rect(right.right - 210, right.bottom - 210, 210, 210)
        text = pygame.Rect(right.x, right.y + 120, right.w, right.h - 120 - 220)
        mapbtn = pygame.Rect(mini.x - 150, mini.bottom - 30, 140, 30)
        return dict(win=win, left=left, mid=mid, right=right, search=search, mini=mini, text=text, mapbtn=mapbtn)

    @staticmethod
    def _cat_rect(r, i):
        return pygame.Rect(r["left"].x, r["search"].bottom + 12 + i * (CAT_H + 4), r["left"].w, CAT_H)

    def _list_rows_visible(self):
        return max(1, self._dict_rects()["mid"].h // ROW_H)

    def _row_rect(self, r, i):
        return pygame.Rect(r["mid"].x, r["mid"].y + i * ROW_H, r["mid"].w - 10, ROW_H - 2)

    @staticmethod
    def _where_has_points(e, ctx):
        return bool(codex.markers_for(e["where"], ctx.get("areas")))

    def _draw_dictionary(self, surf, ctx, mouse):
        ui = _ui()
        r = self._dict_rects()
        win = r["win"]
        panel, _ = ui._ornate_panel(win.w, win.h)
        panel.blit(ui._FONT_L.render("Dictionary", True, (240, 225, 180)), (20, 10))
        surf.blit(panel, win.topleft)
        self._draw_close(surf, win, mouse)
        fs, fm = ui._FONT_S, ui._FONT_M
        # search bar
        sb = r["search"]
        pygame.draw.rect(surf, (16, 15, 22), sb, border_radius=4)
        pygame.draw.rect(surf, ui.CHROME_GOLD, sb, width=1, border_radius=4)
        shown = self.query if self.query else "Search everything..."
        col = (235, 235, 240) if self.query else (120, 118, 130)
        t = fs.render(shown, True, col)
        if self.query_all and self.query:
            pygame.draw.rect(surf, (60, 90, 150), (sb.x + 6, sb.y + 6, t.get_width() + 2, t.get_height() + 2))
        surf.blit(t, (sb.x + 7, sb.centery - t.get_height() // 2))
        if self.query and int(self.t * 2) % 2 == 0:
            cx = sb.x + 8 + t.get_width()
            pygame.draw.line(surf, (230, 230, 240), (cx, sb.y + 7), (cx, sb.bottom - 7))
        # categories
        searching = bool(self.query.strip())
        for i, (cat, label) in enumerate(codex.CATEGORIES):
            cr = self._cat_rect(r, i)
            active = cat == self.cat and not searching
            ui._bevel_button(surf, cr, (70, 60, 40) if active else (36, 34, 48), hovered=cr.collidepoint(mouse))
            n = sum(1 for e in codex.entries() if e["cat"] == cat)
            t = fs.render(f"{label} ({n})", True, (255, 235, 180) if active else (205, 202, 215))
            surf.blit(t, (cr.x + 10, cr.centery - t.get_height() // 2))
        # entry list
        lst = self._list()
        pygame.draw.rect(surf, (18, 17, 25), r["mid"], border_radius=4)
        if not lst:
            surf.blit(fs.render("Nothing matches.", True, (150, 150, 160)), (r["mid"].x + 8, r["mid"].y + 8))
        vis = self._list_rows_visible()
        self.list_scroll = max(0, min(max(0, len(lst) - vis), self.list_scroll))
        for i in range(vis):
            idx = self.list_scroll + i
            if idx >= len(lst):
                break
            e = lst[idx]
            rr = self._row_rect(r, i)
            sel = e["id"] == self.sel
            if sel or rr.collidepoint(mouse):
                pygame.draw.rect(surf, (60, 55, 85) if sel else (38, 36, 52), rr, border_radius=3)
            title = e["title"]
            while fs.size(title)[0] > rr.w - 14 and len(title) > 4:
                title = title[:-2]
            if title != e["title"]:
                title = title.rstrip() + "."
            surf.blit(fs.render(title, True, (255, 240, 200) if sel else (220, 218, 230)),
                      (rr.x + 7, rr.centery - fs.get_height() // 2))
        self._scrollbar(surf, pygame.Rect(r["mid"].x, r["mid"].y, r["mid"].w - 10, r["mid"].h),
                        self.list_scroll * ROW_H, len(lst) * ROW_H)
        # detail pane
        e = codex.entry(self.sel) if self.sel else None
        if e is None and lst:
            e = lst[0]
            self.sel = e["id"]
        if e is not None:
            self._draw_entry(surf, r, e, ctx, mouse)
        hint = fs.render("Type to search - Tab: next category - Up/Down: select - wheel scrolls - Esc closes",
                         True, (140, 138, 155))
        surf.blit(hint, (win.centerx - hint.get_width() // 2, win.bottom - 28))

    def _draw_entry(self, surf, r, e, ctx, mouse):
        ui = _ui()
        fs, fm = ui._FONT_S, ui._FONT_M
        right = r["right"]
        cat_label = dict(codex.CATEGORIES).get(e["cat"], e["cat"])
        surf.blit(fm.render(e["title"], True, (245, 215, 130)), (right.x, right.y))
        surf.blit(fs.render(cat_label, True, (150, 148, 165)), (right.x, right.y + 22))
        box = pygame.Rect(right.x, right.y + 44, 72, 72)
        img = _sprite_surface(e.get("sprite"), 64)
        if img is not None:
            pygame.draw.rect(surf, (22, 20, 30), box, border_radius=6)
            pygame.draw.rect(surf, ui.CHROME_GOLD, box, width=1, border_radius=6)
            surf.blit(img, (box.x + 4, box.y + 4))
            sx = box.right + 14
        else:
            sx = right.x
        col_w = max(150, (right.right - sx) // 2)
        for i, (k, v) in enumerate(e["stats"][:8]):
            cx, cy = sx + (i % 2) * col_w, right.y + 46 + (i // 2) * 18
            t = fs.render(f"{k}: ", True, (160, 160, 175))
            surf.blit(t, (cx, cy))
            val = str(v)
            while fs.size(val)[0] > col_w - t.get_width() - 8 and len(val) > 3:
                val = val[:-2]
            surf.blit(fs.render(val, True, (235, 232, 240)), (cx + t.get_width(), cy))
        # text (wrapped, scrollable) - help pages (no sprite/stats/location) use the whole pane
        has_where = bool(e["where"].get("biomes") or e["where"].get("areas"))
        top = right.y + 120 if (img is not None or e["stats"]) else right.y + 46
        bottom = r["mini"].y - 26 if has_where else right.bottom
        tr = pygame.Rect(right.x, top, right.w, bottom - top)
        lines = []
        for para in e["text"].split("\n"):
            lines += ui._wrap_text(para, fs, tr.w - 10) if para.strip() else [""]
        lh = fs.get_height() + 3
        max_lines = max(1, tr.h // lh)
        self.text_scroll = max(0, min(max(0, len(lines) - max_lines), self.text_scroll))
        for i, line in enumerate(lines[self.text_scroll:self.text_scroll + max_lines]):
            surf.blit(fs.render(line, True, (220, 218, 230)), (tr.x, tr.y + i * lh))
        if len(lines) > max_lines:
            surf.blit(fs.render("(scroll for more)", True, (130, 128, 145)), (tr.x, tr.bottom - lh + 4))
        if not has_where:
            return
        # where to find
        mini = r["mini"]
        surf.blit(fs.render("Where to find", True, (200, 190, 150)), (mini.x, mini.y - 20))
        pygame.draw.rect(surf, (10, 10, 14), mini)
        pts = codex.markers_for(e["where"], ctx.get("areas"))
        grid = ctx.get("grid")
        if grid:
            surf.blit(_scaled_map(grid, mini.size), mini.topleft)
            sx_, sy_ = mini.w / len(grid[0]), mini.h / len(grid)
            pulse = 3 + int(2 * (1 + math.sin(self.t * 5)))
            for (x, y, _label) in pts:
                p = (mini.x + int(x * sx_), mini.y + int(y * sy_))
                pygame.draw.circle(surf, (255, 70, 70), p, pulse, width=2)
            if ctx.get("player_tile"):
                px, py = ctx["player_tile"]
                pygame.draw.circle(surf, (255, 230, 90), (mini.x + int(px * sx_), mini.y + int(py * sy_)), 3)
        else:
            for i, line in enumerate(ui._wrap_text("Enter the Realm once to see the map here.", fs, mini.w - 16)):
                surf.blit(fs.render(line, True, (150, 150, 165)), (mini.x + 8, mini.y + 8 + i * 18))
        pygame.draw.rect(surf, ui.CHROME_GOLD, mini, width=1)
        if not pts and grid:
            surf.blit(fs.render("No fixed spot", True, (170, 170, 185)), (mini.x + 8, mini.bottom - 22))
        if pts:
            b = r["mapbtn"]
            ui._bevel_button(surf, b, (60, 58, 90), hovered=b.collidepoint(mouse))
            t = fs.render("Open on map", True, (255, 240, 200))
            surf.blit(t, (b.centerx - t.get_width() // 2, b.centery - t.get_height() // 2))

    # --------------------------------------------------------- quest map --
    def _default_center(self, ctx):
        grid = ctx.get("grid")
        if not grid:
            return (0, 0)
        return (len(grid[0]) / 2, len(grid) / 2)

    def _map_geom(self, ctx):
        """(map viewport rect, screen px per tile) - scale 0 when there's no map."""
        grid = ctx.get("grid")
        rect = pygame.Rect(30, 50, C.SCREEN_W - 60, C.SCREEN_H - 50 - 70)
        if not grid:
            return rect, 0
        w, h = len(grid[0]), len(grid)
        base = min(rect.w / w, rect.h / h)
        return rect, base * self.map_zoom

    def _map_points(self, ctx):
        """[(tile_x, tile_y, label, kind)] for everything labelled on the quest map."""
        areas = ctx.get("areas") or {}
        pts = []
        for l in areas.get("landmarks", []):
            pts.append((l["x"], l["y"], codex.cap(l["name"]), "landmark"))
        for i in areas.get("islands", []):
            pts.append((i["x"], i["y"], i["label"], "island"))
        for n in areas.get("npcs", []):
            pts.append((n["x"], n["y"], n["name"], "npc"))
        for c in areas.get("chests", []):
            pts.append((c["x"], c["y"], "Island chest", "chest"))
        if areas.get("spawn"):
            pts.append((areas["spawn"]["x"], areas["spawn"]["y"], "Arrival beach", "spawn"))
        return pts

    def map_hover(self, ctx, mouse):
        """Tooltip text for whatever is under the mouse on the quest map (or None)."""
        rect, scale = self._map_geom(ctx)
        if not scale or not rect.collidepoint(mouse):
            return None
        to_screen = self._to_screen(ctx)
        best, bd = None, 14
        targets = [(x, y, f"QUEST: {label}", "target") for (x, y, label) in
                   codex.markers_for(self.map_where, ctx.get("areas"))] if self.map_where else []
        for x, y, label, kind in targets + self._map_points(ctx):
            sx, sy = to_screen(x, y)
            d = math.hypot(sx - mouse[0], sy - mouse[1])
            if d < bd:
                best, bd = label, d
        if best:
            return best
        if ctx.get("player_tile"):
            sx, sy = to_screen(*ctx["player_tile"])
            if math.hypot(sx - mouse[0], sy - mouse[1]) < 12:
                return "You are here"
        cx, cy = self.map_center or self._default_center(ctx)
        tx = int(cx + (mouse[0] - rect.centerx) / scale)
        ty = int(cy + (mouse[1] - rect.centery) / scale)
        b = codex.tile_biome(ctx.get("grid"), tx, ty)
        return codex.BIOME_LABELS.get(b) if b else None

    def _to_screen(self, ctx):
        rect, scale = self._map_geom(ctx)
        cx, cy = self.map_center or self._default_center(ctx)

        def f(x, y):
            return rect.centerx + (x - cx) * scale, rect.centery + (y - cy) * scale
        return f

    def _draw_quest_map(self, surf, ctx, mouse):
        ui = _ui()
        fs, fm = ui._FONT_S, ui._FONT_M
        surf.fill((8, 8, 12))
        title = "Quest Map" + (f" - {self.map_title}" if self.map_title else "")
        t = fm.render(title, True, (240, 225, 180))
        surf.blit(t, (C.SCREEN_W // 2 - t.get_width() // 2, 14))
        self._draw_close(surf, pygame.Rect(0, 0, C.SCREEN_W, 40), mouse)
        rect, scale = self._map_geom(ctx)
        grid = ctx.get("grid")
        if not grid:
            msg = fs.render("No Realm map yet - enter the Realm once and it will be charted here.", True,
                            (180, 180, 195))
            surf.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, C.SCREEN_H // 2))
            return
        if self.map_center is None:
            self.map_center = self._default_center(ctx)
        w, h = len(grid[0]), len(grid)
        to_screen = self._to_screen(ctx)
        old = surf.get_clip()
        surf.set_clip(rect)
        # crop the 1px/tile render to the visible window, then scale it
        cx, cy = self.map_center
        vx0 = max(0, int(cx - rect.w / 2 / scale) - 1)
        vy0 = max(0, int(cy - rect.h / 2 / scale) - 1)
        vx1 = min(w, int(cx + rect.w / 2 / scale) + 2)
        vy1 = min(h, int(cy + rect.h / 2 / scale) + 2)
        if vx1 > vx0 and vy1 > vy0:
            base = realm_surface(grid).subsurface((vx0, vy0, vx1 - vx0, vy1 - vy0))
            size = (max(1, int((vx1 - vx0) * scale)), max(1, int((vy1 - vy0) * scale)))
            img = pygame.transform.scale(base, size)
            sx, sy = to_screen(vx0, vy0)
            surf.blit(img, (int(sx), int(sy)))
        areas = ctx.get("areas") or {}
        placed = []  # label rects already drawn - later labels that would overlap them are skipped

        def label_at(text, color, sx, sy, anchors=((8, -8), (-8, -8), (-6, 6), (-6, -24))):
            img = fs.render(text, True, color)
            for ax, ay in anchors:
                x = sx + ax if ax >= 0 else sx + ax - img.get_width()
                if ax < 0 and ay >= 0:
                    x = sx - img.get_width() // 2
                r = pygame.Rect(int(x), int(sy + ay), img.get_width(), img.get_height())
                if not any(r.colliderect(p) for p in placed):
                    placed.append(r.inflate(4, 2))
                    surf.blit(fs.render(text, True, (0, 0, 0)), (r.x + 1, r.y + 1))
                    surf.blit(img, r.topleft)
                    return True
            return False

        colors = {"landmark": (255, 255, 255), "island": (240, 190, 80), "npc": (110, 230, 130),
                  "chest": (170, 120, 60), "spawn": (120, 200, 255)}
        points = self._map_points(ctx)
        for x, y, label, kind in points:
            sx, sy = to_screen(x, y)
            col = colors.get(kind, (220, 220, 220))
            if kind == "landmark":
                pygame.draw.polygon(surf, col, [(sx, sy - 6), (sx + 5, sy), (sx, sy + 6), (sx - 5, sy)])
            elif kind == "chest":
                pygame.draw.rect(surf, col, (sx - 3, sy - 3, 6, 6))
            else:
                pygame.draw.circle(surf, col, (int(sx), int(sy)), 4)
                pygame.draw.circle(surf, (0, 0, 0), (int(sx), int(sy)), 4, width=1)
            placed.append(pygame.Rect(int(sx) - 5, int(sy) - 5, 10, 10))
        # labels by priority: islands + landmarks, then (zoomed in) people, then biome names
        for x, y, label, kind in points:
            if kind in ("island", "landmark"):
                sx, sy = to_screen(x, y)
                label_at(label, colors[kind], sx, sy)
        if self.map_zoom >= 2.0:
            for x, y, label, kind in points:
                if kind in ("npc", "spawn"):
                    sx, sy = to_screen(x, y)
                    label_at(label, colors[kind], sx, sy)
        for reg in sorted(areas.get("biomes", []), key=lambda r: -r["size"]):
            if reg["size"] < (40 if self.map_zoom < 2 else 15):
                continue
            sx, sy = to_screen(reg["x"], reg["y"])
            label_at(codex.BIOME_LABELS.get(reg["biome"], reg["biome"]), (225, 225, 232), sx, sy,
                     anchors=((-1, -7), (-1, 6), (-1, -20)))
        # quest target markers
        pulse = 8 + 4 * (1 + math.sin(self.t * 5))
        for x, y, label in codex.markers_for(self.map_where, areas) if self.map_where else []:
            sx, sy = to_screen(x, y)
            pygame.draw.circle(surf, (255, 60, 60), (int(sx), int(sy)), int(pulse), width=3)
            pygame.draw.circle(surf, (255, 200, 200), (int(sx), int(sy)), 3)
        if ctx.get("player_tile"):
            sx, sy = to_screen(*ctx["player_tile"])
            pygame.draw.circle(surf, (255, 230, 90), (int(sx), int(sy)), 6)
            pygame.draw.circle(surf, (0, 0, 0), (int(sx), int(sy)), 6, width=2)
        surf.set_clip(old)
        pygame.draw.rect(surf, ui.CHROME_GOLD, rect, width=1)
        # legend + note
        legend = [("You", (255, 230, 90)), ("Quest target", (255, 60, 60)), ("Landmark", (255, 255, 255)),
                  ("Island", (240, 190, 80)), ("Person / creature", (110, 230, 130)), ("Arrival beach", (120, 200, 255))]
        x = rect.x
        ly = rect.bottom + 10
        for label, col in legend:
            pygame.draw.circle(surf, col, (x + 6, ly + 8), 5)
            t = fs.render(label, True, (210, 208, 220))
            surf.blit(t, (x + 16, ly))
            x += t.get_width() + 34
        note = self.map_note or ("" if ctx.get("player_tile") else "You're not in the Realm right now.")
        hint = ("Wheel/+- zoom - right-drag to pan - hover for names - Esc closes" +
                (f"   |   {note}" if note else ""))
        t = fs.render(hint, True, (150, 148, 165))
        surf.blit(t, (C.SCREEN_W // 2 - t.get_width() // 2, ly + 26))
        tip = self.map_hover(ctx, mouse)
        if tip:
            tt = fs.render(tip, True, (245, 240, 220))
            box = pygame.Rect(mouse[0] + 14, mouse[1] + 10, tt.get_width() + 12, tt.get_height() + 8)
            box.clamp_ip(pygame.Rect(0, 0, C.SCREEN_W, C.SCREEN_H))
            pygame.draw.rect(surf, (20, 18, 28), box, border_radius=4)
            pygame.draw.rect(surf, ui.CHROME_GOLD, box, width=1, border_radius=4)
            surf.blit(tt, (box.x + 6, box.y + 4))

    # ------------------------------------------------------------- draw --
    def draw(self, surf, ctx, mouse=(-1, -1), dt=1 / 60):
        self.t += dt
        mode = self.mode
        if mode is None:
            return
        if mode != QUEST_MAP:
            dim = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 150))
            surf.blit(dim, (0, 0))
        if mode == QUEST_LOG:
            self._draw_quest_log(surf, ctx, mouse)
        elif mode == DICTIONARY:
            self._draw_dictionary(surf, ctx, mouse)
        elif mode == QUEST_MAP:
            self._draw_quest_map(surf, ctx, mouse)

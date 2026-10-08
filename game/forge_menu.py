"""
Brother Hammerstein's Forge window (the Nexus tavern): F on him -> "Open the Forge".

Every recipe the Anvil knows, in four tabs - Temper, Reforge (UT), Fuse Shards, Stonework
(Set / Combine / Pry) - with NO cap (the old dialogue showed at most 3). Recipes you can't
afford are listed too, greyed out with what's missing. The detail panel shows the result
(before -> after for a temper / reforge), each ingredient with its owned count (red when
short), the Forge Ingot cost and, for stonework, the weapon's sockets with the stones in them.
The big FORGE button is disabled (with the reason) when you can't; destructive work (prying a
stone - it shatters - or anything that eats a T12+ item or 2+ Ingots) asks for a second
click. Forging plays a short hammering animation, then the result appears.

Logic (pure, no pygame): catalog / needs_confirm / recipe_key / apply / apply_request.
In co-op the window is just UI: it sends {"action": "forge_apply", **recipe_key(...)} and
the SERVER re-builds its own catalog, finds the identical recipe (same backpack slots, names
and label) and applies it - stale or made-up requests never match (apply_request).
"""
import copy
import math

import pygame

from game import forge, gems

TABS = (("temper", "Temper"), ("reforge", "Reforge (UT)"), ("fuse", "Fuse Shards"), ("stonework", "Stonework"))
STONE_GROUPS = (("set", "Set a stone"), ("combine", "Combine stones"), ("pry", "Pry a stone out"))
CONFIRM_TIER = 12        # eating an item of this tier or better asks twice
ANIM_TIME = 0.6          # the hammering before the result shows
RESULT_TIME = 5.0
FAIL = (220, 150, 90)


# ------------------------------------------------------------------ logic --
def catalog(player):
    """{tab: [recipe]} - everything, affordable first (stonework keeps Set/Combine/Pry order)."""
    out = {k: [] for k, _l in TABS}
    if player is None:
        return out
    for r in forge.forge_options(player, limit=None, include_blocked=True):
        out[r["kind"]].append(r)
    order = {k: i for i, (k, _l) in enumerate(STONE_GROUPS)}
    out["stonework"] = gems.stonework_options(player, limit=None, include_blocked=True)
    out["stonework"].sort(key=lambda r: (order[r["kind"]], not r["ok"]))
    for k in ("temper", "reforge", "fuse"):
        out[k].sort(key=lambda r: not r["ok"])
    return out


def _consumed(r):
    return list(r.get("use") or []) + ([r["gem"]] if r.get("gem") is not None else [])


def needs_confirm(r):
    """Pry (the stone shatters), or eating a T12+ item / 2+ Forge Ingots."""
    if r["kind"] == "pry":
        return True
    if len(r.get("ingots") or []) >= 2:
        return True
    return any(getattr(it, "tier", 0) >= CONFIRM_TIER and getattr(it, "shape", "") != "ingot" for it in _consumed(r))


def recipe_key(player, r):
    """How a client names a recipe over the wire: the backpack slots it consumes (+ their names)
    and its label. JSON-safe."""
    bag = player.backpack
    idx = []
    for it in _consumed(r) + list(r.get("ingots") or []):
        i = next((i for i, b in enumerate(bag) if b is it), None)
        if i is not None:
            idx.append(i)
    idx.sort()
    return {"kind": r["kind"], "idx": idx, "names": [bag[i].name for i in idx], "label": r["label"]}


def _key_tuple(k):
    return (k.get("kind"), list(k.get("idx") or []), list(k.get("names") or []), k.get("label"))


def apply(player, r):
    """Does the work. Returns {ok, msg, color, sfx, result (Item or None), feed: [(msg, color)]}."""
    if not r.get("ok"):
        return dict(ok=False, msg=r.get("why") or "You can't forge that yet.", color=FAIL, sfx="forge_fail",
                    result=None, feed=[])
    if r["kind"] in ("set", "combine", "pry"):
        n_before = len(player.backpack)
        ok, msg, col = gems.apply_stonework(player, r)
        res = player.backpack[-1] if ok and r["kind"] == "combine" and len(player.backpack) <= n_before else None
        sfx = {"set": "gem_set", "combine": "gem_combine", "pry": "gem_pry"}[r["kind"]] if ok else "forge_fail"
        return dict(ok=ok, msg=msg, color=col, sfx=sfx, result=res, feed=[(msg, col)])
    ok, msg, res = forge.apply_forge(player, r)
    feed = [(msg, res.color if res else FAIL)]
    if ok:
        sp = getattr(player, "story", None)
        if sp is not None:
            feed.extend(sp.on_event("forge"))  # Act III: forge something at the Anvil
    return dict(ok=ok, msg=msg, color=res.color if res else FAIL, sfx="forge_success" if ok else "forge_fail",
                result=res, feed=feed)


def apply_request(player, req):
    """The server side of "forge_apply": find the identical recipe in this player's own catalog
    and apply it, or refuse. Never trusts anything but the match."""
    refuse = dict(ok=False, color=FAIL, sfx="forge_fail", result=None, feed=[])
    if not isinstance(req, dict):
        return dict(refuse, msg="That recipe isn't possible any more.")
    try:
        want = _key_tuple(req)
    except TypeError:
        return dict(refuse, msg="That recipe isn't possible any more.")
    for recipes in catalog(player).values():
        for r in recipes:
            if _key_tuple(recipe_key(player, r)) != want:
                continue
            if not r["ok"]:
                return dict(refuse, msg=r["why"])
            if needs_confirm(r) and not req.get("confirmed"):
                return dict(refuse, msg="Brother Hammerstein wants you to confirm that one first.")
            return apply(player, r)
    return dict(refuse, msg="That recipe isn't possible any more.")


def result_preview(player, r):
    """The item the recipe makes (or the stone it sets / pries) - for icons."""
    if r.get("result") is not None:
        return r["result"]
    if r["kind"] == "set":
        return r["gem"]
    if r["kind"] == "pry":
        return gems.make_gem(*r["stone"])
    return None


def weapon_after(player, r):
    """A copy of the equipped weapon as it would be after a Set / Pry (None otherwise)."""
    w = getattr(player, "weapon", None)
    if w is None or r["kind"] not in ("set", "pry"):
        return None
    after = copy.copy(w)
    stones = [list(s) for s in gems.stones_in(w)]
    if r["kind"] == "set" and r["ok"]:
        stones.append([r["gem"].gem_kind, r["gem"].gem_grade])
    elif r["kind"] == "pry":
        stones = stones[:-1]
    after.gems = stones
    return after


# ----------------------------------------------------------------- window --
_FONTS = {}


def _font(size, bold=False):
    k = (size, bold)
    if k not in _FONTS:
        _FONTS[k] = pygame.font.SysFont("consolas", size, bold=bold)
    return _FONTS[k]


def _ui():
    from game import ui
    return ui


ROW_H = 46


class ForgeWindow:
    """One per client. on_apply(recipe, confirmed) -> result dict (single-player) or None (co-op:
    the server's "forge_result" arrives later via show_result). on_fx(sfx_key, color) plays a
    sound + sparks at the Anvil."""

    def __init__(self):
        self.open = False
        self.tab = TABS[0][0]
        self.sel = 0
        self.scroll = 0
        self.confirm = None      # recipe label awaiting its second click
        self.anim = None         # [time left, recipe, confirmed]
        self.result = None       # the last result dict + "t" left on screen
        self.waiting = False     # co-op: sent, waiting for the server
        self.t = 0.0
        self.on_apply = None
        self.on_fx = None

    # -- state --
    def is_open(self):
        return self.open

    def open_window(self):
        self.open = True
        self.confirm, self.anim, self.waiting = None, None, False
        self.scroll = 0

    def close(self):
        self.open = False
        self.confirm = None
        self.anim = None

    def recipes(self, player):
        return catalog(player)[self.tab]

    def rows(self, player):
        """[("header", text) | ("recipe", i)] - stonework gets Set / Combine / Pry sub-headers."""
        recs = self.recipes(player)
        if self.tab != "stonework":
            return [("recipe", i) for i in range(len(recs))]
        out, last = [], None
        for i, r in enumerate(recs):
            if r["kind"] != last:
                out.append(("header", dict(STONE_GROUPS)[r["kind"]]))
                last = r["kind"]
            out.append(("recipe", i))
        return out

    def selected(self, player):
        recs = self.recipes(player)
        if not recs:
            return None
        self.sel = max(0, min(len(recs) - 1, self.sel))
        return recs[self.sel]

    def set_tab(self, tab):
        if tab != self.tab:
            self.tab, self.sel, self.scroll, self.confirm, self.result = tab, 0, 0, None, None

    def _step_tab(self, d):
        keys = [k for k, _l in TABS]
        self.set_tab(keys[(keys.index(self.tab) + d) % len(keys)])

    def _move(self, player, d):
        n = len(self.recipes(player))
        if n:
            self.sel = max(0, min(n - 1, self.sel + d))
            self.confirm = None
            self._scroll_to(player)

    def _scroll_to(self, player):
        rows = self.rows(player)
        ri = next((j for j, (k, v) in enumerate(rows) if k == "recipe" and v == self.sel), 0)
        vis = self._visible_rows()
        if ri - (1 if ri > 0 and rows[ri - 1][0] == "header" else 0) < self.scroll:
            self.scroll = max(0, ri - 1)
        elif ri >= self.scroll + vis:
            self.scroll = ri - vis + 1

    def press_forge(self, player):
        """The FORGE button / Enter. Returns what happened: 'blocked', 'confirm', 'forging' or None."""
        if self.anim is not None or self.waiting:
            return None
        r = self.selected(player)
        if r is None:
            return None
        if not r["ok"]:
            if self.on_fx:
                self.on_fx("forge_fail", None)
            return "blocked"
        if needs_confirm(r) and self.confirm != r["label"]:
            self.confirm = r["label"]
            return "confirm"
        self.anim = [ANIM_TIME, r, self.confirm == r["label"]]
        self.confirm = None
        self.result = None
        if self.on_fx:
            self.on_fx("forge_hammer", None)
        return "forging"

    def update(self, dt, player):
        self.t += dt
        if self.result is not None:
            self.result["t"] -= dt
            if self.result["t"] <= 0:
                self.result = None
        if self.anim is None:
            return
        self.anim[0] -= dt
        if self.anim[0] > 0:
            return
        _t, r, confirmed = self.anim
        self.anim = None
        res = self.on_apply(r, confirmed) if self.on_apply else apply(player, r)
        if res is None:
            self.waiting = True  # co-op: the server answers with show_result
        else:
            self.show_result(res)

    def show_result(self, res):
        self.waiting = False
        self.result = dict(res, t=RESULT_TIME)
        if self.on_fx:
            self.on_fx(res.get("sfx") or ("forge_success" if res.get("ok") else "forge_fail"), res.get("color"))

    # -- layout --
    def rects(self):
        from game import constants as C
        w, h = min(1060, C.SCREEN_W - 30), min(680, C.SCREEN_H - 30)
        win = pygame.Rect(C.SCREEN_W // 2 - w // 2, C.SCREEN_H // 2 - h // 2, w, h)
        tab_w = (w - 32 - 3 * 6) // 4
        tabs = [(k, pygame.Rect(win.x + 16 + i * (tab_w + 6), win.y + 56, tab_w, 32)) for i, (k, _l) in enumerate(TABS)]
        top = win.y + 56 + 32 + 10
        lst = pygame.Rect(win.x + 16, top, 420, win.bottom - 38 - top)
        detail = pygame.Rect(lst.right + 14, top, win.right - 16 - (lst.right + 14), lst.h)
        button = pygame.Rect(detail.centerx - 140, detail.bottom - 96, 280, 50)
        close = pygame.Rect(win.right - 34, win.y + 8, 26, 24)
        return dict(win=win, tabs=tabs, list=lst, detail=detail, button=button, close=close)

    def _visible_rows(self):
        return max(1, self.rects()["list"].h // ROW_H)

    def _row_rect(self, r, i):
        return pygame.Rect(r["list"].x, r["list"].y + i * ROW_H, r["list"].w - 12, ROW_H - 4)

    # -- input --
    def handle_event(self, event, player):
        """True if the event belonged to the open window (it's modal: it takes every key/click)."""
        if not self.open:
            return False
        if event.type == pygame.KEYDOWN:
            k = event.key
            if k == pygame.K_ESCAPE:
                if self.confirm is not None:
                    self.confirm = None
                else:
                    self.close()
            elif k in (pygame.K_UP, pygame.K_w):
                self._move(player, -1)
            elif k in (pygame.K_DOWN, pygame.K_s):
                self._move(player, 1)
            elif k in (pygame.K_LEFT, pygame.K_a):
                self._step_tab(-1)
            elif k in (pygame.K_RIGHT, pygame.K_d, pygame.K_TAB):
                self._step_tab(-1 if (k == pygame.K_TAB and event.mod & pygame.KMOD_SHIFT) else 1)
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.press_forge(player)
            elif k == pygame.K_f:
                self.close()  # F again walks away from the Anvil
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            r = self.rects()
            if event.button in (4, 5):
                self._wheel(1 if event.button == 4 else -1, player)
                return True
            if event.button != 1:
                return True
            if r["close"].collidepoint(event.pos):
                self.close()
                return True
            for key, tr in r["tabs"]:
                if tr.collidepoint(event.pos):
                    self.set_tab(key)
                    return True
            rows = self.rows(player)
            for i in range(self._visible_rows()):
                j = self.scroll + i
                if j < len(rows) and rows[j][0] == "recipe" and self._row_rect(r, i).collidepoint(event.pos):
                    if self.sel != rows[j][1]:
                        self.confirm = None
                    self.sel = rows[j][1]
                    return True
            if r["button"].collidepoint(event.pos):
                self.press_forge(player)
            return True
        if event.type == pygame.MOUSEWHEEL:
            self._wheel(event.y, player)
            return True
        return event.type in (pygame.KEYUP, pygame.TEXTINPUT, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)

    def _wheel(self, dy, player):
        n = len(self.rows(player))
        self.scroll = max(0, min(max(0, n - self._visible_rows()), self.scroll - dy))

    # -- drawing --
    def draw(self, surf, player, mouse=(-1, -1), dt=1 / 60):
        from game import constants as C
        if not self.open:
            return
        self.update(dt, player)
        ui = _ui()
        dim = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        surf.blit(dim, (0, 0))
        r = self.rects()
        win = r["win"]
        pygame.draw.rect(surf, (10, 9, 12), win, border_radius=8)
        panel, _ = ui._ornate_panel(win.w, win.h, border=(205, 140, 70))
        surf.blit(panel, win.topleft)
        _anvil_icon(surf, win.x + 34, win.y + 30, (215, 160, 90))
        surf.blit(ui._FONT_L.render("Brother Hammerstein's Forge", True, (250, 222, 170)), (win.x + 62, win.y + 10))
        ing = sum(1 for it in (player.backpack if player else ()) if it.slot == "material" and it.shape == "ingot")
        it_t = _font(14, True).render(f"Forge Ingots: {ing}", True, (235, 200, 150))
        surf.blit(it_t, (r["close"].x - it_t.get_width() - 18, win.y + 14))
        ui._bevel_button(surf, r["close"], (140, 55, 55), hovered=r["close"].collidepoint(mouse))
        xt = ui._FONT_S.render("X", True, (255, 225, 225))
        surf.blit(xt, (r["close"].centerx - xt.get_width() // 2, r["close"].centery - xt.get_height() // 2))
        cat = catalog(player)
        for key, tr in r["tabs"]:
            on = key == self.tab
            ui._bevel_button(surf, tr, (110, 70, 34) if on else (40, 36, 46), hovered=tr.collidepoint(mouse))
            if on:
                pygame.draw.rect(surf, (255, 200, 120), tr, 2, border_radius=5)
            ready = sum(1 for x in cat[key] if x["ok"])
            label = dict(TABS)[key]
            t = _font(15, True).render(label, True, (255, 240, 210) if on else (205, 200, 212))
            c = _font(13, True).render(f"{ready}/{len(cat[key])}", True,
                                       (140, 230, 150) if ready else (160, 150, 150))
            surf.blit(t, (tr.x + 12, tr.centery - t.get_height() // 2))
            surf.blit(c, (tr.right - c.get_width() - 10, tr.centery - c.get_height() // 2))
        self._draw_list(surf, r, player, mouse)
        self._draw_detail(surf, r, player, mouse)
        hint = ui._FONT_S.render("Up/Down: recipe - Left/Right or Tab: section - Enter: FORGE - Esc: back / close",
                                 True, (150, 140, 130))
        surf.blit(hint, (win.centerx - hint.get_width() // 2, win.bottom - 27))

    def _draw_list(self, surf, r, player, mouse):
        ui = _ui()
        from game import sprites
        lst = r["list"]
        pygame.draw.rect(surf, (20, 18, 24), lst, border_radius=5)
        recs = self.recipes(player)
        rows = self.rows(player)
        if not recs:
            msg = {"temper": "No gear in your backpack to temper. Bring 3 items of the same tier.",
                   "reforge": "No UT weapon in your backpack to reforge.",
                   "fuse": "No Weapon Shards in your backpack to fuse.",
                   "stonework": "No gemstones in your backpack and none in your weapon."}[self.tab]
            for i, line in enumerate(ui._wrap_text(msg, ui._FONT_S, lst.w - 24)):
                surf.blit(ui._FONT_S.render(line, True, (170, 165, 160)), (lst.x + 12, lst.y + 12 + i * 18))
            return
        vis = self._visible_rows()
        self.scroll = max(0, min(max(0, len(rows) - vis), self.scroll))
        for i in range(vis):
            j = self.scroll + i
            if j >= len(rows):
                break
            kind, v = rows[j]
            rr = self._row_rect(r, i)
            if kind == "header":
                t = _font(13, True).render(v.upper(), True, (235, 190, 120))
                surf.blit(t, (rr.x + 8, rr.bottom - t.get_height() - 6))
                pygame.draw.line(surf, (120, 90, 55), (rr.x + 16 + t.get_width(), rr.bottom - 13), (rr.right - 4, rr.bottom - 13))
                continue
            rec = recs[v]
            sel = v == self.sel
            if sel:
                pygame.draw.rect(surf, (66, 50, 34), rr, border_radius=4)
                pygame.draw.rect(surf, (255, 200, 120), rr, 1, border_radius=4)
            elif rr.collidepoint(mouse):
                pygame.draw.rect(surf, (40, 34, 30), rr, border_radius=4)
            icon_r = pygame.Rect(rr.x + 5, rr.y + 3, 36, 36)
            ui._slot_frame(surf, icon_r, filled=True, accent=(205, 140, 70))
            it = result_preview(player, rec)
            if it is not None:
                img = pygame.transform.smoothscale(sprites.icon_of(it), (32, 32))
                if not rec["ok"]:
                    img = img.copy()
                    img.fill((110, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
                surf.blit(img, (icon_r.x + 2, icon_r.y + 2))
            chip_w = 74
            label = rec["label"]
            f = _font(13, sel)
            maxw = rr.w - 48 - chip_w - 10
            lines = ui._wrap_text(label, f, maxw)[:2]
            if len(ui._wrap_text(label, f, maxw)) > 2:
                lines[1] = lines[1][:-2].rstrip() + "."
            col = (255, 240, 205) if rec["ok"] else (150, 145, 150)
            for k, line in enumerate(lines):
                surf.blit(f.render(line, True, col), (rr.x + 48, rr.y + (13 if len(lines) == 1 else 4) + k * 16))
            chip = pygame.Rect(rr.right - chip_w - 4, rr.centery - 10, chip_w, 20)
            ready = rec["ok"]
            pygame.draw.rect(surf, (40, 92, 50) if ready else (92, 36, 36), chip, border_radius=10)
            pygame.draw.rect(surf, (120, 220, 130) if ready else (230, 110, 100), chip, 1, border_radius=10)
            t = _font(11, True).render(("+ READY" if ready else "x MISSING"), True, (230, 255, 230) if ready else (255, 220, 215))
            surf.blit(t, (chip.centerx - t.get_width() // 2, chip.centery - t.get_height() // 2))
        if len(rows) > vis:
            bar = pygame.Rect(lst.right - 7, lst.y + 2, 5, lst.h - 4)
            pygame.draw.rect(surf, (40, 36, 44), bar, border_radius=2)
            th = max(20, int(bar.h * vis / len(rows)))
            ty = bar.y + int((bar.h - th) * self.scroll / max(1, len(rows) - vis))
            pygame.draw.rect(surf, (190, 140, 80), (bar.x, ty, bar.w, th), border_radius=2)

    def _draw_detail(self, surf, r, player, mouse):
        ui = _ui()
        from game import sprites
        d = r["detail"]
        ui._vgrad(surf, d, (34, 29, 26), (22, 20, 22))
        pygame.draw.rect(surf, (120, 90, 55), d, 1, border_radius=5)
        rec = self.selected(player)
        x, y, w = d.x + 14, d.y + 12, d.w - 28
        fs = ui._FONT_S
        if rec is None:
            surf.blit(_font(16, True).render("Nothing to forge here yet", True, (230, 210, 170)), (x, y))
            self._draw_button(surf, r, None, mouse)
            return
        title = {"temper": "Temper", "reforge": "Reforge a UT", "fuse": "Fuse Weapon Shards", "set": "Set a stone",
                 "combine": "Combine stones", "pry": "Pry a stone out"}[rec["kind"]]
        surf.blit(_font(17, True).render(title, True, (250, 215, 150)), (x, y))
        y += 26
        # --- what goes in -> what comes out
        if rec["kind"] in ("temper", "reforge", "fuse", "combine"):
            before = rec["use"][0] if rec.get("use") else None
            after = rec.get("result")
            col_w = (w - 40) // 2
            y = max(self._item_card(surf, x, y, col_w, before, {"temper": "Uses 3 of this tier (lead item)",
                                                                   "fuse": "Uses 3 like this", "combine": "Uses 3 like this",
                                                                   "reforge": "Before"}[rec["kind"]]),
                    self._item_card(surf, x + col_w + 40, y, col_w, after, "You get"))
            ax = x + col_w + 8
            pygame.draw.polygon(surf, (235, 180, 100), [(ax, d.y + 70), (ax + 18, d.y + 80), (ax, d.y + 90)])
        else:
            y = self._draw_sockets(surf, x, y, w, player, rec)
        y += 6
        # --- ingredients
        pygame.draw.line(surf, (90, 70, 50), (x, y), (x + w, y))
        y += 6
        surf.blit(_font(14, True).render("Ingredients", True, (235, 200, 140)), (x, y))
        y += 22
        if not rec.get("needs"):
            surf.blit(fs.render("Nothing - but the stone in the socket shatters.", True, (230, 160, 140)), (x, y))
            y += 22
        for label, icon_item, have, need in rec.get("needs") or ():
            ir = pygame.Rect(x, y, 28, 28)
            ui._slot_frame(surf, ir, filled=True)
            if icon_item is not None:
                surf.blit(pygame.transform.smoothscale(sprites.icon_of(icon_item), (24, 24)), (x + 2, y + 2))
            surf.blit(fs.render(label, True, (225, 220, 215)), (x + 38, y + 6))
            short = have < need
            cnt = _font(14, True).render(f"{have} / {need}", True, (255, 110, 100) if short else (140, 230, 150))
            surf.blit(cnt, (x + w - cnt.get_width(), y + 6))
            if short:
                tag = _font(11, True).render("SHORT", True, (255, 130, 120))
                surf.blit(tag, (x + w - cnt.get_width() - tag.get_width() - 10, y + 8))
            y += 32
        ing = len(rec.get("ingots") or [])
        need_ing = next((n for (lab, _i, _h, n) in rec.get("needs") or () if lab == "Forge Ingot"), 0)
        cost_t = (f"Forge Ingot cost: {need_ing}" if need_ing else "Forge Ingot cost: free")
        surf.blit(_font(13, True).render(cost_t, True, (230, 190, 140)), (x, y + 2))
        y += 22
        if rec["ok"] and _consumed(rec):
            names = ", ".join(it.display_name for it in _consumed(rec))
            for line in ui._wrap_text("Consumes: " + names + (f" + {ing} Ingot{'s' if ing != 1 else ''}" if ing else ""),
                                      fs, w)[:3]:
                surf.blit(fs.render(line, True, (170, 160, 150)), (x, y))
                y += 17
        # --- result banner / the big button
        if self.result is not None:
            res = self.result
            br = pygame.Rect(d.x + 10, r["button"].y - 50, d.w - 20, 40)
            a = min(1.0, res["t"] / 0.6)
            pygame.draw.rect(surf, (30, 60, 34) if res["ok"] else (70, 30, 28), br, border_radius=6)
            pygame.draw.rect(surf, (140, 230, 150) if res["ok"] else (240, 120, 110), br, 1, border_radius=6)
            it = res.get("result")
            tx = br.x + 10
            if it is not None and hasattr(it, "shape"):
                surf.blit(pygame.transform.smoothscale(sprites.icon_of(it), (30, 30)), (br.x + 6, br.y + 5))
                tx = br.x + 44
            msg = res.get("msg", "")
            lines = ui._wrap_text(msg, fs, br.right - tx - 8)[:2]
            for k, line in enumerate(lines):
                t = fs.render(line, True, (230, 255, 230) if res["ok"] else (255, 220, 210))
                t.set_alpha(int(255 * a))
                surf.blit(t, (tx, br.y + (12 if len(lines) == 1 else 3) + k * 17))
        self._draw_button(surf, r, rec, mouse)

    def _item_card(self, surf, x, y, w, item, head):
        ui = _ui()
        from game import sprites
        surf.blit(_font(12, True).render(head.upper(), True, (190, 160, 120)), (x, y))
        y += 18
        if item is None:
            return y
        box = pygame.Rect(x, y, 44, 44)
        ui._slot_frame(surf, box, filled=True, accent=item.color)
        surf.blit(pygame.transform.smoothscale(sprites.icon_of(item), (40, 40)), (x + 2, y + 2))
        name_lines = ui._wrap_text(item.display_name, _font(13, True), w - 52)[:2]
        for k, line in enumerate(name_lines):
            surf.blit(_font(13, True).render(line, True, item.color), (x + 52, y + 4 + k * 16))
        y += 50
        for line in ui.item_stat_lines(item)[:5]:
            for sub in ui._wrap_text(line, ui._FONT_S, w)[:1]:
                surf.blit(ui._FONT_S.render(sub, True, (215, 212, 220)), (x, y))
                y += 17
        if getattr(item, "rune_effect", "") and item.description:
            for sub in ui._wrap_text(item.description, ui._FONT_S, w)[:5]:
                surf.blit(ui._FONT_S.render(sub, True, (175, 170, 180)), (x, y))
                y += 17
        return y

    def _draw_sockets(self, surf, x, y, w, player, rec):
        """The weapon's sockets as slots with their stones; the new stone pulses, a pried one cracks."""
        ui = _ui()
        from game import sprites
        weapon = getattr(player, "weapon", None)
        if rec["kind"] == "combine" or weapon is None:
            surf.blit(ui._FONT_S.render("No weapon in your hand - stones go into the weapon you hold.", True,
                                        (220, 170, 150)), (x, y))
            return y + 24
        surf.blit(_font(12, True).render("YOUR WEAPON", True, (190, 160, 120)), (x, y))
        y += 18
        box = pygame.Rect(x, y, 44, 44)
        ui._slot_frame(surf, box, filled=True, accent=weapon.color)
        surf.blit(pygame.transform.smoothscale(sprites.icon_of(weapon), (40, 40)), (x + 2, y + 2))
        surf.blit(_font(13, True).render(weapon.display_name, True, weapon.color), (x + 52, y + 4))
        n = gems.socket_count(weapon)
        surf.blit(ui._FONT_S.render(f"{n} socket{'s' if n != 1 else ''} (T0-4: 1, T5-9: 2, T10+: 3, UT/Divine: 2)",
                                    True, (175, 170, 165)), (x + 52, y + 24))
        y += 54
        stones = gems.stones_in(weapon)
        pulse = 0.5 + 0.5 * math.sin(self.t * 6)
        sx = x
        for i in range(n):
            sr = pygame.Rect(sx, y, 46, 46)
            pygame.draw.circle(surf, (14, 12, 16), sr.center, 22)
            pygame.draw.circle(surf, (130, 105, 70), sr.center, 22, 2)
            stone = stones[i] if i < len(stones) else None
            new = rec["kind"] == "set" and rec["ok"] and i == len(stones)
            if new:
                stone = (rec["gem"].gem_kind, rec["gem"].gem_grade)
            if stone is not None:
                img = sprites.icon_of(gems.make_gem(*stone))
                img = pygame.transform.smoothscale(img, (34, 34))
                if new:
                    img = img.copy()
                    img.set_alpha(int(140 + 115 * pulse))
                surf.blit(img, (sr.centerx - 17, sr.centery - 17))
            if new:
                pygame.draw.circle(surf, (255, 230, 150), sr.center, 23 + int(2 * pulse), 2)
                t = _font(11, True).render("NEW", True, (255, 235, 170))
                surf.blit(t, (sr.centerx - t.get_width() // 2, sr.bottom + 1))
            if rec["kind"] == "pry" and i == len(stones) - 1:
                c = (255, 90, 80)
                pygame.draw.line(surf, c, (sr.x + 10, sr.y + 10), (sr.right - 10, sr.bottom - 10), 3)
                pygame.draw.line(surf, c, (sr.right - 10, sr.y + 10), (sr.x + 10, sr.bottom - 10), 3)
                t = _font(11, True).render("SHATTERS", True, (255, 140, 130))
                surf.blit(t, (sr.centerx - t.get_width() // 2, sr.bottom + 1))
            sx += 58
        # what the stones do once this is done
        after = weapon_after(player, rec) or weapon
        tx = x + max(3, n) * 58 + 8
        tw = x + w - tx
        ty = y - 2
        lines = []
        for k, c in gems.counts(after).items():
            bond = gems.bond(c)
            mult = gems.RESONANT_MULT if c >= 3 else gems.ATTUNED_MULT if c == 2 else 1.0
            lines.append((f"{gems.STONES[k][0]} x{c}" + (f" - {bond} (x{mult})" if bond else ""), gems.color_of(k)))
            lines.append(("  " + gems.STONES[k][4], (200, 196, 200)))
            if c >= 3:
                lines.append(("  + " + gems.RESONANT[k], (255, 225, 150)))
        if not lines:
            lines = [("After prying: no stones left in it." if rec["kind"] == "pry" else "No stones set yet.",
                      (170, 165, 160))]
        if rec["kind"] == "set" and rec["ok"]:
            k = rec["gem"].gem_kind
            c = gems.counts(after).get(k, 0)
            if c == 2:
                lines.append(("Two alike: ATTUNED (x1.15)", (255, 225, 150)))
            elif c == 3:
                lines.append(("Three alike: RESONANT!", (255, 225, 150)))
        for text, col in lines[:6]:
            for sub in ui._wrap_text(text, ui._FONT_S, tw)[:2]:
                surf.blit(ui._FONT_S.render(sub, True, col), (tx, ty))
                ty += 16
        return max(y + 64, ty + 4)

    def _draw_button(self, surf, r, rec, mouse):
        ui = _ui()
        b = r["button"]
        anim = self.anim is not None or self.waiting
        ok = rec is not None and rec["ok"]
        confirm = rec is not None and self.confirm == rec["label"]
        if anim:
            base, label = (120, 80, 40), "Hammering..."
        elif not ok:
            base, label = (60, 56, 60), "FORGE"
        elif confirm:
            base, label = (170, 50, 40), "CONFIRM"
        else:
            base, label = (190, 120, 40), "FORGE"
        ui._bevel_button(surf, b, base, hovered=b.collidepoint(mouse) and ok and not anim, enabled=ok or anim)
        pygame.draw.rect(surf, (255, 215, 140) if ok and not anim else (110, 100, 100), b, 2, border_radius=6)
        t = _font(22, True).render(label, True, (255, 245, 225) if ok or anim else (150, 145, 150))
        surf.blit(t, (b.centerx - t.get_width() // 2 + (14 if anim else 0), b.centery - t.get_height() // 2))
        if anim:
            prog = 1.0 - (self.anim[0] / ANIM_TIME if self.anim else 0.5)
            _hammer(surf, b.x + 34, b.centery + 6, prog, self.t)
        sub = None
        if rec is not None and not ok:
            sub, col = rec["why"], (255, 140, 125)
        elif confirm:
            sub, col = ("It shatters - can't be undone. Click / Enter again to confirm, Esc cancels."
                        if rec["kind"] == "pry" else
                        "That eats rare stuff - click / Enter again to confirm, Esc cancels."), (255, 190, 160)
        elif ok and needs_confirm(rec) and not anim:
            sub, col = "Destructive: asks you to confirm.", (200, 175, 150)
        if sub:
            for k, line in enumerate(ui._wrap_text(sub, ui._FONT_S, r["detail"].w - 24)[:2]):
                t = ui._FONT_S.render(line, True, col)
                surf.blit(t, (r["detail"].centerx - t.get_width() // 2, b.bottom + 6 + k * 16))


def _anvil_icon(surf, cx, cy, col):
    pygame.draw.polygon(surf, col, [(cx - 14, cy - 6), (cx + 12, cy - 6), (cx + 16, cy - 2), (cx + 6, cy),
                                    (cx + 4, cy + 4), (cx - 6, cy + 4), (cx - 8, cy), (cx - 14, cy - 2)])
    pygame.draw.rect(surf, col, (cx - 9, cy + 4, 14, 4))
    pygame.draw.rect(surf, col, (cx - 12, cy + 8, 20, 4))


def _hammer(surf, x, y, prog, t):
    """A hammer swinging down onto a tiny anvil; sparks fly on each hit (3 hits per forge)."""
    phase = (prog * 3) % 1.0
    ang = -70 + 80 * min(1.0, phase / 0.7) if phase < 0.7 else 10 - 80 * ((phase - 0.7) / 0.3)
    _anvil_icon(surf, x, y + 6, (140, 140, 150))
    a = math.radians(ang - 90)
    px, py = x + 14, y - 14
    hx, hy = px + math.cos(a) * 22, py + math.sin(a) * 22
    pygame.draw.line(surf, (150, 105, 60), (px, py), (hx, hy), 3)
    perp = (math.cos(a + math.pi / 2) * 7, math.sin(a + math.pi / 2) * 7)
    pygame.draw.line(surf, (200, 200, 210), (hx - perp[0], hy - perp[1]), (hx + perp[0], hy + perp[1]), 6)
    if 0.62 < phase < 0.95:
        for i in range(7):
            ang2 = -math.pi / 2 + (i - 3) * 0.4 + math.sin(t * 13 + i) * 0.15
            d = 6 + (phase - 0.62) * 50
            sx, sy = x + math.cos(ang2) * d, y - 2 + math.sin(ang2) * d
            pygame.draw.circle(surf, (255, 200 - i * 10, 90), (int(sx), int(sy)), 2)

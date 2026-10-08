"""
Key rebinding (Options > Key bindings...). Shared by main.py and coop_client.py.

The game's input code keeps checking the DEFAULT keys (pygame.K_f for "interact", K_SPACE for
the ability...). Instead of rewriting every check, the clients translate each gameplay KEYDOWN
with translate_event(): a key bound to an action becomes that action's default key, and a
default key whose action was moved elsewhere becomes nothing. Held keys (WASD movement, Q/E
rotation) go through Pressed(), which answers "is the key for this action down?". Arrow keys
always move too, Esc / Enter / F11 / 1-8 can't be rebound.

Bindings live in settings["keys"] as {action: pygame key code}; a new key that's already used by
another action SWAPS the two, so nothing is ever left with two actions on one key.
"""
import pygame

# (action, label, default key) - the order is the window's order
ACTIONS = (
    ("move_up", "Move up", pygame.K_w),
    ("move_left", "Move left", pygame.K_a),
    ("move_down", "Move down", pygame.K_s),
    ("move_right", "Move right", pygame.K_d),
    ("ability", "Ability", pygame.K_SPACE),
    ("dash", "Dash / roll", pygame.K_LSHIFT),
    ("interact", "Talk / door / herb / mine / fish", pygame.K_f),
    ("nexus", "Nexus / leave dungeon", pygame.K_r),
    ("auto_fire", "Auto-fire toggle", pygame.K_i),
    ("dock_tab", "Dock tabs", pygame.K_TAB),
    ("quest_log", "Quest log", pygame.K_j),
    ("track", "Track quest marker", pygame.K_t),
    ("calendar", "Calendar", pygame.K_k),
    ("map", "Full map", pygame.K_m),
    ("rotate_left", "Rotate camera left", pygame.K_q),
    ("rotate_right", "Rotate camera right", pygame.K_e),
    ("reset_camera", "Reset camera", pygame.K_x),
    ("friends", "Friends (co-op)", pygame.K_l),
    ("options", "Options menu", pygame.K_o),
)
DEFAULT = {a: k for a, _l, k in ACTIONS}
LABEL = {a: l for a, l, _k in ACTIONS}
RESERVED = {pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_F11, pygame.K_BACKSPACE,
            *range(pygame.K_1, pygame.K_9)}
_NAMES = {"left shift": "Shift", "right shift": "R-Shift", "space": "Space", "tab": "Tab",
          "left ctrl": "Ctrl", "right ctrl": "R-Ctrl", "left alt": "Alt", "right alt": "R-Alt"}


def key_name(k):
    n = pygame.key.name(k) if k else ""
    return _NAMES.get(n, n.upper() if len(n) == 1 else n.title()) or "?"


def bindings():
    from game import settings
    saved = settings.get("keys") or {}
    return {a: int(saved.get(a, d)) for a, d in DEFAULT.items()}


def bound(action):
    return bindings()[action]


def to_default(key):
    """The default key the game's code checks for whatever action `key` is bound to.
    Unbound keys pass through, except a default key whose action now lives elsewhere."""
    b = bindings()
    for a, k in b.items():
        if k == key:
            return DEFAULT[a]
    if key in DEFAULT.values():
        return pygame.K_UNKNOWN  # its action was moved to another key
    return key


def translate_event(event):
    """A KEYDOWN/KEYUP with its key mapped through the bindings (other events unchanged)."""
    if event.type not in (pygame.KEYDOWN, pygame.KEYUP):
        return event
    k = to_default(event.key)
    if k == event.key:
        return event
    d = dict(event.dict)
    d["key"] = k
    return pygame.event.Event(event.type, d)


class Pressed:
    """pygame.key.get_pressed() through the bindings: pressed[pygame.K_w] means "is the key
    bound to Move up down?". Keys that aren't action defaults (arrows...) read as-is."""

    def __init__(self, keys=None):
        self.keys = keys if keys is not None else pygame.key.get_pressed()
        self.b = bindings()
        self.by_default = {d: a for a, d in DEFAULT.items()}

    def __getitem__(self, k):
        a = self.by_default.get(k)
        if a is not None:
            return bool(self.keys[self.b[a]])
        return bool(self.keys[k])

    def __len__(self):
        return len(self.keys)


def set_key(action, key):
    """Binds `action` to `key`. Returns the action that had that key (now swapped onto this
    action's old key) or None; raises ValueError for reserved keys."""
    from game import settings
    if key in RESERVED:
        raise ValueError(f"{key_name(key)} can't be rebound")
    b = bindings()
    other = next((a for a, k in b.items() if k == key and a != action), None)
    if other is not None:
        b[other] = b[action]
    b[action] = key
    settings.change("keys", {a: k for a, k in b.items() if k != DEFAULT[a]})
    return other


def reset():
    from game import settings
    settings.change("keys", {})


def help_lines():
    """ui.HELP_LINES with the CURRENT keys filled in (the Options screen's controls list)."""
    from game import ui
    b = bindings()
    n = {a: key_name(k) for a, k in b.items()}
    by_label = {
        "Move": f"{n['move_up']}{n['move_left']}{n['move_down']}{n['move_right']} / Arrows",
        "Auto-fire toggle": n["auto_fire"], "Ability": n["ability"], "Dash / roll": n["dash"],
        "Dock tabs (Items/Bag 2/Shards/Pet)": n["dock_tab"],
        "Talk / door / herb / mine / fish": n["interact"],
        "Quest log / track marker": f"{n['quest_log']} / {n['track']}",
        "Calendar (nights, events)": f"{n['calendar']} / Options",
        "Nexus / leave dungeon": n["nexus"], "Rotate camera": f"{n['rotate_left']} / {n['rotate_right']}",
        "Reset camera": n["reset_camera"], "Full map / zoom": f"{n['map']}, scroll, +/-",
        "Friends (co-op)": n["friends"], "Options menu": n["options"],
    }
    return [(label, by_label.get(label, keys)) for label, keys in ui.HELP_LINES]


class KeybindWindow:
    """The Key bindings window: Up/Down pick, Enter / click = press the new key (Esc cancels),
    R or the button resets everything. Modal while open."""
    ROW_H = 26

    def __init__(self):
        self.open = False
        self.sel = 0
        self.capturing = False
        self.msg = ""

    def open_window(self):
        self.open, self.capturing, self.msg = True, False, ""

    def rects(self):
        from game import constants as C
        w, h = 560, min(C.SCREEN_H - 30, 74 + len(ACTIONS) * self.ROW_H + 96)
        win = pygame.Rect(C.SCREEN_W // 2 - w // 2, C.SCREEN_H // 2 - h // 2, w, h)
        rows = [pygame.Rect(win.x + 16, win.y + 52 + i * self.ROW_H, w - 32, self.ROW_H - 2) for i in range(len(ACTIONS))]
        reset = pygame.Rect(win.x + 16, win.bottom - 44, 170, 30)
        close = pygame.Rect(win.right - 34, win.y + 8, 26, 24)
        return dict(win=win, rows=rows, reset=reset, close=close)

    def handle_event(self, event):
        if not self.open:
            return False
        if event.type == pygame.KEYDOWN:
            if self.capturing:
                if event.key == pygame.K_ESCAPE:
                    self.capturing, self.msg = False, "Cancelled."
                    return True
                action = ACTIONS[self.sel][0]
                try:
                    other = set_key(action, event.key)
                except ValueError as e:
                    self.msg = str(e)
                    return True
                self.capturing = False
                self.msg = (f"{LABEL[action]}: {key_name(event.key)}" +
                            (f" - swapped with {LABEL[other]} (now {key_name(bound(other))})" if other else ""))
                return True
            if event.key == pygame.K_ESCAPE:
                self.open = False
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.sel = (self.sel - 1) % len(ACTIONS)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.sel = (self.sel + 1) % len(ACTIONS)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.capturing, self.msg = True, ""
            elif event.key == pygame.K_r:
                reset()
                self.msg = "Every key is back to its default."
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            r = self.rects()
            if r["close"].collidepoint(event.pos):
                self.open, self.capturing = False, False
            elif r["reset"].collidepoint(event.pos):
                reset()
                self.capturing, self.msg = False, "Every key is back to its default."
            else:
                for i, rr in enumerate(r["rows"]):
                    if rr.collidepoint(event.pos):
                        self.sel, self.capturing, self.msg = i, True, ""
            return True
        return event.type in (pygame.KEYUP, pygame.TEXTINPUT, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION,
                              pygame.MOUSEWHEEL, pygame.MOUSEBUTTONDOWN)

    def draw(self, surf, mouse=(-1, -1)):
        if not self.open:
            return
        from game import ui
        from game import constants as C
        dim = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        surf.blit(dim, (0, 0))
        r = self.rects()
        win = r["win"]
        pygame.draw.rect(surf, (10, 9, 12), win, border_radius=8)
        panel, _ = ui._ornate_panel(win.w, win.h)
        surf.blit(panel, win.topleft)
        surf.blit(ui._FONT_M.render("Key bindings", True, (245, 225, 175)), (win.x + 18, win.y + 14))
        ui._bevel_button(surf, r["close"], (140, 55, 55), hovered=r["close"].collidepoint(mouse))
        xt = ui._FONT_S.render("X", True, (255, 225, 225))
        surf.blit(xt, (r["close"].centerx - xt.get_width() // 2, r["close"].centery - xt.get_height() // 2))
        b = bindings()
        for i, (a, label, d) in enumerate(ACTIONS):
            rr = r["rows"][i]
            sel = i == self.sel
            if sel or rr.collidepoint(mouse):
                pygame.draw.rect(surf, (70, 62, 98) if sel else (40, 38, 54), rr, border_radius=4)
            surf.blit(ui._FONT_S.render(label, True, (255, 236, 180) if sel else (215, 212, 225)),
                      (rr.x + 8, rr.centery - 8))
            box = pygame.Rect(rr.right - 120, rr.y + 2, 112, rr.h - 4)
            capture = sel and self.capturing
            pygame.draw.rect(surf, (90, 40, 40) if capture else (24, 22, 30), box, border_radius=4)
            pygame.draw.rect(surf, (255, 200, 120) if capture else ui.CHROME_GOLD_DIM, box, 1, border_radius=4)
            txt = "press a key..." if capture else key_name(b[a])
            col = (255, 220, 170) if capture else ((150, 230, 160) if b[a] != d else (225, 225, 235))
            t = ui._FONT_S.render(txt, True, col)
            surf.blit(t, (box.centerx - t.get_width() // 2, box.centery - t.get_height() // 2))
        ui._bevel_button(surf, r["reset"], (90, 70, 40), hovered=r["reset"].collidepoint(mouse))
        rt = ui._FONT_S.render("Reset to defaults (R)", True, (250, 235, 205))
        surf.blit(rt, (r["reset"].centerx - rt.get_width() // 2, r["reset"].centery - rt.get_height() // 2))
        hint = self.msg or "Enter / click: rebind - green = changed - a used key swaps - Esc closes"
        for k, line in enumerate(ui._wrap_text(hint, ui._FONT_S, win.w - 32)[:2]):
            ht = ui._FONT_S.render(line, True, (190, 220, 190) if self.msg else (150, 148, 160))
            surf.blit(ht, (win.x + 16, r["reset"].y - 40 + k * 17))

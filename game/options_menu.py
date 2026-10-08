"""
The O-key options menu's model + input handling, shared by main.py and
coop_client.py (drawing lives in ui.draw_help_overlay). Each client only
supplies its own client-specific bits (fullscreen switch, camera reset, the
full-map toggle, abandon-run vs. disconnect) through build_rows(); every
persisted setting row reads/writes game/settings.py directly.

Keyboard: Up/Down (W/S) select, Left/Right (A/D) change, Enter/Space
activates. Mouse: click a row to select + activate it; click on a slider bar
to set it to that point.
"""
import pygame

from game import settings

VOLUME_STEP = 0.1


class Row:
    """kind: 'toggle' (get()->bool, set(bool)), 'slider' (get()->0..1,
    set(float)), 'cycle' (get()->value, set(value), choices=[(value, text)]),
    or 'action' (action())."""

    def __init__(self, kind, label, section="", get=None, set=None, action=None, choices=None):
        self.kind, self.label, self.section = kind, label, section
        self.get, self.set, self.action, self.choices = get, set, action, choices or []

    def value_text(self):
        if self.kind == "toggle":
            return "ON" if self.get() else "OFF"
        if self.kind == "slider":
            return f"{int(round(self.get() * 100))}%"
        if self.kind == "cycle":
            cur = self.get()
            return next((text for val, text in self.choices if val == cur), str(cur))
        return ""


def _setting_row(kind, key, label, section, choices=None):
    return Row(kind, label, section, get=lambda: settings.get(key),
               set=lambda v: settings.change(key, v), choices=choices)


def build_rows(auto_fire_get, auto_fire_set, fullscreen_get, fullscreen_toggle,
               reset_camera, close, full_map=None, leave=None, journal=None, keybinds=None):
    """full_map: optional (get_open, toggle) pair, shown only when a map exists.
    leave: optional (label, fn) - "Abandon run" in single-player, "Disconnect" in co-op.
    journal: optional [(label, fn)] - the Quest Log / Dictionary windows (game/journal.py)."""
    rows = [
        Row("toggle", "Auto-fire", "Gameplay", get=auto_fire_get, set=auto_fire_set),
        _setting_row("slider", "master_volume", "Master volume", "Audio"),
        _setting_row("slider", "music_volume", "Music volume", "Audio"),
        _setting_row("slider", "sfx_volume", "Sound effects", "Audio"),
        _setting_row("toggle", "muted", "Mute all", "Audio"),
        Row("toggle", "Fullscreen", "Display", get=fullscreen_get, set=lambda _v: fullscreen_toggle()),
        _setting_row("cycle", "fps_cap", "FPS cap", "Display",
                     choices=[(30, "30"), (60, "60"), (120, "120"), (0, "Unlimited")]),
        _setting_row("toggle", "show_fps", "Show FPS", "Display"),
        _setting_row("cycle", "zoom", "Zoom (everything bigger)", "Display",
                     choices=[(1.0, "100%"), (1.1, "110%"), (1.25, "125%"), (1.5, "150%")]),
        _setting_row("slider", "luminosity", "Luminosity (night)", "Display"),
        _setting_row("toggle", "screen_shake", "Screen shake", "Effects"),
        _setting_row("toggle", "hit_stop", "Hit-stop (freeze on big hits)", "Effects"),
        _setting_row("cycle", "particles", "Particles", "Effects",
                     choices=[("off", "Off"), ("low", "Low"), ("high", "High")]),
        _setting_row("toggle", "auto_loot", "Auto-loot potions / shards / gems", "Loot"),
        _setting_row("cycle", "loot_hide_below", "Hide gear-only bags below", "Loot",
                     choices=[(n, f"T{n}" if n else "Off") for n in (0, 3, 5, 7, 9, 11)]),
        _setting_row("toggle", "loot_beams", "Light beams on rare drops", "Loot"),
        _setting_row("cycle", "colorblind", "Colour-blind palette", "Accessibility",
                     choices=[("off", "Off"), ("deuteranopia", "Deutan"), ("protanopia", "Protan"),
                              ("tritanopia", "Tritan")]),
        _setting_row("toggle", "bullet_outline", "Outline enemy bullets", "Accessibility"),
        _setting_row("slider", "tele_strength", "Telegraph strength", "Accessibility"),
        _setting_row("cycle", "text_size", "Text size", "Accessibility",
                     choices=[("normal", "Normal"), ("large", "Large")]),
        _setting_row("toggle", "reduce_flashing", "Reduce flashing", "Accessibility"),
    ]
    for label, fn in journal or ():
        rows.append(Row("action", label, "Journal", action=fn))
    if keybinds is not None:  # opens game/binds.py's Key bindings window
        rows.append(Row("action", "Key bindings...", "Controls", action=keybinds))
    rows.append(Row("action", "Reset camera rotation", "Actions", action=reset_camera))
    if full_map is not None:
        get_open, toggle = full_map
        rows.append(Row("toggle", "Full map", "Actions", get=get_open, set=lambda _v: toggle()))
    if leave is not None:
        rows.append(Row("action", leave[0], "Actions", action=leave[1]))
    rows.append(Row("action", "Close menu", "Actions", action=close))
    return rows


def adjust(row, step):
    """Left/Right on a row: flip a toggle, step a slider by 10%, cycle a choice."""
    if row.kind == "toggle":
        row.set(not row.get())
    elif row.kind == "slider":
        row.set(round(max(0.0, min(1.0, row.get() + step * VOLUME_STEP)), 2))
    elif row.kind == "cycle" and row.choices:
        vals = [v for v, _ in row.choices]
        i = vals.index(row.get()) if row.get() in vals else 0
        row.set(vals[(i + step) % len(vals)])


def activate(row):
    if row.kind == "action":
        row.action()
    elif row.kind in ("toggle", "cycle"):
        adjust(row, 1)


_UP = (pygame.K_UP, pygame.K_w)
_DOWN = (pygame.K_DOWN, pygame.K_s)
_LEFT = (pygame.K_LEFT, pygame.K_a)
_RIGHT = (pygame.K_RIGHT, pygame.K_d)
_ACTIVATE = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
MENU_KEYS = _UP + _DOWN + _LEFT + _RIGHT + _ACTIVATE  # keys the open menu swallows


def quit_confirm_verdict(event):
    """For the Esc quit-confirmation dialog: True = quit (Esc again, Enter/Y or the
    Quit button), False = stay (N or the Stay button), None = ignore this event."""
    if event.type == pygame.KEYDOWN:
        if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_y):
            return True
        if event.key == pygame.K_n:
            return False
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        from game import ui
        quit_rect, stay_rect = ui.quit_confirm_button_rects()
        if quit_rect.collidepoint(event.pos):
            return True
        if stay_rect.collidepoint(event.pos):
            return False
    return None


def handle_key(rows, selected, key):
    """Returns the new selected index if the key belonged to the menu, else None."""
    if not rows:
        return None
    selected %= len(rows)
    if key in _UP:
        return (selected - 1) % len(rows)
    if key in _DOWN:
        return (selected + 1) % len(rows)
    if key in _LEFT or key in _RIGHT:
        adjust(rows[selected], -1 if key in _LEFT else 1)
        return selected
    if key in _ACTIVATE:
        activate(rows[selected])
        return selected
    return None


def handle_click(rows, pos):
    """Returns the clicked row's index (after acting on it), or None."""
    from game import ui
    for i, rect in enumerate(ui.help_menu_item_rects(rows)):
        if not rect.collidepoint(pos):
            continue
        row = rows[i]
        bar = ui.help_slider_rect(rows, i)
        if row.kind == "slider" and bar is not None:
            if bar.inflate(12, 8).collidepoint(pos):
                frac = (pos[0] - bar.x) / max(1, bar.w)
                row.set(round(max(0.0, min(1.0, frac)) * 20) / 20)
        else:
            activate(row)
        return i
    return None

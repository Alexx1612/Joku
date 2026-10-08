"""
Persistent client settings (audio volumes, juice/graphics toggles, auto-fire,
fullscreen) - one small JSON file, same atomic tmp+os.replace idiom as
characters/accounts. Shared by main.py (single-player) and coop_client.py so
both clients read, write and apply the exact same settings.

Missing keys fall back to DEFAULTS and a corrupt/unreadable file just means
"all defaults" - a bad settings file must never stop the game from starting.
RR_SETTINGS_PATH overrides the file location (tests/run_all_checks.py points it
at a throwaway temp file so a player's own settings can't leak into the suite).
"""
import json
import os

from game import paths as _paths

SETTINGS_PATH = os.environ.get("RR_SETTINGS_PATH") or _paths.data_path("settings.json")

PARTICLE_LEVELS = ("off", "low", "high")
FPS_CAPS = (30, 60, 120, 0)  # 0 = unlimited

DEFAULTS = {
    "master_volume": 1.0,
    "music_volume": 1.0,
    "sfx_volume": 1.0,
    "muted": False,
    "screen_shake": True,
    "hit_stop": True,
    "particles": "high",
    "fps_cap": 60,
    "show_fps": True,
    "auto_fire": False,
    "fullscreen": False,
    "luminosity": 0.5,  # night darkness: 0 = pitch black outside lights, 0.5 = default horror dark, 1 = ~clear
    "panel_offsets": {},  # dragged chat / quest-log / calendar positions, see ui.PANEL_OFFSETS
    "dict_tags": [],  # the Dictionary's picked tag filter chips (game/codex.py TAGS keys)
    "calendar_filter": ["nights", "live"],  # the Calendar's filter chips (game/calendar_ui.py FILTERS)
    "auto_loot": True,       # walk over your bag: potions / shards / gems / ingots jump in (game/loot_filter.py)
    "loot_hide_below": 0,    # hide bags holding only gear under this tier (0 = show all)
    "loot_beams": True,      # a light column over bags with UT / Divine / T12+ inside
    "keys": {},              # rebound keys only, {action: pygame key code} (game/binds.py)
    # Options > Accessibility (game/access.py)
    "colorblind": "off",     # off / deuteranopia / protanopia / tritanopia - telegraph + enemy bullet palette
    "bullet_outline": False,
    "tele_strength": 0.5,    # telegraph opacity: 0 -> x0.5, 0.5 -> x1, 1 -> x1.5
    "text_size": "normal",   # normal / large
    "reduce_flashing": False,
    "zoom": 1.25,            # Options > Display > Zoom: everything drawn this much bigger (game/view_scale.py)
}

current = dict(DEFAULTS)


def _clean(data):
    """Coerce a loaded dict onto DEFAULTS' keys/types - unknown keys dropped,
    wrong-typed or out-of-range values replaced by the default."""
    out = dict(DEFAULTS)
    if not isinstance(data, dict):
        return out
    for key, default in DEFAULTS.items():
        val = data.get(key, default)
        if isinstance(default, bool):
            out[key] = val if isinstance(val, bool) else default
        elif key == "zoom":  # not a 0..1 fraction like the other floats
            out[key] = val if val in (1.0, 1.1, 1.25, 1.5) and not isinstance(val, bool) else default
        elif isinstance(default, float):
            out[key] = max(0.0, min(1.0, float(val))) if isinstance(val, (int, float)) and not isinstance(val, bool) else default
        elif key == "particles":
            out[key] = val if val in PARTICLE_LEVELS else default
        elif key == "fps_cap":
            out[key] = val if val in FPS_CAPS and not isinstance(val, bool) else default
        elif key == "loot_hide_below":
            from game.loot_filter import HIDE_CHOICES
            out[key] = val if val in HIDE_CHOICES and not isinstance(val, bool) else default
        elif key == "panel_offsets":
            out[key] = {k: [int(v[0]), int(v[1])] for k, v in val.items()
                        if isinstance(v, (list, tuple)) and len(v) == 2
                        and all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in v)
                        } if isinstance(val, dict) else {}
        elif key == "colorblind":
            out[key] = val if val in ("off", "deuteranopia", "protanopia", "tritanopia") else default
        elif key == "text_size":
            out[key] = val if val in ("normal", "large") else default
        elif key == "keys":
            out[key] = {str(a): int(k) for a, k in val.items()
                        if isinstance(k, int) and not isinstance(k, bool)} if isinstance(val, dict) else {}
        elif isinstance(default, list):
            out[key] = [v for v in val if isinstance(v, str)] if isinstance(val, (list, tuple)) else list(default)
    return out


def load(path=None):
    """Reads the settings file into `current` (and returns it)."""
    global current
    path = path or SETTINGS_PATH
    data = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    current = _clean(data)
    apply()
    return current


def save(path=None):
    path = path or SETTINGS_PATH
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass  # read-only install dir etc. - settings just won't persist this session


def get(key):
    return current.get(key, DEFAULTS[key])


def change(key, value, path=None):
    """Changes one setting, persists it, and applies it live."""
    current[key] = value
    current.update(_clean(current))
    save(path)
    apply()


def apply():
    """Pushes the current values into the live audio/vfx modules."""
    from game import audio, vfx, weather
    audio.set_volumes(current["master_volume"], current["music_volume"],
                      current["sfx_volume"], current["muted"])
    vfx.configure(shake=current["screen_shake"], hitstop=current["hit_stop"],
                  particles=current["particles"])
    weather.set_particle_level(current["particles"])
    try:
        from game import access
        access.apply_text_size()
    except Exception:
        pass  # fonts need pygame - only matters for the real clients
    try:
        from game import ui
        ui.PANEL_OFFSETS.clear()
        for name, off in current["panel_offsets"].items():
            ui.set_panel_offset(name, off)
    except Exception:
        pass  # ui needs pygame fonts - only matters for the real clients


def fps_cap():
    return get("fps_cap")

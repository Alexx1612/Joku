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

SETTINGS_PATH = os.environ.get("RR_SETTINGS_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")

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
    "panel_offsets": {},  # dragged chat / quest-log positions, see ui.PANEL_OFFSETS
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
        elif isinstance(default, float):
            out[key] = max(0.0, min(1.0, float(val))) if isinstance(val, (int, float)) and not isinstance(val, bool) else default
        elif key == "particles":
            out[key] = val if val in PARTICLE_LEVELS else default
        elif key == "fps_cap":
            out[key] = val if val in FPS_CAPS and not isinstance(val, bool) else default
        elif key == "panel_offsets":
            out[key] = {k: [int(v[0]), int(v[1])] for k, v in val.items()
                        if isinstance(v, (list, tuple)) and len(v) == 2
                        and all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in v)
                        } if isinstance(val, dict) else {}
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
        from game import ui
        ui.PANEL_OFFSETS.clear()
        for name, off in current["panel_offsets"].items():
            ui.set_panel_offset(name, off)
    except Exception:
        pass  # ui needs pygame fonts - only matters for the real clients


def fps_cap():
    return get("fps_cap")

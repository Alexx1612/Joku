"""
Regression check for the tactical weather hooks (Batch 12 track D) and the
portal difficulty readiness signpost (track E):
- a Tundra/Ice blizzard (snow) shrinks the minimap fog-of-war reveal radius
- a Desert/Wasteland sandstorm (sand) narrows the soft-aim-assist cone
- other weather kinds (or no weather) leave both unchanged
- a Dungeon Shard portal's difficulty label now includes a suggested level

Run with: .venv\\Scripts\\python.exe tests\\check_weather_tactical.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import weather
from game import ui
from game import minimap
from game.realm_sim import AUTO_AIM_CONE_DEG


def check_blizzard_shrinks_reveal_radius():
    base = minimap.REVEAL_RADIUS_TILES
    assert weather.reveal_radius_for("snow", base) < base
    assert weather.reveal_radius_for("rain", base) == base
    assert weather.reveal_radius_for("sand", base) == base
    assert weather.reveal_radius_for("ash", base) == base
    assert weather.reveal_radius_for(None, base) == base
    # real regression: reveal_radius_for("snow", ...) used to return a float
    # (base * 0.6), and minimap.reveal() passes it straight into range() as
    # a bound - range() rejects a float with a TypeError, so standing in
    # snow weather crashed the game outright. Cross-system integration
    # testing caught this; a real end-to-end reveal() call locks in the fix.
    snow_radius = weather.reveal_radius_for("snow", base)
    assert isinstance(snow_radius, int), f"reveal_radius_for must return an int, got {type(snow_radius)}"
    mm = minimap.MinimapState()
    mm.reveal(pygame.Vector2(320, 320), radius=snow_radius)  # must not raise TypeError
    print("check_blizzard_shrinks_reveal_radius: PASSED")


def check_sandstorm_narrows_aim_cone():
    base = AUTO_AIM_CONE_DEG
    assert weather.aim_cone_for("sand", base) < base
    assert weather.aim_cone_for("snow", base) == base
    assert weather.aim_cone_for("rain", base) == base
    assert weather.aim_cone_for("ash", base) == base
    assert weather.aim_cone_for(None, base) == base
    print("check_sandstorm_narrows_aim_cone: PASSED")


class _FakePortal:
    def __init__(self, difficulty=None, label=None):
        self.difficulty = difficulty
        self.label = label
        self.pos = pygame.Vector2(0, 0)


def check_difficulty_label_includes_suggested_level():
    for name in ("Easy", "Medium", "Hard"):
        text, color = ui._portal_label_text(_FakePortal(difficulty=name))
        assert name in text, f"{name} label lost its own name: {text!r}"
        suggested = ui.PORTAL_DIFFICULTY_SUGGESTED_LEVEL[name]
        assert suggested in text, f"{name} label missing suggested level {suggested!r}: {text!r}"
        assert color == ui.PORTAL_DIFFICULTY_COLORS[name]
    # a non-difficulty (hub) portal is untouched
    text, color = ui._portal_label_text(_FakePortal(label="The Reforging"))
    assert text == "The Reforging"
    # a bare portal with neither still no-ops
    assert ui._portal_label_text(_FakePortal()) == (None, None)
    print("check_difficulty_label_includes_suggested_level: PASSED")


if __name__ == "__main__":
    check_blizzard_shrinks_reveal_radius()
    check_sandstorm_narrows_aim_cone()
    check_difficulty_label_includes_suggested_level()
    print("PASSED: weather-tactical + difficulty-signpost checks all green.")

"""
Regression check for weather.py:weather_for_tile() - the fix for a real bug
where weather was looked up by the EXACT tile id underfoot (a decoration
tile is a different id than its biome's ground tile), silently going blank
the instant the player stood on any decoration. Covers normal cases (base
ground tiles) and the actual bug (decoration tiles within a biome must
resolve to the SAME weather, not blank).

Run with: .venv\\Scripts\\python.exe tests\\check_weather_per_biome.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import world


def check_base_ground_tiles():
    assert world.weather_for_tile(world.GRASS) == "rain"
    assert world.weather_for_tile(world.SNOW) == "snow"
    assert world.weather_for_tile(world.SAND) == "sand"
    assert world.weather_for_tile(world.ASH) == "ash"
    assert world.weather_for_tile(world.STONE) is None
    assert world.weather_for_tile(world.CAVE) is None
    print("check_base_ground_tiles: PASSED")


def check_decoration_tiles_keep_biome_weather():
    """The actual reported bug: a decoration tile within a biome must
    resolve to the SAME weather as that biome's own ground tile."""
    forest_rock = world.BIOME_PROP_TILE[("forest", "rock")]
    forest_tree = world.BIOME_PROP_TILE[("forest", "tree")]
    desert_boulder = world.BIOME_PROP_TILE[("desert", "boulder")]
    swamp_puddle = world.BIOME_PROP_TILE[("swamp", "puddle")]
    assert world.weather_for_tile(forest_rock) == "rain"
    assert world.weather_for_tile(forest_tree) == "rain"
    assert world.weather_for_tile(desert_boulder) == "sand"
    assert world.weather_for_tile(swamp_puddle) == "rain"

    # edge case: EVERY decoration kind in a weather-bearing biome must resolve,
    # not just a couple of hand-picked ones
    for kind in world.BIOME_PROP_KINDS:
        tile_id = world.BIOME_PROP_TILE[("desert", kind)]
        assert world.weather_for_tile(tile_id) == "sand", f"desert/{kind} lost its weather"
    print("check_decoration_tiles_keep_biome_weather: PASSED")


def check_unresolvable_tile_returns_none():
    assert world.weather_for_tile(99999) is None
    assert world.weather_for_tile(None) is None
    print("check_unresolvable_tile_returns_none: PASSED")


if __name__ == "__main__":
    check_base_ground_tiles()
    check_decoration_tiles_keep_biome_weather()
    check_unresolvable_tile_returns_none()
    print("PASSED: weather-per-biome checks all green.")

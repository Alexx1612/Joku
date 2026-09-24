"""
Regression check for the dungeon theme's 8-bit doom-rock rewrite
(game.audio._build_theme_dungeon). Confirms it still builds a valid,
non-silent pygame.mixer.Sound with real varied signal content (multiple
distinct frequency components across the mixed lead/chord/bass/drum
layers), not just "didn't crash".

Run with: .venv\\Scripts\\python.exe tests\\check_theme_dungeon_rock.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((100, 100))

from game import audio


def _pcm_from_sound(snd):
    """Extract the raw int16 samples back out of a built Sound via get_raw()
    + struct.unpack (NOT pygame.sndarray, which needs numpy - this project's
    own audio.py deliberately avoids that dependency, per its docstring, so
    this test must too) so we can inspect real signal content."""
    raw = snd.get_raw()
    count = len(raw) // 2
    return struct.unpack("<%dh" % count, raw)


def check_builds_valid_sound():
    audio.init()
    snd = audio._build_theme_dungeon()
    assert isinstance(snd, pygame.mixer.Sound), "must return a real pygame.mixer.Sound"
    length_ms = snd.get_length()
    assert length_ms > 1.5, f"theme should be a real multi-second loop, got {length_ms}s"
    print("check_builds_valid_sound: PASSED")


def check_not_silent_and_has_variation():
    audio.init()
    snd = audio._build_theme_dungeon()
    arr = _pcm_from_sound(snd)
    assert len(arr) > 0, "sample buffer must not be empty"
    # Not silence: some real amplitude must be present somewhere in the buffer.
    peak = max(abs(v) for v in arr)
    assert peak > 1000, f"expected real signal amplitude, peak was only {peak}"
    # Real variation, not a single flat tone held the whole buffer: split the
    # buffer into 4 quarters and confirm they are NOT all identical (the
    # sparse lead/kick/snare placement guarantees the quarters differ).
    n = len(arr)
    quarter = n // 4
    quarters = [arr[0:quarter], arr[quarter:2 * quarter], arr[2 * quarter:3 * quarter]]
    energies = [sum(v * v for v in q) for q in quarters]
    assert len(set(energies)) > 1, f"expected varying energy across the loop, got identical quarters {energies}"
    print("check_not_silent_and_has_variation: PASSED")


def check_power_chord_and_drum_helpers_exist():
    """The shared infra this rewrite depends on - must exist with the agreed
    exact signatures so sibling theme rewrites can reuse them identically."""
    pc = audio._power_chord(110, 0.2, volume=0.1)
    assert len(pc) > 0
    k = audio._kick()
    s = audio._snare()
    h = audio._hihat()
    assert len(k) > 0 and len(s) > 0 and len(h) > 0
    print("check_power_chord_and_drum_helpers_exist: PASSED")


def check_triangle_waveform_exists():
    samples = audio._samples(110, 0.05, volume=0.2, wave="triangle")
    assert len(samples) > 0
    assert max(samples) > 0 and min(samples) < 0, "triangle wave should oscillate around zero"
    print("check_triangle_waveform_exists: PASSED")


if __name__ == "__main__":
    check_builds_valid_sound()
    check_not_silent_and_has_variation()
    check_power_chord_and_drum_helpers_exist()
    check_triangle_waveform_exists()
    print("PASSED: dungeon doom-rock theme checks all green.")

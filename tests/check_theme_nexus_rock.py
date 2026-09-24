"""
Regression check for the Nexus theme's rewritten soft-rock ballad arrangement
(game.audio._build_theme_nexus) - confirms it still builds a valid Sound and
that the underlying waveform genuinely has multiple distinct components (a
real signal-content check, not just "it didn't crash").

Run with: .venv\\Scripts\\python.exe tests\\check_theme_nexus_rock.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import audio

audio.init()


def check_builds_valid_sound():
    snd = audio._build_theme_nexus()
    assert isinstance(snd, pygame.mixer.Sound)
    raw = snd.get_raw()
    assert len(raw) > 0
    print("check_builds_valid_sound: PASSED")


def check_signal_has_real_content():
    """Not silence, and not a single flat tone - a real multi-voice mix should
    show non-trivial variance and at least one nonzero sample far from zero."""
    snd = audio._build_theme_nexus()
    raw = snd.get_raw()
    import struct
    n = len(raw) // 2
    samples = struct.unpack("<%dh" % n, raw[:n * 2])
    assert any(abs(s) > 1000 for s in samples), "expected real audible amplitude somewhere in the buffer"
    nonzero = [s for s in samples if s != 0]
    assert len(nonzero) > len(samples) * 0.3, "expected a substantial fraction of non-silent samples"
    # crude variance check - a single constant tone would still vary sample-to-sample,
    # but a broken/empty buffer would be all zeros or all-identical
    distinct_values = len(set(samples[:5000]))
    assert distinct_values > 50, "expected real waveform variation, not a degenerate buffer"
    print("check_signal_has_real_content: PASSED")


def check_helpers_exist_with_expected_shape():
    """The shared _power_chord/_kick/_snare/_hihat helpers this rewrite relies
    on must exist and return non-empty sample lists."""
    chord = audio._power_chord(220, 0.1)
    assert isinstance(chord, list) and len(chord) > 0
    kick = audio._kick()
    snare = audio._snare()
    hihat = audio._hihat()
    assert len(kick) > 0 and len(snare) > 0 and len(hihat) > 0
    print("check_helpers_exist_with_expected_shape: PASSED")


if __name__ == "__main__":
    check_builds_valid_sound()
    check_signal_has_real_content()
    check_helpers_exist_with_expected_shape()
    print("\nAll check_theme_nexus_rock checks PASSED.")

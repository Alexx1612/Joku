"""
Regression check for game.audio._build_theme_realm() - the rewritten
original 8-bit rock-anthem arrangement (square-wave lead riff, power-chord
rhythm guitar, triangle bass, kick/snare/hi-hat beat). Confirms the theme
builder still returns a valid, non-silent, multi-frequency Sound buffer
after the rewrite, not just "didn't raise."

Run with: .venv\\Scripts\\python.exe tests\\check_theme_realm_rock.py
"""
import os
import sys
import math
import struct

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import audio


def _sound_to_samples(snd):
    raw = snd.get_raw()
    n = len(raw) // 2
    samples = struct.unpack("<%dh" % n, raw)
    if audio._channels == 2:
        samples = samples[0::2]
    return samples


def _dominant_freqs(samples, sample_rate, window):
    """A crude but real per-window zero-crossing-rate frequency estimate -
    good enough to confirm multiple distinct pitches are actually present
    across a buffer, without pulling in a real FFT dependency."""
    freqs = []
    step = window
    for start in range(0, len(samples) - window, step):
        chunk = samples[start:start + window]
        crossings = sum(1 for i in range(1, len(chunk)) if (chunk[i - 1] < 0) != (chunk[i] < 0))
        freqs.append(crossings * sample_rate / (2.0 * window))
    return freqs


def check_returns_valid_sound():
    snd = audio._build_theme_realm()
    assert isinstance(snd, pygame.mixer.Sound), "must return a real pygame.mixer.Sound"
    raw = snd.get_raw()
    assert len(raw) > 1000, "buffer must be a real, non-trivial length"
    print("PASS: _build_theme_realm returns a valid non-empty Sound")


def check_not_silence():
    snd = audio._build_theme_realm()
    samples = _sound_to_samples(snd)
    peak = max(abs(s) for s in samples)
    assert peak > 5000, f"expected real audible signal, peak amplitude was only {peak}"
    nonzero_frac = sum(1 for s in samples if s != 0) / len(samples)
    assert nonzero_frac > 0.5, f"expected mostly non-silent buffer, only {nonzero_frac:.2%} nonzero"
    print(f"PASS: buffer is real audio, not silence (peak={peak}, nonzero={nonzero_frac:.2%})")


def check_multiple_frequency_components():
    """Confirms the arrangement actually layers distinct voices (lead, power
    chord, bass, drums) rather than collapsing to one flat tone - samples
    several 40ms windows across the loop and checks the estimated pitch
    actually varies, which a single static tone could never produce."""
    snd = audio._build_theme_realm()
    samples = _sound_to_samples(snd)
    window = int(audio.SAMPLE_RATE * 0.04)
    freqs = _dominant_freqs(samples, audio.SAMPLE_RATE, window)
    freqs = [f for f in freqs if f > 20]  # drop near-silent windows (rests between notes)
    assert len(freqs) >= 4, "expected several non-silent windows across the 2-second loop"
    distinct = {round(f / 20) for f in freqs}  # bucket into ~20Hz bins
    assert len(distinct) >= 3, f"expected varied pitch content across the loop, got buckets {distinct}"
    print(f"PASS: theme has real frequency variation across {len(distinct)} distinct pitch buckets")


def check_matches_theme_builders_registry():
    assert audio._THEME_BUILDERS["realm"] is audio._build_theme_realm
    print("PASS: _THEME_BUILDERS['realm'] still points at the rewritten builder")


if __name__ == "__main__":
    audio.init()
    check_returns_valid_sound()
    check_not_silence()
    check_multiple_frequency_components()
    check_matches_theme_builders_registry()
    print("\nALL CHECKS PASSED (check_theme_realm_rock.py)")

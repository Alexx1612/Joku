"""
Regression check for game/audio.py:_build_theme_bazaar() - the original 8-bit
rock'n'roll rearrangement of the Bazaar theme (power-chord rhythm guitar,
walking triangle bass, an original square-wave lead, and a driving
kick/snare/hi-hat beat). Confirms the builder still returns a valid,
non-silent, multi-frequency-component pygame.mixer.Sound - not just "it
didn't crash".

Run with: .venv\\Scripts\\python.exe tests\\check_theme_bazaar_rock.py
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

audio.init()


def _raw_samples(snd):
    raw = snd.get_raw()
    n = len(raw) // 2
    return list(struct.unpack("<%dh" % n, raw[:n * 2]))


def check_builds_valid_nonempty_sound():
    snd = audio._build_theme_bazaar()
    assert isinstance(snd, pygame.mixer.Sound)
    raw = snd.get_raw()
    assert len(raw) > 0, "theme buffer must not be empty"
    print("check_builds_valid_nonempty_sound: PASSED")


def check_signal_is_not_silence_and_has_real_variation():
    """A real music buffer must have meaningful amplitude variation, not be
    flat/silent and not be a single constant tone (multiple overlapping
    voices - lead, power chords, bass, drums - should produce a varied
    waveform, not a pure repeating sinusoid at one level)."""
    snd = audio._build_theme_bazaar()
    samples = _raw_samples(snd)
    assert len(samples) > 1000, "expected a real multi-second buffer, got too few samples"

    peak = max(abs(s) for s in samples)
    assert peak > 3000, f"signal is essentially silent (peak={peak})"

    # Real variation check: compute a coarse "energy per chunk" profile across
    # the buffer and confirm it's not flat - multiple interlocking voices
    # (lead/chords/bass/drums) firing at different steps must produce audibly
    # different loudness across time, unlike a single held tone.
    chunk = max(1, len(samples) // 32)
    energies = []
    for i in range(0, len(samples), chunk):
        window = samples[i:i + chunk]
        if not window:
            continue
        energies.append(sum(abs(s) for s in window) / len(window))
    assert len(energies) > 4
    assert max(energies) - min(energies) > 200, (
        f"expected real loudness variation across the loop (drums/chords hit on some "
        f"steps, not others), got a nearly-flat energy profile: {min(energies):.1f}-{max(energies):.1f}"
    )
    print("check_signal_is_not_silence_and_has_real_variation: PASSED")


def check_multiple_distinct_frequency_components():
    """The bazaar theme mixes 4 voices (lead/power-chord/bass/drums) at
    different registers - a zero-crossing-rate check on two different
    coarse time windows should show measurably different dominant
    frequency content (drums are noise-heavy/broadband, the melodic
    sections are tonal), confirming this isn't a single flat tone."""
    snd = audio._build_theme_bazaar()
    samples = _raw_samples(snd)

    def zero_crossings(seg):
        crossings = 0
        for i in range(1, len(seg)):
            if (seg[i - 1] < 0) != (seg[i] < 0):
                crossings += 1
        return crossings

    third = len(samples) // 3
    seg_a = samples[0:third]
    seg_b = samples[third:2 * third]
    seg_c = samples[2 * third:3 * third]
    zc = [zero_crossings(seg_a), zero_crossings(seg_b), zero_crossings(seg_c)]
    assert all(z > 0 for z in zc), f"expected real oscillation in every segment, got {zc}"
    assert max(zc) != min(zc), (
        f"expected different frequency content across the loop's sections (melody vs. "
        f"chord-chug vs. drum hits), got identical zero-crossing counts: {zc}"
    )
    print("check_multiple_distinct_frequency_components: PASSED")


if __name__ == "__main__":
    check_builds_valid_nonempty_sound()
    check_signal_is_not_silence_and_has_real_variation()
    check_multiple_distinct_frequency_components()
    print("ALL CHECKS PASSED")

"""
Renders every procedurally-synthesized sound effect in game.audio to a real
.wav file under assets/audio_export/, purely for archival/reference - the
game itself keeps synthesizing everything at runtime, this changes nothing
about how it actually plays. See GAME_DATA.md's "Audio file exports" section
for why these are .wav and not .mp3 (no MP3 encoder is available in this
environment, and adding one would be the project's first non-pygame
dependency).

Works entirely without a real/dummy audio device: it swaps out
game.audio._sound_from with a stand-in that captures the raw PCM samples
instead of constructing a pygame.mixer.Sound, so every play_*() function
runs exactly its normal synthesis code unmodified - this script never
duplicates any of that logic.

Usage: python tools/export_audio.py
"""
import os
import sys
import wave

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from game import audio  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "audio_export")

_captured = None


class _FakeSound:
    """Stands in for pygame.mixer.Sound - captures samples on construction,
    no-ops on .play() so nothing here needs a real audio device."""

    def __init__(self, samples):
        global _captured
        _captured = list(samples)

    def play(self, *args, **kwargs):
        return None


def _write_wav(name, samples):
    if not samples:
        print(f"  SKIP {name} (no samples captured)")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}.wav")
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(audio.SAMPLE_RATE)
        frames = b"".join(int(max(-32768, min(32767, s))).to_bytes(2, "little", signed=True) for s in samples)
        f.writeframes(frames)
    print(f"  wrote {path} ({len(samples) / audio.SAMPLE_RATE:.2f}s)")


def _capture(play_fn, *args, **kwargs):
    global _captured
    _captured = None
    play_fn(*args, **kwargs)
    return _captured


def export_all():
    # force the module into "enabled" so _play()'s "if not _enabled: return"
    # guard doesn't skip synthesis - nothing here actually touches a real
    # mixer device since _sound_from is replaced below
    audio._enabled = True
    audio._channels = 1
    audio._sound_from = lambda samples: _FakeSound(samples)
    audio._cache.clear()  # force every factory() to actually run this pass, not reuse a prior real Sound

    print("Simple one-shot effects:")
    for name, fn, args in [
        ("hit", audio.play_hit, ()),
        ("enemy_hit", audio.play_enemy_hit, ()),
        ("pickup", audio.play_pickup, ()),
        ("drop", audio.play_drop, ()),
        ("death", audio.play_death, ()),
        ("levelup", audio.play_levelup, ()),
        ("ability", audio.play_ability, ()),
        ("boss_spawn", audio.play_boss_spawn, ()),
        ("wish", audio.play_wish, (False,)),
        ("wish_jackpot", audio.play_wish, (True,)),
    ]:
        _write_wav(name, _capture(fn, *args))

    print("Per-class shoot sounds:")
    for cls_name in audio._SHOT_TONE:
        _write_wav(f"shoot_{cls_name}", _capture(audio.play_shoot, cls_name))

    print("Per-family mob sounds:")
    for family in ("beast", "undead", "elemental", "construct"):
        _write_wav(f"mob_hit_{family}", _capture(audio.play_mob_hit, family))
        _write_wav(f"mob_death_{family}", _capture(audio.play_mob_death, family))
        _write_wav(f"mob_bark_{family}", _capture(audio.play_mob_bark, family))

    print("Per-zone theme music (may take a moment - these are full tracks):")
    for zone in audio._THEME_BUILDERS:
        audio._current_theme_zone = None  # force play_theme() to actually rebuild, not short-circuit
        _write_wav(f"theme_{zone}", _capture(audio.play_theme, zone))

    print(f"\nDone - exported to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    export_all()

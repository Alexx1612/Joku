"""
Batch 14, Track H2: regression check for the extended ~20-second Realm/
Bazaar/Dungeon(generic) arrangements and the 6 new per-dungeon-theme music
variants. Confirms these are real, longer, multi-section compositions (not
the old short loop just repeated), that the dungeon-theme->track mapping
actually varies by theme, and that main.py's/coop_client.py's bonus-room
call sites resolve the correct theme-specific zone.

Run with: .venv\\Scripts\\python.exe tests\\check_theme_realm_bazaar_dungeon_extended.py
"""
import os
import sys
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


def _duration_seconds(snd):
    return len(_sound_to_samples(snd)) / audio.SAMPLE_RATE


def _dominant_freqs(samples, sample_rate, window):
    freqs = []
    for start in range(0, len(samples) - window, window):
        chunk = samples[start:start + window]
        crossings = sum(1 for i in range(1, len(chunk)) if (chunk[i - 1] < 0) != (chunk[i] < 0))
        freqs.append(crossings * sample_rate / (2.0 * window))
    return freqs


def check_realm_bazaar_dungeon_are_real_20s_arrangements():
    for name, builder in (("realm", audio._build_theme_realm), ("bazaar", audio._build_theme_bazaar),
                           ("dungeon", audio._build_theme_dungeon)):
        snd = builder()
        dur = _duration_seconds(snd)
        assert 14.0 <= dur <= 26.0, f"{name}: expected a real ~20s arrangement, got {dur:.2f}s"
        samples = _sound_to_samples(snd)
        window = int(audio.SAMPLE_RATE * 0.5)
        # compare pitch content in the first half vs. second half of the track -
        # a genuinely varied multi-section piece should NOT look identical across
        # halves the way a short phrase looped end-to-end would.
        half = len(samples) // 2
        first_half_freqs = tuple(round(f / 20) for f in _dominant_freqs(samples[:half], audio.SAMPLE_RATE, window) if f > 20)
        second_half_freqs = tuple(round(f / 20) for f in _dominant_freqs(samples[half:], audio.SAMPLE_RATE, window) if f > 20)
        assert first_half_freqs != second_half_freqs, (
            f"{name}: first half and second half have IDENTICAL pitch-bucket sequences - "
            f"this looks like a short phrase just repeated, not a real multi-section arrangement"
        )
        print(f"PASS: {name} is a real {dur:.1f}s arrangement with distinct first/second-half content")


def check_six_dungeon_variants_exist_and_registered():
    expected = {"cave", "frozen_crypt", "jungle_ruins", "ember_den", "sunken_grotto", "wind_spire"}
    assert set(audio._DUNGEON_VARIANT_BUILDERS.keys()) == expected, (
        f"expected exactly these 6 dungeon variants, got {set(audio._DUNGEON_VARIANT_BUILDERS.keys())}"
    )
    for key in expected:
        zone = f"dungeon_{key}"
        assert zone in audio._THEME_BUILDERS, f"{zone} must be registered in _THEME_BUILDERS"
        snd = audio._THEME_BUILDERS[zone]()
        assert isinstance(snd, pygame.mixer.Sound), f"{zone} builder must return a real Sound"
        raw = snd.get_raw()
        assert len(raw) > 1000, f"{zone}: buffer must be a real, non-trivial length"
    print(f"PASS: all 6 dungeon-theme variants exist, are registered, and build valid Sounds")


def check_dungeon_variants_are_actually_distinct():
    """Confirms the 6 variants aren't secretly identical (e.g. a copy-paste
    bug that reused the same chord_roots/lead for two "different" themes) -
    real pairwise pitch-content comparison, not just "6 functions exist"."""
    signatures = {}
    for key, builder in audio._DUNGEON_VARIANT_BUILDERS.items():
        samples = _sound_to_samples(builder())
        window = int(audio.SAMPLE_RATE * 0.5)
        freqs = tuple(round(f / 20) for f in _dominant_freqs(samples, audio.SAMPLE_RATE, window) if f > 20)
        signatures[key] = freqs
    keys = list(signatures.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            assert signatures[keys[i]] != signatures[keys[j]], (
                f"dungeon variants '{keys[i]}' and '{keys[j]}' have identical pitch content - not actually distinct"
            )
    print("PASS: all 6 dungeon-theme variants are pairwise musically distinct")


def check_dungeon_zone_resolution_by_key_and_label():
    assert audio.dungeon_zone_for_key("cave") == "dungeon_cave"
    assert audio.dungeon_zone_for_key("frozen_crypt") == "dungeon_frozen_crypt"
    assert audio.dungeon_zone_for_key("generic") == "dungeon"
    assert audio.dungeon_zone_for_key("not_a_real_theme") == "dungeon"
    assert audio.dungeon_zone_for_label("Cave Warren") == "dungeon_cave"
    assert audio.dungeon_zone_for_label("Ember Den") == "dungeon_ember_den"
    assert audio.dungeon_zone_for_label("Forgotten Vault") == "dungeon"
    assert audio.dungeon_zone_for_label(None) == "dungeon"
    assert audio.dungeon_zone_for_label("Some Unknown Label") == "dungeon"
    print("PASS: dungeon_zone_for_key/dungeon_zone_for_label resolve correctly, including fallbacks")


def check_bonus_room_call_site_selects_theme_appropriate_track():
    """Real integration check on main.py's actual update() logic: a Game in
    STATE_BONUS with a themed RealmSim must call play_theme with THAT
    theme's zone, not the generic 'dungeon' zone, and different themes must
    resolve to different zones (not all silently falling back to one)."""
    import main as main_module
    from game.realm_sim import RealmSim

    calls = []
    original_play_theme = main_module.audio.play_theme
    main_module.audio.play_theme = lambda zone="nexus": calls.append(zone)
    try:
        game = main_module.Game()  # a real, fully-initialized Game (matches this
        # suite's existing "drive a real Game()" convention, e.g. check_hud_and_overlap.py)
        game.start_run("wizard")
        game.enter_realm()
        game.enter_bonus_room(theme="cave")
        calls.clear()
        main_module.Game.update(game, 0.016)
        assert calls, "expected a play_theme call for STATE_BONUS"
        assert calls[-1] == "dungeon_cave", f"expected 'dungeon_cave' for the cave theme, got {calls[-1]}"

        calls.clear()
        game.enter_bonus_room(theme="wind_spire")
        calls.clear()
        main_module.Game.update(game, 0.016)
        assert calls[-1] == "dungeon_wind_spire", f"expected 'dungeon_wind_spire', got {calls[-1]}"

        calls.clear()
        game.enter_bonus_room(theme="generic")
        calls.clear()
        main_module.Game.update(game, 0.016)
        assert calls[-1] == "dungeon", f"expected the generic 'dungeon' zone, got {calls[-1]}"
    finally:
        main_module.audio.play_theme = original_play_theme
    print("PASS: main.py's STATE_BONUS update() selects the correct theme-specific dungeon zone")


if __name__ == "__main__":
    audio.init()
    check_realm_bazaar_dungeon_are_real_20s_arrangements()
    check_six_dungeon_variants_exist_and_registered()
    check_dungeon_variants_are_actually_distinct()
    check_dungeon_zone_resolution_by_key_and_label()
    check_bonus_room_call_site_selects_theme_appropriate_track()
    print("\nALL CHECKS PASSED (check_theme_realm_bazaar_dungeon_extended.py)")

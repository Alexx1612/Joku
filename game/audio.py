"""
Procedural sound effects + a short looping theme.

No audio assets are used anywhere - every sound here is a raw PCM waveform
synthesized at runtime (sine/square tones with a tiny fade envelope to avoid
clicks) and handed to pygame.mixer.Sound as a buffer. This deliberately
avoids a numpy dependency (pygame.sndarray needs one; raw buffer bytes
don't). Every public function is a no-op if the mixer failed to initialize
(no sound card, headless environment, etc.) - audio must never be able to
crash the game.
"""
import math
import random
import struct

import pygame

SAMPLE_RATE = 44100
_enabled = False
_channels = 1
_cache = {}
# live volume multipliers from game/settings.py (set_volumes) - applied on top of
# every sound's own hard-coded relative volume, never replacing it
_music_gain = 1.0
_sfx_gain = 1.0


def set_volumes(master=1.0, music=1.0, sfx=1.0, muted=False):
    """Applies the options-menu volumes live: SFX take the new gain on their next
    play, the looping theme channel is re-leveled immediately."""
    global _music_gain, _sfx_gain
    scale = 0.0 if muted else max(0.0, min(1.0, master))
    _music_gain = scale * max(0.0, min(1.0, music))
    _sfx_gain = scale * max(0.0, min(1.0, sfx))
    if _theme_channel is not None:
        try:
            _theme_channel.set_volume(_music_gain)
        except pygame.error:
            pass


def init():
    """Safe to call multiple times; safe to call with no audio device present."""
    global _enabled, _channels
    if _enabled:
        return
    try:
        pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1)
        info = pygame.mixer.get_init()
        _enabled = info is not None
        if _enabled:
            # SDL is free to ignore the requested channel count (observed: asking
            # for mono, getting stereo back) - always build buffers to match
            # whatever it actually gave us, never what we asked for.
            _channels = info[2]
    except pygame.error:
        _enabled = False


def _samples(freq, duration, volume=0.35, wave="square", freq_end=None, fade=0.015,
             envelope="linear", decay_rate=8.0):
    """
    envelope="linear": symmetric fade in/out - good for sustained tones (shots, theme notes).
    envelope="exp_decay": a ~4ms attack then an exponential decay - a proper percussive
    "impact" shape instead of a flat tone, used for hits/death/boss-spawn.
    """
    n = max(1, int(SAMPLE_RATE * duration))
    fade_n = max(1, int(SAMPLE_RATE * fade))
    attack_n = max(1, int(SAMPLE_RATE * 0.004))
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        f = freq if freq_end is None else freq + (freq_end - freq) * (i / n)
        if wave == "sine":
            v = math.sin(2 * math.pi * f * t)
        elif wave == "square":
            v = 1.0 if math.sin(2 * math.pi * f * t) >= 0 else -1.0
        elif wave == "triangle":
            # A proper triangle wave (not an approximation) - the classic NES/
            # chiptune choice for bass: softer harmonic content than a square,
            # so it sits underneath a buzzy square-wave lead without fighting it.
            v = (2.0 / math.pi) * math.asin(math.sin(2 * math.pi * f * t))
        elif wave == "noise":
            v = random.uniform(-1, 1)
        else:
            v = 0.0
        if envelope == "exp_decay":
            env = (i / attack_n) if i < attack_n else math.exp(-decay_rate * (i - attack_n) / SAMPLE_RATE)
        else:
            env = 1.0
            if i < fade_n:
                env = i / fade_n
            elif i > n - fade_n:
                env = (n - i) / fade_n
        out.append(int(max(-1.0, min(1.0, v * volume * env)) * 32767))
    return out


def _mix(*sample_lists):
    """Layers several sample lists together (e.g. a fundamental + a harmonic,
    or a tone + a noise burst) for a richer timbre than a single flat tone."""
    n = max(len(s) for s in sample_lists)
    out = []
    for i in range(n):
        total = sum(s[i] for s in sample_lists if i < len(s))
        out.append(max(-32767, min(32767, total)))
    return out


def _sound_from(samples):
    if _channels == 2:
        # duplicate each mono sample to L+R so it plays at the correct pitch/speed
        # instead of two consecutive mono samples being read as one stereo frame
        interleaved = [0] * (len(samples) * 2)
        interleaved[0::2] = samples
        interleaved[1::2] = samples
        samples = interleaved
    buf = struct.pack("<%dh" % len(samples), *samples)
    return pygame.mixer.Sound(buffer=buf)


def _cached(key, factory):
    if key not in _cache:
        _cache[key] = factory()
    return _cache[key]


def _play(key, factory):
    if not _enabled:
        return
    if _sfx_gain <= 0:
        return
    try:
        channel = _cached(key, factory).play()
        if channel is not None:
            channel.set_volume(_sfx_gain)
    except pygame.error:
        pass  # a bad buffer or a lost audio device must never crash gameplay


# ------------------------------------------------------------- sfx --
_SHOT_TONE = {
    "wizard": (620, 420), "necromancer": (520, 340), "priest": (700, 520),
    "archer": (900, 700), "rogue": (500, 350), "assassin": (450, 300),
    "warrior": (220, 150), "paladin": (240, 170),
}


def play_shoot(cls_name):
    freq, freq_end = _SHOT_TONE.get(cls_name, (600, 420))
    wave = "square" if cls_name not in ("warrior", "paladin") else "noise"
    _play(f"shoot_{cls_name}", lambda: _sound_from(
        _samples(freq, 0.055, volume=0.22, wave=wave, freq_end=freq_end,
                 envelope="exp_decay", decay_rate=16)))


def play_hit():
    # a low fundamental "thud" plus a brief higher harmonic gives a punchier
    # impact than one flat tone, without needing any real drum samples
    def build():
        fundamental = _samples(160, 0.1, volume=0.3, wave="square", freq_end=70,
                                envelope="exp_decay", decay_rate=16)
        harmonic = _samples(320, 0.06, volume=0.12, wave="square", freq_end=140,
                             envelope="exp_decay", decay_rate=24)
        return _sound_from(_mix(fundamental, harmonic))
    _play("hit", build)


def play_enemy_hit():
    _play("enemy_hit", lambda: _sound_from(
        _samples(950, 0.035, volume=0.17, wave="square", freq_end=1300,
                 envelope="exp_decay", decay_rate=45)))


# ------------------------------------------------------- mob sound families --
# 30 fully bespoke per-kind sounds isn't a manageable scope, so every enemy kind
# is grouped into one of 4 sound families by its flavor/pattern - each family
# gets a pitch/timbre-tinted variant of the existing hit/death shapes above
# (still the same exp_decay percussive envelope, just shifted), not a whole new
# instrument. See entities.ENEMY_KINDS for which kind is which.
_BEAST_KINDS = {"bat", "goblin", "scorpion", "yeti", "troll", "harpy", "panther",
                "thornling", "dune_stalker", "vine_serpent", "husk_wanderer",
                "cliff_strider", "forest_hare", "cave_moth",
                # ambient wildlife - real animals, not machines; without these 4 here
                # they fell through to the "construct" fallback family (a mechanical
                # clang instead of an animal sound) since no explicit bucket covered them
                "songbird", "deer", "desert_lizard", "marsh_heron"}
_UNDEAD_KINDS = {"ghost", "skeleton", "ghoul", "frost_wraith", "frost_sprite",
                 "bog_crawler", "cave_lurker", "glacier_shard", "deep_stalker"}
_ELEMENTAL_KINDS = {"imp", "salamander", "cinder_wisp"}
# everything else (bosses) gets its own distinct, bigger "construct"-family tone


def sound_family(kind):
    if kind in _BEAST_KINDS:
        return "beast"
    if kind in _UNDEAD_KINDS:
        return "undead"
    if kind in _ELEMENTAL_KINDS:
        return "elemental"
    return "construct"


_FAMILY_PITCH = {"beast": 1.15, "undead": 0.75, "elemental": 1.35, "construct": 0.55}
_FAMILY_WAVE = {"beast": "square", "undead": "sine", "elemental": "square", "construct": "noise"}


def play_mob_hit(family="beast"):
    """Family-tinted variant of play_enemy_hit() - same percussive shape, pitch/
    wave shifted per family so a beast's yelp reads differently from a construct's
    clang without needing a whole new instrument per family."""
    mult = _FAMILY_PITCH.get(family, 1.0)
    wave = _FAMILY_WAVE.get(family, "square")
    _play(f"mob_hit_{family}", lambda: _sound_from(
        _samples(950 * mult, 0.035, volume=0.17, wave=wave, freq_end=1300 * mult,
                 envelope="exp_decay", decay_rate=45)))


def play_mob_death(family="beast"):
    """A real death cue for enemies specifically (previously only the PLAYER's
    own death had a distinct sound - see play_death) - family-tinted the same
    way as play_mob_hit, built on the same tone+rumble shape as play_death."""
    mult = _FAMILY_PITCH.get(family, 1.0)
    def build():
        tone = _samples(320 * mult, 0.4, volume=0.24, wave=_FAMILY_WAVE.get(family, "sine"), freq_end=45 * mult,
                         envelope="exp_decay", decay_rate=4.0)
        rumble = _samples(200, 0.3, volume=0.12, wave="noise", envelope="exp_decay", decay_rate=6.5)
        return _sound_from(_mix(tone, rumble))
    _play(f"mob_death_{family}", build)


# a real animal-vocalization shape per family - a low carrier tone with vibrato
# (rapid pitch wobble) mixed with noise, instead of the old flat "blip" tone.
# beast reads as a growl/"grr", undead as a long low moan/hiss, elemental as a
# crackling hiss, construct as a slow mechanical groan - tuned by ear against
# real animal-vocalization references (fast, shallow vibrato + a noise floor is
# what makes a synthesized tone read as "growl" rather than "beep").
_BARK_PROFILE = {
    "beast":     dict(base=150, duration=0.32, vibrato_rate=26, vibrato_depth=0.30, noise_mix=0.35),
    "undead":    dict(base=105, duration=0.55, vibrato_rate=5,  vibrato_depth=0.10, noise_mix=0.55),
    "elemental": dict(base=280, duration=0.24, vibrato_rate=45, vibrato_depth=0.55, noise_mix=0.65),
    "construct": dict(base=90,  duration=0.42, vibrato_rate=3,  vibrato_depth=0.04, noise_mix=0.20),
}


def _bark_wave(family, volume=0.15):
    prof = _BARK_PROFILE.get(family, _BARK_PROFILE["beast"])
    mult = _FAMILY_PITCH.get(family, 1.0)
    base, duration = prof["base"] * mult, prof["duration"]
    n = max(1, int(SAMPLE_RATE * duration))
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        frac = i / n
        f = base * (1 + prof["vibrato_depth"] * math.sin(2 * math.pi * prof["vibrato_rate"] * t))
        tone = 1.0 if math.sin(2 * math.pi * f * t) >= 0 else -1.0
        noise = random.uniform(-1, 1)
        v = tone * (1 - prof["noise_mix"]) + noise * prof["noise_mix"]
        # a real growl shape: quick attack, a held snarl, a quick release - not a blip
        if frac < 0.12:
            env = frac / 0.12
        elif frac > 0.7:
            env = max(0.0, (1 - frac) / 0.3)
        else:
            env = 1.0
        out.append(int(max(-1.0, min(1.0, v * volume * env)) * 32767))
    return out


def play_mob_bark(family="beast"):
    """A mob's idle/aggro vocalization - low-probability ambience with a real
    per-mob cooldown, see Enemy.MIN_REBARK_INTERVAL/update(). Each family gets a
    genuinely distinct animal-like shape (see _BARK_PROFILE), not a shared blip."""
    _play(f"mob_bark_{family}", lambda: _sound_from(_bark_wave(family)))


def play_pickup():
    _play("pickup", lambda: _sound_from(_samples(700, 0.05, volume=0.2, wave="sine", freq_end=1100)))


def play_drop():
    # a soft downward "thud" - the inverse shape of pickup's upward chirp, so the
    # two read as a clear pair (something leaving your hands vs. arriving in them)
    def build():
        thud = _samples(500, 0.09, volume=0.16, wave="sine", freq_end=220, envelope="linear")
        tap = _samples(180, 0.04, volume=0.1, wave="noise", envelope="exp_decay", decay_rate=40)
        return _sound_from(_mix(thud, tap))
    _play("drop", build)


def play_death():
    def build():
        tone = _samples(320, 0.55, volume=0.32, wave="sine", freq_end=45,
                         envelope="exp_decay", decay_rate=3.2)
        rumble = _samples(200, 0.4, volume=0.16, wave="noise",
                           envelope="exp_decay", decay_rate=5.5)
        return _sound_from(_mix(tone, rumble))
    _play("death", build)


def play_levelup():
    def build():
        notes = [440, 554, 659, 880]
        out = []
        for f in notes:
            out += _samples(f, 0.1, volume=0.3, wave="square")
        return _sound_from(out)
    _play("levelup", build)


def play_ability():
    def build():
        rise = _samples(300, 0.18, volume=0.26, wave="sine", freq_end=900, envelope="linear")
        sparkle = _samples(1200, 0.12, volume=0.14, wave="square", freq_end=1800,
                            envelope="exp_decay", decay_rate=18)
        return _sound_from(_mix(rise, sparkle))
    _play("ability", build)


def play_boss_spawn():
    def build():
        low = _samples(85, 0.9, volume=0.38, wave="square", freq_end=45,
                        envelope="exp_decay", decay_rate=2.4)
        rumble = _samples(40, 0.9, volume=0.2, wave="noise",
                           envelope="exp_decay", decay_rate=2.4)
        return _sound_from(_mix(low, rumble))
    _play("boss_spawn", build)


def play_wish(jackpot=False):
    """The Nexus fountain's wish result - an ordinary reroll gets a soft splash-y
    chime; an untiered jackpot gets a bigger, ascending fanfare."""
    def build_normal():
        splash = _samples(500, 0.14, volume=0.18, wave="sine", freq_end=750, envelope="linear")
        droplet = _samples(1400, 0.08, volume=0.1, wave="sine", freq_end=1000, envelope="exp_decay", decay_rate=20)
        return _sound_from(_mix(splash, droplet))

    def build_jackpot():
        notes = [440, 554, 659, 880, 1108]
        out = []
        for f in notes:
            out += _samples(f, 0.09, volume=0.28, wave="square", fade=0.01)
        shimmer = _samples(1800, 0.5, volume=0.1, wave="sine", freq_end=2400, envelope="exp_decay", decay_rate=3)
        base = _render_track(max(len(out), len(shimmer)), [(0.0, out), (0.0, shimmer)])
        return _sound_from(base)
    _play("wish_jackpot" if jackpot else "wish", build_jackpot if jackpot else build_normal)


# ----------------------------------------------------------- theme --
_theme_channel = None


def _render_track(total_n, events):
    """Places each (start_time_sec, samples) event into a shared silent buffer at
    its own offset (additively) rather than concatenating tracks end-to-end - this
    is what lets a bass line, a lead line and a percussion line overlap and
    interlock rhythmically instead of just taking turns one at a time."""
    buf = [0] * total_n
    for start_t, samples in events:
        start_i = int(start_t * SAMPLE_RATE)
        for i, v in enumerate(samples):
            idx = start_i + i
            if idx >= total_n:
                break
            buf[idx] += v
    return [max(-32767, min(32767, v)) for v in buf]


def _power_chord(root_freq, duration, volume=0.13, fade=0.008, detune=1.003):
    """Root + perfect fifth (freq*1.5), the real chiptune trick for a duophonic
    '2-oscillator' hardware faking a guitar power chord (see NES pulse-channel
    arpeggio/duophony technique). A tiny detune on the fifth is a cheap analog
    for the beating/chorus a real distorted guitar's harmonics produce."""
    root = _samples(root_freq, duration, volume=volume, wave="square", fade=fade)
    fifth = _samples(root_freq * 1.5 * detune, duration, volume=volume * 0.85, wave="square", fade=fade)
    return _mix(root, fifth)


def _kick(volume=0.22, decay=10.0):
    return _samples(70, 0.16, volume=volume, wave="noise", envelope="exp_decay", decay_rate=decay)


def _snare(volume=0.16, decay=22.0):
    return _samples(180, 0.09, volume=volume, wave="noise", envelope="exp_decay", decay_rate=decay)


def _hihat(volume=0.06, decay=70.0):
    return _samples(90, 0.03, volume=volume, wave="noise", envelope="exp_decay", decay_rate=decay)


def _semitone_ratio(n):
    return 2.0 ** (n / 12.0)


def _transpose(freqs, ratio):
    return [None if f is None else f * ratio for f in freqs]


def _rock_section(step, lead, chord_roots, offset, lead_vol=0.12, chord_vol=0.1,
                   bass_vol=0.1, bass_div=2.0, drums="full", kick_steps=(0, 4),
                   snare_steps=(2, 6), hihat=True, chord_detune=1.003, fade=0.008):
    """One ~(len(lead)*step) seconds long musical section (a verse/chorus/
    bridge block), pre-offset by `offset` seconds so several of these can be
    concatenated end to end into a single longer arrangement while still
    reusing the exact same per-voice generation as a short theme - this is
    how Realm/Bazaar/Dungeon go from a ~2s repeating riff to a real ~20s
    arrangement with genuine sections (not the same 16 steps just repeated
    more times). `drums`: "full" (kick+snare+optional hihat), "sparse"
    (kick only, no snare/hihat) or "none" (a quiet bridge/breakdown)."""
    steps = len(lead)
    lead_events = [(offset + i * step, _samples(f, step * 0.85, volume=lead_vol, wave="square", fade=fade))
                   for i, f in enumerate(lead) if f is not None]
    chord_events = [(offset + beat * step * 4, _power_chord(f, step * (steps / len(chord_roots) - 0.3),
                                                              volume=chord_vol, detune=chord_detune))
                     for beat, f in enumerate(chord_roots)]
    bass_events = [(offset + beat * step * 4, _samples(f / bass_div, step * (steps / len(chord_roots) - 0.2),
                                                         volume=bass_vol, wave="triangle", fade=0.01))
                   for beat, f in enumerate(chord_roots)]
    perc_events = []
    if drums != "none":
        for s in range(steps):
            if s % 8 in kick_steps:
                perc_events.append((offset + s * step, _kick()))
            if drums == "full" and s % 8 in snare_steps:
                perc_events.append((offset + s * step, _snare()))
            if drums == "full" and hihat:
                perc_events.append((offset + s * step, _hihat()))
    return lead_events, chord_events, bass_events, perc_events


def _bazaar_section(step, lead, chord_roots, bass, offset, lead_vol=0.11, chord_vol=0.1,
                     kick_vol=0.19, snare_vol=0.14, hihat_vol=0.055, drums=True):
    """One chugging rock'n'roll section - two short palm-muted power-chord
    hits per beat (Bazaar's distinctive feel, different from Realm's one-
    chord-per-beat), used to build a real multi-section ~20s arrangement the
    same way `_rock_section` does for Realm."""
    steps = len(lead)
    lead_events = [(offset + i * step, _samples(f, step * 0.78, volume=lead_vol, wave="square", fade=0.006))
                   for i, f in enumerate(lead) if f is not None]
    chord_events = []
    for beat, f in enumerate(chord_roots):
        chord_events.append((offset + beat * step * 4, _power_chord(f, step * 0.7, volume=chord_vol, fade=0.005)))
        chord_events.append((offset + beat * step * 4 + step * 2,
                              _power_chord(f, step * 0.7, volume=chord_vol * 0.8, fade=0.005)))
    bass_events = [(offset + beat * step * 4, _samples(f, step * 3.6, volume=0.1, wave="triangle", fade=0.01))
                   for beat, f in enumerate(bass)]
    perc_events = []
    if drums:
        for s in range(steps):
            if s % 8 in (0, 4):
                perc_events.append((offset + s * step, _kick(volume=kick_vol, decay=15)))
            if s % 4 == 2:
                perc_events.append((offset + s * step, _snare(volume=snare_vol, decay=28)))
            perc_events.append((offset + s * step, _hihat(volume=hihat_vol)))
    return lead_events, chord_events, bass_events, perc_events


def _concat_sections(*section_results):
    lead, chord, bass, perc = [], [], [], []
    for l, c, b, p in section_results:
        lead += l
        chord += c
        bass += b
        perc += p
    return lead, chord, bass, perc


def _render_theme(total_seconds, lead_events, chord_events, bass_events, perc_events):
    total_n = int(SAMPLE_RATE * total_seconds)
    return _sound_from(_mix(_render_track(total_n, lead_events), _render_track(total_n, chord_events),
                             _render_track(total_n, bass_events), _render_track(total_n, perc_events)))


def _build_theme_realm():
    # An original 8-bit rock anthem for the open Realm - a full ~20s
    # arrangement (verse -> chorus -> quiet bridge -> verse -> bigger chorus
    # -> sustained outro chord), not a single short riff on repeat. The
    # chorus is the SAME melodic contour as the verse transposed up a whole
    # step with a reordered chord sequence - real harmonic variation (a
    # standard songwriting "lift"), not literal repetition. Not a cover of
    # any existing song. Square-wave lead, root+fifth power-chord rhythm
    # guitar, triangle bass an octave down, real kick/snare/hi-hat rock beat.
    STEP = 0.125
    VERSE_LEAD = [330, 392, 494, None, 392, 330, 294, 330,
                  247, 294, 330, None, 392, 494, 440, 392]
    VERSE_CHORDS = [165, 220, 247, 165]  # i - VI - VII - i (Em - C - D - Em)
    CHORUS_LEAD = _transpose(VERSE_LEAD, _semitone_ratio(2))
    CHORUS_CHORDS = [220, 247, 165, 220]  # VI - VII - i - VI, a lifted reordering
    BRIDGE_LEAD = [None] * 8
    BRIDGE_CHORDS = [165, 131]  # a quiet i - VI(low) breather, half the harmonic rate

    t = 0.0
    sections = []
    s = _rock_section(STEP, VERSE_LEAD, VERSE_CHORDS, t); sections.append(s); t += len(VERSE_LEAD) * STEP
    s = _rock_section(STEP, VERSE_LEAD, VERSE_CHORDS, t); sections.append(s); t += len(VERSE_LEAD) * STEP
    s = _rock_section(STEP, CHORUS_LEAD, CHORUS_CHORDS, t, lead_vol=0.13, drums="full",
                       snare_steps=(2, 4, 6)); sections.append(s); t += len(CHORUS_LEAD) * STEP
    s = _rock_section(STEP, BRIDGE_LEAD, BRIDGE_CHORDS, t, chord_vol=0.07, bass_vol=0.08,
                       drums="none"); sections.append(s); t += len(BRIDGE_LEAD) * STEP
    s = _rock_section(STEP, VERSE_LEAD, VERSE_CHORDS, t); sections.append(s); t += len(VERSE_LEAD) * STEP
    s = _rock_section(STEP, CHORUS_LEAD, CHORUS_CHORDS, t, lead_vol=0.14, chord_vol=0.11,
                       snare_steps=(2, 4, 6)); sections.append(s); t += len(CHORUS_LEAD) * STEP
    s = _rock_section(STEP, CHORUS_LEAD, CHORUS_CHORDS, t, lead_vol=0.14, chord_vol=0.11,
                       snare_steps=(2, 4, 6)); sections.append(s); t += len(CHORUS_LEAD) * STEP
    s = _rock_section(STEP, CHORUS_LEAD, CHORUS_CHORDS, t, lead_vol=0.14, chord_vol=0.11,
                       snare_steps=(2, 4, 6)); sections.append(s); t += len(CHORUS_LEAD) * STEP
    # sustained final tonic power chord as a real outro tag, not another loop
    outro_chord = _power_chord(165, 5.0, volume=0.13, fade=0.4)
    outro_bass = _samples(165 / 2, 5.0, volume=0.11, wave="triangle", fade=0.4)
    sections.append(([], [(t, outro_chord)], [(t, outro_bass)], []))
    t += 5.0

    return _render_theme(t, *_concat_sections(*sections))


def _phrase_events(phrase_step_offset, step, lead, chord_roots, lead_vol=0.09, lead_wave="square",
                    lead_fade=0.03, lead_dur_mult=1.5, chord_vol=0.06, chord_fade=0.06, chord_dur_mult=4.3,
                    bass_vol=0.08, bass_wave="triangle", bass_fade=0.08, bass_dur_mult=4.4,
                    bass_octave_div=1.0, hihat_steps=(2,), hihat_vol=0.03, hihat_decay=40):
    """Builds one 16-step phrase's worth of (lead, chord, bass, hihat) events at a
    given step offset - the shared building block both the Nexus and Vault themes
    below use to assemble several DISTINCT phrases into one real ~20s arrangement
    instead of just looping one 16-step riff for longer. Each phrase call passes
    its own LEAD/CHORD_ROOTS, so the full track has genuine musical development
    (new melodic/harmonic material every phrase), not a repeated period."""
    t0 = phrase_step_offset * step
    lead_events = [(t0 + i * step, _samples(f, step * lead_dur_mult, volume=lead_vol, wave=lead_wave, fade=lead_fade))
                   for i, f in enumerate(lead) if f is not None]
    chord_events = [(t0 + beat * step * 4, _power_chord(f, step * chord_dur_mult, volume=chord_vol, fade=chord_fade))
                     for beat, f in enumerate(chord_roots)]
    bass_events = [(t0 + beat * step * 4, _samples(f / bass_octave_div, step * bass_dur_mult, volume=bass_vol,
                                                     wave=bass_wave, fade=bass_fade))
                    for beat, f in enumerate(chord_roots)]
    hihat_events = [(t0 + s * step, _hihat(volume=hihat_vol, decay=hihat_decay))
                     for s in range(16) if s % 4 in hihat_steps]
    return lead_events, chord_events, bass_events, hihat_events


def _build_theme_nexus():
    # An original 8-bit SOFT-ROCK BALLAD for the social hub - not a fight, so
    # it stays relaxed rather than driving: long, softly-faded power chords
    # (see _power_chord) standing in for a strummed acoustic-guitar feel, a
    # gentle square-wave lead carrying a warm, spacious original melody, a
    # triangle bass walking underneath the chord roots, and only a very
    # sparse hi-hat pulse (no kick/snare at all) to keep it unhurried.
    #
    # A real ~20-second arrangement (not one 16-step riff just looped longer):
    # five distinct 16-step phrases (A-B-A'-C-D, 80 steps total at STEP=0.25 =
    # 20.0s) - a main theme (A), a lighter ascending answer phrase (B) over a
    # different chord color, a varied return of the main theme (A', changed
    # ending), a sparse hushed bridge (C, mostly rests), and a turnaround (D)
    # that resolves back onto the A/loop-point chord so the 20s loop is
    # seamless. Every phrase shares the same soft-rock instrumentation/mood.
    STEP = 0.25
    PHRASES = [
        # A - the original main theme
        ([523, None, 587, None, 659, None, 587, None,
          494, None, 587, None, 698, None, 659, 587],
         [131, 98, 110, 87]),  # C3-G2-A2-F2 (I-V-vi-IV)
        # B - a lighter, ascending answer phrase over a different chord color
        ([587, None, 659, None, 698, None, 784, None,
          698, None, 659, None, 587, None, 523, None],
         [147, 110, 131, 98]),  # D3-A2-C3-G2 (ii-vi-I-V)
        # A' - the main theme returns, but the last two notes change (real
        # variation, not an identical repeat) and the final chord differs
        ([523, None, 587, None, 659, None, 587, None,
          494, None, 587, None, 659, 587, 523, None],
         [131, 98, 110, 98]),  # C3-G2-A2-G2
        # C - a hushed bridge: mostly rests, just two sparse high accents,
        # chords held and wandering, giving the loop real breathing room
        ([None, None, None, None, 784, None, None, None,
          None, None, None, None, 698, None, None, None],
         [98, 87, 98, 110]),  # G2-F2-G2-A2
        # D - turnaround: resolves onto the tonic so it loops back into A cleanly
        ([659, None, 587, None, 523, None, None, None,
          494, None, 523, None, 587, None, 523, None],
         [110, 98, 131, 131]),  # A2-G2-C3-C3 (settles on the tonic)
    ]
    total_n = int(SAMPLE_RATE * STEP * 16 * len(PHRASES))

    lead_events, chord_events, bass_events, hihat_events = [], [], [], []
    for i, (lead, roots) in enumerate(PHRASES):
        l, c, b, h = _phrase_events(i * 16, STEP, lead, roots)
        lead_events += l
        chord_events += c
        bass_events += b
        hihat_events += h

    return _sound_from(_mix(_render_track(total_n, lead_events), _render_track(total_n, chord_events),
                             _render_track(total_n, bass_events), _render_track(total_n, hihat_events)))


def _build_theme_vault():
    # An original 8-bit HUSHED/SECURE arrangement for the Vault - a "treasure
    # room" mood, distinct from Nexus's warm sociable ballad: slower, sparser,
    # more minor/moody (i-VI-III-VII in D minor), a soft SINE lead (softer
    # than Nexus's square-wave lead, reading as muffled/underground) instead
    # of a buzzy tone, and a literal echo - each lead note gets a quieter,
    # delayed repeat layered in afterward (the cheap, real way to fake a
    # stone-vault reverb with this project's additive _render_track/_mix
    # toolkit, no new synthesis primitive needed). No kick/snare at all; the
    # only percussion is a rare, very soft low "thud" standing in for a
    # distant heavy door, on a long irregular interval - never a steady beat.
    #
    # Four distinct 16-step phrases (main theme, an echo-emphasized variant
    # an octave up, a near-silent "held breath" phrase of chords only, and a
    # return/resolution phrase) - 64 steps at STEP=0.315 = ~20.16s, a real
    # ~20-second arrangement with genuine development, not one riff looped.
    STEP = 0.315
    ECHO_DELAY = STEP * 1.5
    PHRASES = [
        # main theme - sparse, spacious, minor
        ([None, 440, None, None, 587, None, None, 523,
          None, None, 440, None, None, 349, None, None],
         [73, 58, 87, 65]),  # D2-Bb1-F2-C2 (i-VI-III-VII in D minor)
        # echo-emphasized variant, up an octave for contrast
        ([None, 880, None, None, None, 698, None, None,
          None, 1047, None, None, None, 880, None, None],
         [65, 87, 58, 73]),  # C2-F2-Bb1-D2 (same colors, reordered)
        # "held breath" - chords only, no lead at all, the vault falling silent
        ([None] * 16,
         [58, 73, 65, 87]),  # Bb1-D2-C2-F2
        # return/resolution - back to the main theme's register, settling on
        # the tonic so the 20s loop closes cleanly
        ([None, 440, None, None, 523, None, None, None,
          440, None, None, None, 392, None, None, None],
         [73, 87, 73, 73]),  # D2-F2-D2-D2 (settles on the tonic)
    ]
    total_n = int(SAMPLE_RATE * STEP * 16 * len(PHRASES))

    lead_events, chord_events, bass_events, thud_events = [], [], [], []
    for i, (lead, roots) in enumerate(PHRASES):
        t0 = i * 16 * STEP
        for step_i, f in enumerate(lead):
            if f is None:
                continue
            t = t0 + step_i * STEP
            lead_events.append((t, _samples(f, STEP * 1.8, volume=0.08, wave="sine", fade=0.05)))
            # the echo: a quieter, delayed repeat of the exact same note
            lead_events.append((t + ECHO_DELAY, _samples(f, STEP * 1.4, volume=0.03, wave="sine", fade=0.08)))
        chord_events += [(t0 + beat * STEP * 4, _power_chord(f, STEP * 3.9, volume=0.055, fade=0.22, detune=1.005))
                          for beat, f in enumerate(roots)]
        bass_events += [(t0 + beat * STEP * 4, _samples(f, STEP * 4.0, volume=0.09, wave="triangle", fade=0.2))
                         for beat, f in enumerate(roots)]
    # one distant, very soft "door thud" near the start of each phrase - never
    # a steady beat, just an occasional reminder of the vault's own weight
    thud_events = [(i * 16 * STEP, _kick(volume=0.1, decay=6)) for i in range(len(PHRASES))]

    return _sound_from(_mix(_render_track(total_n, lead_events), _render_track(total_n, chord_events),
                             _render_track(total_n, bass_events), _render_track(total_n, thud_events)))


def _build_theme_bazaar():
    # An original 8-bit ROCK'N'ROLL arrangement for the marketplace - a full
    # ~20s arrangement (verse -> chorus lift -> quiet market-hum bridge ->
    # verse -> chorus -> big finish), not one short riff on repeat. Not a
    # cover of any existing song. Chugging eighth-note power-chord rhythm
    # guitar, a bouncy walking triangle bass, a playful square-wave lead, the
    # busiest/fastest drum pattern of the zone themes.
    STEP = 0.095
    VERSE_LEAD = [523, 587, 659, 523, 440, 523, 587, 659,
                  698, 659, 587, 523, 494, 523, 587, 440]
    VERSE_CHORDS = [196, 262, 294, 196]  # I - IV - V - I (G-C-D-G)
    VERSE_BASS = [98, 110, 123, 131]
    CHORUS_LEAD = _transpose(VERSE_LEAD, _semitone_ratio(2))
    CHORUS_CHORDS = [262, 294, 196, 262]  # IV - V - I - IV, reordered lift
    CHORUS_BASS = [110, 123, 98, 110]
    BRIDGE_LEAD = [None, 523, None, None, 587, None, None, None]
    BRIDGE_CHORDS = [196, 165]  # a quiet half-tempo market-hum breather
    BRIDGE_BASS = [98, 82]

    t = 0.0
    sections = []
    s = _bazaar_section(STEP, VERSE_LEAD, VERSE_CHORDS, VERSE_BASS, t); sections.append(s)
    t += len(VERSE_LEAD) * STEP
    s = _bazaar_section(STEP, CHORUS_LEAD, CHORUS_CHORDS, CHORUS_BASS, t, lead_vol=0.12,
                         chord_vol=0.11); sections.append(s); t += len(CHORUS_LEAD) * STEP
    s = _bazaar_section(STEP, BRIDGE_LEAD, BRIDGE_CHORDS, BRIDGE_BASS, t, lead_vol=0.07,
                         chord_vol=0.05, drums=False); sections.append(s); t += len(BRIDGE_LEAD) * STEP
    s = _bazaar_section(STEP, VERSE_LEAD, VERSE_CHORDS, VERSE_BASS, t); sections.append(s)
    t += len(VERSE_LEAD) * STEP
    s = _bazaar_section(STEP, CHORUS_LEAD, CHORUS_CHORDS, CHORUS_BASS, t, lead_vol=0.13,
                         chord_vol=0.12, kick_vol=0.21, snare_vol=0.16)
    sections.append(s); t += len(CHORUS_LEAD) * STEP
    s = _bazaar_section(STEP, CHORUS_LEAD, CHORUS_CHORDS, CHORUS_BASS, t, lead_vol=0.13,
                         chord_vol=0.12, kick_vol=0.21, snare_vol=0.16)
    sections.append(s); t += len(CHORUS_LEAD) * STEP
    s = _bazaar_section(STEP, CHORUS_LEAD, CHORUS_CHORDS, CHORUS_BASS, t, lead_vol=0.13,
                         chord_vol=0.12, kick_vol=0.21, snare_vol=0.16)
    sections.append(s); t += len(CHORUS_LEAD) * STEP
    s = _bazaar_section(STEP, VERSE_LEAD, VERSE_CHORDS, VERSE_BASS, t); sections.append(s)
    t += len(VERSE_LEAD) * STEP
    s = _bazaar_section(STEP, CHORUS_LEAD, CHORUS_CHORDS, CHORUS_BASS, t, lead_vol=0.13,
                         chord_vol=0.12, kick_vol=0.21, snare_vol=0.16)
    sections.append(s); t += len(CHORUS_LEAD) * STEP
    outro_chord = _power_chord(196, 5.56, volume=0.13, fade=0.3)
    outro_bass = _samples(98, 5.56, volume=0.1, wave="triangle", fade=0.3)
    sections.append(([], [(t, outro_chord)], [(t, outro_bass)], []))
    t += 5.56

    return _render_theme(t, *_concat_sections(*sections))


def _doom_section(step, lead, chord_roots, offset, chord_vol=0.1, bass_vol=0.11,
                   detune=1.008, kick_steps=(0, 7, 11), snare_steps=(4, 13), lead_vol=0.1):
    """One heavy/doom-rock section - long de-tuned power chords, sparse lead
    stabs, a slow irregular kick/snare pulse with no hi-hats at all. Shared
    by the generic Dungeon track and every per-theme dungeon variant below,
    so each variant only needs to supply its own root notes/mood, not
    reinvent the heavy-rock arrangement shape."""
    steps = len(lead)
    lead_events = [(offset + i * step, _samples(f, step * 1.7, volume=lead_vol, wave="square", fade=0.02))
                   for i, f in enumerate(lead) if f is not None]
    chord_dur = step * (steps / len(chord_roots))
    chord_events = [(offset + beat * step * 4, _power_chord(f, chord_dur, volume=chord_vol,
                                                              fade=0.15, detune=detune))
                     for beat, f in enumerate(chord_roots)]
    bass_events = [(offset + beat * step * 4, _samples(f, chord_dur, volume=bass_vol, wave="triangle", fade=0.15))
                   for beat, f in enumerate(chord_roots)]
    perc_events = [(offset + s * step, _kick(volume=0.2, decay=8)) for s in kick_steps]
    perc_events += [(offset + s * step, _snare(volume=0.14, decay=14)) for s in snare_steps]
    return lead_events, chord_events, bass_events, perc_events


def _build_theme_dungeon():
    # An original 8-bit HEAVY/DOOM-ROCK arrangement for a generic bonus-room
    # crawl - a full ~20s arrangement (two long verse-like sections, a
    # near-silent dread bridge, then a heavier reprise), not one short riff
    # on repeat. Not a fanfare, not a cover of any existing song. Low
    # de-tuned power chords held long for a sludgy "wall of sound", a low
    # triangle bass locked to the same dissonant roots, sparse unsettling
    # lead stabs breaking long silences, a slow irregular kick/snare pulse
    # with NO hi-hats at all - the heaviest/most spacious of the zone themes.
    STEP = 0.18
    LEAD_A = [None, None, 207, None, None, 196, None, None,
              None, None, 220, 246, None, None, 185, None]
    CHORDS_A = [55, 55, 62, 58]  # a low, deliberately dissonant non-diatonic crawl
    LEAD_B = _transpose(LEAD_A, _semitone_ratio(-2))  # a step lower - heavier, not "lifted"
    CHORDS_B = [58, 62, 55, 55]
    BRIDGE_LEAD = [None] * 8
    BRIDGE_CHORDS = [55]

    t = 0.0
    sections = []
    s = _doom_section(STEP, LEAD_A, CHORDS_A, t); sections.append(s); t += len(LEAD_A) * STEP
    s = _doom_section(STEP, LEAD_B, CHORDS_B, t, chord_vol=0.11); sections.append(s); t += len(LEAD_B) * STEP
    s = _doom_section(STEP, BRIDGE_LEAD, BRIDGE_CHORDS, t, chord_vol=0.06, bass_vol=0.07,
                       kick_steps=(), snare_steps=()); sections.append(s); t += len(BRIDGE_LEAD) * STEP
    s = _doom_section(STEP, LEAD_A, CHORDS_A, t, chord_vol=0.12, bass_vol=0.12,
                       kick_steps=(0, 5, 9, 13), snare_steps=(4, 11))
    sections.append(s); t += len(LEAD_A) * STEP
    s = _doom_section(STEP, LEAD_B, CHORDS_B, t, chord_vol=0.12, bass_vol=0.12,
                       kick_steps=(0, 5, 9, 13), snare_steps=(4, 11))
    sections.append(s); t += len(LEAD_B) * STEP
    outro_chord = _power_chord(55, 4.6, volume=0.13, fade=0.5, detune=1.01)
    outro_bass = _samples(55, 4.6, volume=0.12, wave="triangle", fade=0.5)
    sections.append(([], [(t, outro_chord)], [(t, outro_bass)], []))
    t += 4.6

    return _render_theme(t, *_concat_sections(*sections))


def _build_theme_dungeon_variant(chord_roots, lead, mood_lead_vol=0.1, detune=1.008):
    """Shorter (~12-14s) per-dungeon-theme variant built on the exact same
    `_doom_section` shape as the generic Dungeon track, just with its own
    root notes/mood - real distinct music per dungeon theme instead of one
    shared track for all 7, without re-deriving the whole arrangement shape
    each time."""
    STEP = 0.18
    lead_b = _transpose(lead, _semitone_ratio(-1))
    chords_b = list(reversed(chord_roots))
    t = 0.0
    sections = []
    s = _doom_section(STEP, lead, chord_roots, t, lead_vol=mood_lead_vol, detune=detune)
    sections.append(s); t += len(lead) * STEP
    s = _doom_section(STEP, lead_b, chords_b, t, lead_vol=mood_lead_vol, chord_vol=0.11, detune=detune)
    sections.append(s); t += len(lead_b) * STEP
    s = _doom_section(STEP, lead, chord_roots, t, lead_vol=mood_lead_vol, chord_vol=0.12,
                       bass_vol=0.12, kick_steps=(0, 5, 9, 13), snare_steps=(4, 11), detune=detune)
    sections.append(s); t += len(lead) * STEP
    outro_chord = _power_chord(chord_roots[0], 3.4, volume=0.13, fade=0.4, detune=detune)
    outro_bass = _samples(chord_roots[0], 3.4, volume=0.12, wave="triangle", fade=0.4)
    sections.append(([], [(t, outro_chord)], [(t, outro_bass)], []))
    t += 3.4
    return _render_theme(t, *_concat_sections(*sections))


def _build_theme_dungeon_cave():
    # Cave Warren - echoey and cavernous: a wide, slow, low-register crawl.
    return _build_theme_dungeon_variant(
        chord_roots=[49, 49, 55, 52], lead=[None, None, 185, None, None, None, 174, None,
                                             None, None, None, 196, None, None, 165, None])


def _build_theme_dungeon_frozen_crypt():
    # Frozen Crypt - icy and brittle: higher, thinner-sounding stabs over
    # the same heavy doom-rock bed, a slight extra detune for a "creaking
    # ice" edge.
    return _build_theme_dungeon_variant(
        chord_roots=[62, 62, 69, 65], lead=[None, 294, None, None, None, 277, None, None,
                                             311, None, None, None, 262, None, None, None],
        mood_lead_vol=0.11, detune=1.012)


def _build_theme_dungeon_jungle_ruins():
    # Jungle Ruins - a more percussive/tribal feel: extra kick hits, a
    # slightly higher, more rhythmic lead than the other variants.
    return _build_theme_dungeon_variant(
        chord_roots=[59, 59, 55, 62], lead=[233, None, None, 220, None, None, 247, None,
                                             None, 233, None, None, 262, None, None, 220])


def _build_theme_dungeon_ember_den():
    # Ember Den - the most aggressive/fastest-feeling variant: a higher
    # detune for real grit and a busier lead line breaking up the silence
    # less than the others.
    return _build_theme_dungeon_variant(
        chord_roots=[62, 65, 62, 58], lead=[277, None, 294, None, 311, None, 262, None,
                                             277, None, 294, 330, None, 277, None, 262],
        mood_lead_vol=0.12, detune=1.015)


def _build_theme_dungeon_sunken_grotto():
    # Sunken Grotto - watery and murky: a lower, slower-feeling register
    # with a softer lead than the others (a muffled, underwater quality).
    return _build_theme_dungeon_variant(
        chord_roots=[52, 52, 58, 55], lead=[None, None, None, 196, None, None, 174, None,
                                             None, None, 185, None, None, None, None, None],
        mood_lead_vol=0.08)


def _build_theme_dungeon_wind_spire():
    # Wind Spire - airier and higher-pitched than the other variants (still
    # heavy underneath), a faster-moving lead line evoking wind at height.
    return _build_theme_dungeon_variant(
        chord_roots=[65, 65, 72, 69], lead=[330, 349, None, 311, None, 330, 349, None,
                                             392, None, 349, 330, None, 311, None, 330],
        mood_lead_vol=0.11)


_DUNGEON_VARIANT_BUILDERS = {
    "cave": _build_theme_dungeon_cave,
    "frozen_crypt": _build_theme_dungeon_frozen_crypt,
    "jungle_ruins": _build_theme_dungeon_jungle_ruins,
    "ember_den": _build_theme_dungeon_ember_den,
    "sunken_grotto": _build_theme_dungeon_sunken_grotto,
    "wind_spire": _build_theme_dungeon_wind_spire,
}
# Human-readable dungeon-theme labels (game/realm_sim.py's DUNGEON_THEMES
# dict) mapped back to the theme KEY, so a co-op client - which only ever
# receives the label string over the network (see coop_client.py's
# self.theme_name) - can still resolve the correct per-theme track without
# needing a new network field.
_DUNGEON_LABEL_TO_KEY = {
    "Cave Warren": "cave", "Frozen Crypt": "frozen_crypt", "Jungle Ruins": "jungle_ruins",
    "Ember Den": "ember_den", "Sunken Grotto": "sunken_grotto", "Wind Spire": "wind_spire",
    "Forgotten Vault": "generic",
}


def dungeon_zone_for_key(theme_key):
    """theme_key: a game.realm_sim.DUNGEON_THEMES key (e.g. "cave"), as
    already tracked server-/single-player-side on RealmSim.theme_key.
    Returns the play_theme() zone string for that dungeon's own distinct
    track, falling back to the generic "dungeon" zone for "generic" or any
    unrecognized key."""
    if theme_key in _DUNGEON_VARIANT_BUILDERS:
        return f"dungeon_{theme_key}"
    return "dungeon"


def dungeon_zone_for_label(label):
    """Same as dungeon_zone_for_key, but resolved from the human-readable
    label a co-op client already receives over the network (self.theme_name)
    instead of the raw theme key, which isn't relayed today."""
    return dungeon_zone_for_key(_DUNGEON_LABEL_TO_KEY.get(label))


_THEME_BUILDERS = {
    "nexus": _build_theme_nexus,
    "bazaar": _build_theme_bazaar,
    "realm": _build_theme_realm,
    "dungeon": _build_theme_dungeon,
    "vault": _build_theme_vault,
}
for _key, _builder in _DUNGEON_VARIANT_BUILDERS.items():
    _THEME_BUILDERS[f"dungeon_{_key}"] = _builder
_current_theme_zone = None


def play_theme(zone="nexus"):
    """zone: 'nexus' | 'bazaar' | 'realm' | 'dungeon' - each has its own distinct
    track (see _THEME_BUILDERS). Safe to call every frame: it only actually
    stops/restarts the music when the zone has changed since the last call."""
    global _theme_channel, _current_theme_zone
    if not _enabled or zone not in _THEME_BUILDERS:
        return
    if zone == _current_theme_zone and _theme_channel is not None:
        return
    _current_theme_zone = zone
    try:
        snd = _cached(f"theme_{zone}", _THEME_BUILDERS[zone])
        if _theme_channel is not None:
            _theme_channel.stop()
        _theme_channel = snd.play(loops=-1)
        if _theme_channel is not None:
            _theme_channel.set_volume(_music_gain)
    except pygame.error:
        pass


def stop_theme():
    global _theme_channel, _current_theme_zone
    if _theme_channel is not None:
        try:
            _theme_channel.stop()
        except pygame.error:
            pass
        _theme_channel = None
    _current_theme_zone = None

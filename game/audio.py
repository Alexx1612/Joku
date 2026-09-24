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
    try:
        _cached(key, factory).play()
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


def _build_theme_realm():
    # An original 8-bit rock anthem for the open Realm - not a cover of any
    # existing song, this project's own chiptune arrangement of "rock band"
    # roles: a square-wave lead riff (fresh original hook, E natural-minor),
    # a _power_chord rhythm-guitar layer (one chord per beat, i-VI-VII-i),
    # a triangle bass doubling the chord roots an octave down, and a real
    # rock beat (kick on 1 & 3, snare on 2 & 4, eighth-note hi-hats
    # throughout) - the biggest/most driving of the four zone themes.
    STEP = 0.125
    STEPS = 16
    total_n = int(SAMPLE_RATE * STEP * STEPS)

    LEAD = [330, 392, 494, None, 392, 330, 294, 330,
            247, 294, 330, None, 392, 494, 440, 392]
    lead_events = [(i * STEP, _samples(f, STEP * 0.85, volume=0.12, wave="square", fade=0.008))
                   for i, f in enumerate(LEAD) if f is not None]

    CHORD_ROOTS = [165, 220, 247, 165]  # i - VI - VII - i (Em - C - D - Em)
    chord_events = [(beat * STEP * 4, _power_chord(f, STEP * 3.7, volume=0.1))
                     for beat, f in enumerate(CHORD_ROOTS)]

    bass_events = [(beat * STEP * 4, _samples(f / 2, STEP * 3.8, volume=0.1, wave="triangle", fade=0.01))
                   for beat, f in enumerate(CHORD_ROOTS)]

    perc_events = []
    for step in range(STEPS):
        if step % 8 in (0, 4):
            perc_events.append((step * STEP, _kick()))
        if step % 8 in (2, 6):
            perc_events.append((step * STEP, _snare()))
        perc_events.append((step * STEP, _hihat()))

    return _sound_from(_mix(_render_track(total_n, lead_events), _render_track(total_n, chord_events),
                             _render_track(total_n, bass_events), _render_track(total_n, perc_events)))


def _build_theme_nexus():
    # An original 8-bit SOFT-ROCK BALLAD for the social hub - not a fight, so
    # it stays relaxed rather than driving: long, softly-faded power chords
    # (see _power_chord) standing in for a strummed acoustic-guitar feel, a
    # gentle square-wave lead carrying a warm, spacious original melody, a
    # triangle bass walking underneath the chord roots, and only a very
    # sparse hi-hat pulse (no kick/snare at all) to keep it unhurried.
    STEP = 0.22
    STEPS = 16
    total_n = int(SAMPLE_RATE * STEP * STEPS)

    LEAD = [523, None, 587, None, 659, None, 587, None,
            494, None, 587, None, 698, None, 659, 587]
    lead_events = [(i * STEP, _samples(f, STEP * 1.5, volume=0.09, wave="square", fade=0.03))
                   for i, f in enumerate(LEAD) if f is not None]

    CHORD_ROOTS = [131, 98, 110, 87]  # C3-G2-A2-F2, a slow original I-V-vi-IV-style wander
    chord_events = [(beat * STEP * 4, _power_chord(f, STEP * 4.3, volume=0.06, fade=0.06))
                     for beat, f in enumerate(CHORD_ROOTS)]

    bass_events = [(beat * STEP * 4, _samples(f, STEP * 4.4, volume=0.08, wave="triangle", fade=0.08))
                   for beat, f in enumerate(CHORD_ROOTS)]

    perc_events = [(step * STEP, _hihat(volume=0.03, decay=40))
                   for step in range(STEPS) if step % 4 == 2]

    return _sound_from(_mix(_render_track(total_n, lead_events), _render_track(total_n, chord_events),
                             _render_track(total_n, bass_events), _render_track(total_n, perc_events)))


def _build_theme_bazaar():
    # An original 8-bit ROCK'N'ROLL arrangement for the marketplace - not a
    # cover of any existing song, this project's own chiptune take on a
    # "rock band" playing an upbeat set: a chugging eighth-note power-chord
    # rhythm guitar (see _power_chord - two short punchy hits per beat for a
    # palm-muted feel), a bouncy walking triangle bass, a playful original
    # square-wave lead melody on top, and the busiest/fastest drum pattern of
    # the four themes (kick+snare backbeat plus a hi-hat on every step).
    STEP = 0.095
    STEPS = 16
    total_n = int(SAMPLE_RATE * STEP * STEPS)

    # An original bouncy G-major melody (not derived from any real song) -
    # a rising-then-falling run with a syncopated skip on beat 3.
    LEAD = [523, 587, 659, 523, 440, 523, 587, 659,
            698, 659, 587, 523, 494, 523, 587, 440]
    lead_events = [(i * STEP, _samples(f, STEP * 0.78, volume=0.11, wave="square", fade=0.006))
                   for i, f in enumerate(LEAD)]

    # A classic I-IV-V-I chord skeleton (G-C-D-G) - four generic chord roots
    # every rock band uses, carrying wholly original melodic/rhythmic content
    # on top, chugged twice per beat for the "rhythm guitar" palm-mute feel.
    CHORD_ROOTS = [196, 262, 294, 196]
    chord_events = []
    for beat, f in enumerate(CHORD_ROOTS):
        chord_events.append((beat * STEP * 4, _power_chord(f, STEP * 0.7, volume=0.1, fade=0.005)))
        chord_events.append((beat * STEP * 4 + STEP * 2, _power_chord(f, STEP * 0.7, volume=0.08, fade=0.005)))

    # A walking bass line climbing under the chord roots (G2-A2-B2-C3).
    BASS = [98, 110, 123, 131]
    bass_events = [(beat * STEP * 4, _samples(f, STEP * 3.6, volume=0.1, wave="triangle", fade=0.01))
                   for beat, f in enumerate(BASS)]

    perc_events = []
    for step in range(STEPS):
        if step % 8 in (0, 4):
            perc_events.append((step * STEP, _kick(volume=0.19, decay=15)))
        if step % 4 == 2:
            perc_events.append((step * STEP, _snare(volume=0.14, decay=28)))
        perc_events.append((step * STEP, _hihat(volume=0.055)))

    return _sound_from(_mix(_render_track(total_n, lead_events), _render_track(total_n, chord_events),
                             _render_track(total_n, bass_events), _render_track(total_n, perc_events)))


def _build_theme_dungeon():
    # An original 8-bit HEAVY/DOOM-ROCK arrangement for a bonus-room crawl -
    # not a fanfare, and not a cover of any existing song. Slow tempo, low
    # de-tuned _power_chord()s (root+fifth, extra detune for grit) held long
    # for a sludgy "wall of sound" instead of a clean sine drone, a low
    # triangle bass locked to the same dissonant chord roots, sparse
    # unsettling square-wave lead stabs breaking long silences, and a slow,
    # heavy, irregular kick/snare pulse with NO hi-hats at all - the heaviest
    # and most spacious of the four themes.
    STEP = 0.18
    STEPS = 16
    total_n = int(SAMPLE_RATE * STEP * STEPS)

    LEAD = [None, None, 207, None, None, 196, None, None,
            None, None, 220, 246, None, None, 185, None]
    lead_events = [(i * STEP, _samples(f, STEP * 1.7, volume=0.1, wave="square", fade=0.02))
                   for i, f in enumerate(LEAD) if f is not None]

    CHORD_ROOTS = [55, 55, 62, 58]  # a low, deliberately dissonant non-diatonic crawl
    chord_events = [(beat * STEP * 4, _power_chord(f, STEP * 4.0, volume=0.1, fade=0.15, detune=1.008))
                     for beat, f in enumerate(CHORD_ROOTS)]

    bass_events = [(beat * STEP * 4, _samples(f, STEP * 4.0, volume=0.11, wave="triangle", fade=0.15))
                   for beat, f in enumerate(CHORD_ROOTS)]

    KICK_STEPS = [0, 7, 11]
    SNARE_STEPS = [4, 13]
    perc_events = [(step * STEP, _kick(volume=0.2, decay=8)) for step in KICK_STEPS]
    perc_events += [(step * STEP, _snare(volume=0.14, decay=14)) for step in SNARE_STEPS]

    return _sound_from(_mix(_render_track(total_n, lead_events), _render_track(total_n, chord_events),
                             _render_track(total_n, bass_events), _render_track(total_n, perc_events)))


_THEME_BUILDERS = {
    "nexus": _build_theme_nexus,
    "bazaar": _build_theme_bazaar,
    "realm": _build_theme_realm,
    "dungeon": _build_theme_dungeon,
}
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

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
import io
import math
import os
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


# the per-zone ~60s original rock tracks themselves live in game/music.py (fast
# wavetable/audioop renderer, disk cache, background worker); this module only
# plays them - crossfading between two reserved mixer channels on zone changes.
from game import music as _music  # noqa: E402

dungeon_zone_for_key = _music.dungeon_zone_for_key
dungeon_zone_for_label = _music.dungeon_zone_for_label
realm_zone = _music.realm_zone
MUSIC_FADE_MS = 1500
_MUSIC_DISABLED = os.environ.get("RR_NO_MUSIC", "") not in ("", "0")
_library = None
_music_channels = None      # two reserved channels, alternated for crossfades
_music_sounds = {}
_current_theme_zone = None  # the zone play_theme() was last asked for
_playing_zone = None        # the zone actually audible right now (lags while rendering)


def _lib():
    global _library
    if _library is None:
        _library = _music.Library()
    return _library


def _channels_pair():
    global _music_channels
    if _music_channels is None:
        pygame.mixer.set_reserved(2)
        _music_channels = [pygame.mixer.Channel(0), pygame.mixer.Channel(1)]
    return _music_channels


def play_theme(zone="nexus"):
    """Asks for `zone`'s track (game/music.TRACKS). Safe to call every frame: it
    only acts when the zone changes. If the track isn't rendered yet it is queued
    on the background worker and the previous music keeps playing until
    update_music() finds it ready - the game loop never waits on synthesis."""
    global _current_theme_zone
    if not _enabled or _MUSIC_DISABLED or zone not in _music.TRACKS:
        return
    if zone == _current_theme_zone:
        return
    _current_theme_zone = zone
    update_music()


def update_music():
    """Call once per frame: starts the requested track (crossfading from the old
    one) as soon as the background worker has it ready."""
    global _theme_channel, _playing_zone
    zone = _current_theme_zone
    if not _enabled or _MUSIC_DISABLED or zone is None or zone == _playing_zone:
        return
    data = _lib().request(zone)
    if data is None:
        return
    try:
        snd = _music_sounds.get(zone)
        if snd is None:
            snd = pygame.mixer.Sound(file=io.BytesIO(data))
            _music_sounds[zone] = snd
        a, b = _channels_pair()
        new_ch = b if _theme_channel is a else a
        if _theme_channel is not None:
            _theme_channel.fadeout(MUSIC_FADE_MS)
        new_ch.set_volume(_music_gain)
        new_ch.play(snd, loops=-1, fade_ms=MUSIC_FADE_MS if _playing_zone is not None else 400)
        _theme_channel = new_ch
        _playing_zone = zone
    except pygame.error:
        _playing_zone = zone  # a lost audio device must never crash (or retry every frame)


def stop_theme():
    global _theme_channel, _current_theme_zone, _playing_zone
    if _theme_channel is not None:
        try:
            _theme_channel.stop()
        except pygame.error:
            pass
        _theme_channel = None
    _current_theme_zone = None
    _playing_zone = None

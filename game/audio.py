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
import time

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


# rate limiting: dense fights can fire dozens of identical sounds in one frame,
# which just clips into noise - a per-key minimum interval plus a small global
# budget per window keeps the mix readable
SFX_MIN_INTERVAL = 0.045       # seconds between two plays of the SAME sound
SFX_WINDOW = 0.12              # ...and at most SFX_WINDOW_BUDGET sounds per window overall
SFX_WINDOW_BUDGET = 10
_last_played = {}
_window_start = 0.0
_window_count = 0


def _rate_ok(key, now=None):
    """True if `key` may play right now (and records the play)."""
    global _window_start, _window_count
    now = time.monotonic() if now is None else now
    if now - _last_played.get(key, -1.0) < SFX_MIN_INTERVAL:
        return False
    if now - _window_start > SFX_WINDOW:
        _window_start, _window_count = now, 0
    if _window_count >= SFX_WINDOW_BUDGET:
        return False
    _window_count += 1
    _last_played[key] = now
    return True


def _play(key, factory):
    if not _enabled:
        return
    if _sfx_gain <= 0:
        return
    if not _rate_ok(key):
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


# each class's weapon TYPE gets its own shot sound (all tiers of that weapon share it)
WEAPON_TYPE = {"wizard": "staff", "necromancer": "scepter", "priest": "wand", "archer": "bow",
               "rogue": "dagger", "assassin": "katar", "warrior": "sword", "paladin": "mace"}


def _weapon_sound(wtype):
    """Original procedural shot sounds, one timbre per weapon type."""
    if wtype == "staff":    # arcane zap + a small sparkle on top
        return _mix(_samples(660, 0.07, 0.2, "square", 380, envelope="exp_decay", decay_rate=18),
                    _samples(1500, 0.05, 0.08, "sine", 2100, envelope="exp_decay", decay_rate=30))
    if wtype == "scepter":  # low dark whoosh
        return _mix(_samples(300, 0.09, 0.2, "triangle", 170, envelope="exp_decay", decay_rate=14),
                    _samples(0, 0.08, 0.07, "noise", envelope="exp_decay", decay_rate=20))
    if wtype == "wand":     # bright chime
        return _mix(_samples(1040, 0.08, 0.16, "sine", 1180, envelope="exp_decay", decay_rate=16),
                    _samples(1560, 0.07, 0.08, "sine", 1760, envelope="exp_decay", decay_rate=22))
    if wtype == "bow":      # string twang: a plucked drop + a soft air whoosh
        return _mix(_samples(420, 0.09, 0.2, "triangle", 210, envelope="exp_decay", decay_rate=22),
                    _samples(0, 0.06, 0.06, "noise", envelope="exp_decay", decay_rate=35))
    if wtype == "dagger":   # quick high swish
        return _mix(_samples(0, 0.045, 0.14, "noise", envelope="exp_decay", decay_rate=55),
                    _samples(1800, 0.03, 0.06, "square", 2400, envelope="exp_decay", decay_rate=60))
    if wtype == "katar":    # double swish
        one = _mix(_samples(0, 0.035, 0.13, "noise", envelope="exp_decay", decay_rate=60),
                   _samples(1400, 0.025, 0.05, "square", 1900, envelope="exp_decay", decay_rate=70))
        gap = [0] * int(SAMPLE_RATE * 0.03)
        return one + gap + [int(v * 0.8) for v in one]
    if wtype == "sword":    # heavier swoosh + a short metallic ring
        return _mix(_samples(0, 0.07, 0.16, "noise", envelope="exp_decay", decay_rate=30),
                    _samples(880, 0.09, 0.06, "sine", 860, envelope="exp_decay", decay_rate=18))
    if wtype == "mace":     # low whump
        return _mix(_samples(170, 0.1, 0.24, "square", 90, envelope="exp_decay", decay_rate=20),
                    _samples(0, 0.06, 0.1, "noise", envelope="exp_decay", decay_rate=35))
    return _samples(600, 0.055, 0.22, "square", 420, envelope="exp_decay", decay_rate=16)


def play_shoot(cls_name):
    wtype = WEAPON_TYPE.get(cls_name, "staff")
    _play(f"shoot_{wtype}", lambda: _sound_from(_weapon_sound(wtype)))


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


# per ability STYLE (game/vfx.py ABILITY_STYLES): (base, end, dur, wave, noise_amt, sparkle, decay)
ABILITY_SOUND = {
    "shatter": (900, 300, 0.22, "square", 0.10, 2200, 10),     # glassy crack
    "ruin": (220, 60, 0.35, "square", 0.18, 0, 6),             # dark implosion boom
    "void": (500, 1400, 0.25, "sine", 0.06, 1800, 9),          # rising warp
    "blight": (260, 200, 0.3, "triangle", 0.16, 0, 7),         # wet poison hiss
    "corruption": (180, 120, 0.4, "triangle", 0.2, 0, 5),      # spreading rot rumble
    "reaper": (700, 180, 0.3, "sine", 0.12, 0, 8),             # scythe sweep
    "thunder": (120, 60, 0.35, "square", 0.3, 0, 7),           # thunderclap
    "storms": (150, 50, 0.45, "square", 0.35, 0, 5),           # rolling thunder
    "gale": (400, 900, 0.4, "sine", 0.25, 0, 5),               # howling wind
    "mending": (520, 780, 0.3, "sine", 0.0, 1560, 7),          # soft holy chord
    "restoration": (440, 880, 0.35, "sine", 0.0, 1320, 6),
    "rebirth": (330, 990, 0.45, "sine", 0.0, 1980, 5),
    "aegis": (600, 600, 0.3, "triangle", 0.0, 1200, 7),        # shield hum
    "ward": (500, 520, 0.4, "triangle", 0.04, 1500, 5),
    "horn": (196, 262, 0.4, "square", 0.02, 0, 4),             # war horn
    "smoke": (0, 0, 0.3, "noise", 0.3, 0, 9),                  # smoke puff
    "shadow": (300, 150, 0.3, "sine", 0.1, 0, 8),              # shadow whoosh
}


def _ability_sound(style):
    base, end, dur, wave, noise, sparkle, decay = ABILITY_SOUND.get(style, (300, 900, 0.18, "sine", 0.0, 1200, 8))
    layers = []
    if wave != "noise":
        layers.append(_samples(base, dur, 0.24, wave, end, envelope="exp_decay", decay_rate=decay))
    if noise > 0:
        layers.append(_samples(0, dur * 0.8, noise, "noise", envelope="exp_decay", decay_rate=decay * 1.3))
    if sparkle:
        layers.append(_samples(sparkle, dur * 0.6, 0.08, "sine", sparkle * 1.25, envelope="exp_decay",
                               decay_rate=decay * 1.5))
    return _mix(*layers)


def play_ability(style=None):
    key = style if style in ABILITY_SOUND else "generic"
    _play(f"ability_{key}", lambda: _sound_from(_ability_sound(key)))


# enemy attack kinds (game/enemy_attacks.py move "sfx" keys + wind-ups / phases)
ENEMY_ATTACK_SOUND = {
    "shot": (520, 380, 0.05, "square", 0.0, 22),
    "shot_small": (600, 470, 0.035, "square", 0.0, 28),   # trash basic shots - quieter, see below
    "shotgun": (300, 180, 0.09, "square", 0.25, 18),
    "burst": (400, 250, 0.1, "square", 0.1, 14),
    "wall": (240, 200, 0.14, "triangle", 0.1, 10),
    "beam": (1200, 500, 0.18, "square", 0.05, 12),
    "wave": (500, 700, 0.12, "sine", 0.0, 12),
    "homing": (700, 900, 0.16, "sine", 0.0, 10),
    "fire": (200, 120, 0.14, "noise", 0.25, 14),
    "spray": (0, 0, 0.22, "noise", 0.2, 8),
    "throw": (600, 300, 0.1, "triangle", 0.1, 18),
    "lob": (340, 520, 0.14, "sine", 0.05, 12),
    "slam": (90, 45, 0.3, "square", 0.3, 9),
    "leap": (200, 400, 0.14, "triangle", 0.1, 12),
    "dash": (0, 0, 0.16, "noise", 0.25, 12),
    "dash_windup": (160, 320, 0.25, "square", 0.05, 6),
    "windup": (300, 600, 0.3, "sine", 0.0, 5),
    "summon": (260, 520, 0.35, "triangle", 0.1, 5),
    "shell": (500, 250, 0.14, "triangle", 0.0, 14),
    "root": (140, 100, 0.35, "triangle", 0.2, 6),
    "bubble": (700, 1100, 0.1, "sine", 0.0, 20),
    "boss_phase": (110, 40, 0.8, "square", 0.3, 3),
}


def _enemy_attack_sound(key):
    base, end, dur, wave, noise, decay = ENEMY_ATTACK_SOUND.get(key, ENEMY_ATTACK_SOUND["shot"])
    vol = 0.09 if key == "shot_small" else 0.2  # fodder shots stay in the background
    layers = []
    if wave != "noise":
        layers.append(_samples(base, dur, vol, wave, end, envelope="exp_decay", decay_rate=decay))
    if noise > 0 or wave == "noise":
        layers.append(_samples(0, dur, max(noise, 0.15), "noise", envelope="exp_decay", decay_rate=decay))
    return _mix(*layers)


def play_enemy_attack(key):
    key = key if key in ENEMY_ATTACK_SOUND else "shot"
    _play(f"enemy_{key}", lambda: _sound_from(_enemy_attack_sound(key)))


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


# ------------------------------------------------ endgame event sfx (V0.2 final) --
# Forging, Heroic dungeons, the level gates, the big islands' ferry, the Mad God's
# Room forms and the Divine items. Each is a short list of layered notes:
# (delay s, freq, freq_end, duration, wave, volume, envelope, decay). All synthesized
# here from scratch - no samples, no borrowed melodies.
EVENT_SOUND = {
    # hammer on hot metal: a clang, a ring, a second lighter tap
    "forge_hammer": [(0.0, 880, 820, 0.18, "square", 0.12, "exp_decay", 22),
                     (0.0, 0, 0, 0.06, "noise", 0.14, "exp_decay", 60),
                     (0.0, 1760, 1700, 0.3, "sine", 0.06, "exp_decay", 9)],
    # three clangs rising, then a bright shimmer: something good came off the Anvil
    "forge_success": [(0.0, 700, 660, 0.14, "square", 0.1, "exp_decay", 24),
                      (0.0, 0, 0, 0.05, "noise", 0.12, "exp_decay", 60),
                      (0.16, 820, 780, 0.14, "square", 0.1, "exp_decay", 24),
                      (0.16, 0, 0, 0.05, "noise", 0.12, "exp_decay", 60),
                      (0.32, 980, 940, 0.16, "square", 0.11, "exp_decay", 20),
                      (0.32, 0, 0, 0.05, "noise", 0.12, "exp_decay", 60),
                      (0.5, 1320, 1980, 0.45, "sine", 0.08, "exp_decay", 6),
                      (0.5, 1650, 2470, 0.45, "sine", 0.05, "exp_decay", 6)],
    "forge_fail": [(0.0, 300, 180, 0.25, "square", 0.1, "exp_decay", 10),
                   (0.12, 220, 130, 0.3, "triangle", 0.1, "exp_decay", 8)],
    # the level gate: a low double buzz
    "gate_denied": [(0.0, 150, 140, 0.16, "square", 0.11, "linear", 0),
                    (0.2, 120, 110, 0.22, "square", 0.11, "linear", 0)],
    # a Heroic portal tearing open: rising noise sweep over a minor-ish dyad
    "heroic_portal": [(0.0, 0, 0, 0.6, "noise", 0.07, "exp_decay", 4),
                      (0.0, 220, 440, 0.6, "triangle", 0.1, "linear", 0),
                      (0.0, 262, 523, 0.6, "sine", 0.07, "linear", 0),
                      (0.55, 880, 860, 0.5, "sine", 0.06, "exp_decay", 5)],
    # the ferry bell at an island harbour
    "harbour_bell": [(0.0, 523, 520, 1.1, "sine", 0.1, "exp_decay", 3),
                     (0.0, 1310, 1305, 0.9, "sine", 0.04, "exp_decay", 4),
                     (0.0, 784, 780, 0.9, "triangle", 0.03, "exp_decay", 4)],
    # the Mad God changing form: a falling roar, a thud, a wobbling growl
    "mg_transform": [(0.0, 0, 0, 1.0, "noise", 0.12, "exp_decay", 2.5),
                     (0.0, 160, 45, 1.0, "square", 0.12, "exp_decay", 2.5),
                     (0.35, 55, 40, 0.5, "square", 0.14, "exp_decay", 6),
                     (0.5, 90, 70, 0.9, "triangle", 0.1, "exp_decay", 3)],
    "mg_enrage": [(0.0, 110, 220, 0.5, "square", 0.1, "linear", 0),
                  (0.0, 0, 0, 0.5, "noise", 0.06, "exp_decay", 3)],
    # a Divine item dropping: a four-note rising arpeggio with a halo on top
    "divine_drop": [(0.0, 523, 523, 0.16, "sine", 0.1, "exp_decay", 10),
                    (0.1, 659, 659, 0.16, "sine", 0.1, "exp_decay", 10),
                    (0.2, 784, 784, 0.16, "sine", 0.1, "exp_decay", 10),
                    (0.3, 1047, 1047, 0.6, "sine", 0.1, "exp_decay", 4),
                    (0.3, 2093, 2100, 0.6, "sine", 0.04, "exp_decay", 4)],
    "mythic_drop": [(0.0, 587, 587, 0.14, "triangle", 0.1, "exp_decay", 12),
                    (0.1, 880, 880, 0.4, "triangle", 0.1, "exp_decay", 6)],
    "starfall": [(0.0, 1400, 2400, 0.12, "sine", 0.06, "exp_decay", 18),
                 (0.03, 1800, 2800, 0.1, "sine", 0.04, "exp_decay", 20)],
    "second_wind": [(0.0, 330, 660, 0.35, "sine", 0.12, "linear", 0),
                    (0.3, 660, 990, 0.5, "sine", 0.1, "exp_decay", 4),
                    (0.0, 0, 0, 0.4, "noise", 0.04, "exp_decay", 6)],
    # night-horror update: an old wooden door creaking open / thudding shut (and the bolt)
    "door_open": [(0.0, 180, 260, 0.35, "triangle", 0.08, "linear", 0),
                  (0.05, 0, 0, 0.3, "noise", 0.03, "exp_decay", 6),
                  (0.2, 300, 240, 0.25, "sine", 0.04, "exp_decay", 8)],
    "door_close": [(0.0, 260, 170, 0.2, "triangle", 0.07, "linear", 0),
                   (0.18, 80, 50, 0.18, "square", 0.12, "exp_decay", 18),
                   (0.18, 0, 0, 0.08, "noise", 0.12, "exp_decay", 40),
                   (0.34, 900, 860, 0.06, "square", 0.05, "exp_decay", 40)],
    # night-horror update
    # realism pass: the night soundscape (crickets, an owl, a distant howl) and the dawn chorus
    "crickets": [(0.0, 4200, 4300, 0.03, "square", 0.012, "linear", 0), (0.06, 4200, 4300, 0.03, "square", 0.012, "linear", 0),
                 (0.12, 4200, 4300, 0.03, "square", 0.012, "linear", 0), (0.4, 4500, 4600, 0.03, "square", 0.01, "linear", 0),
                 (0.46, 4500, 4600, 0.03, "square", 0.01, "linear", 0)],
    "owl": [(0.0, 420, 400, 0.22, "sine", 0.05, "exp_decay", 8), (0.35, 390, 360, 0.5, "sine", 0.05, "exp_decay", 4)],
    "howl": [(0.0, 300, 520, 0.6, "sine", 0.04, "linear", 0), (0.6, 520, 380, 1.4, "sine", 0.04, "exp_decay", 1.8)],
    "dawn_chorus": [(0.0, 2600, 3200, 0.08, "sine", 0.03, "linear", 0), (0.12, 3000, 2400, 0.08, "sine", 0.03, "linear", 0),
                    (0.5, 2200, 3100, 0.1, "sine", 0.025, "linear", 0), (0.9, 3400, 2800, 0.07, "sine", 0.03, "linear", 0),
                    (1.0, 3100, 3500, 0.07, "sine", 0.03, "linear", 0)],
    "heartbeat": [(0.0, 62, 48, 0.12, "sine", 0.22, "exp_decay", 16),
                  (0.0, 0, 0, 0.05, "noise", 0.04, "exp_decay", 60),
                  (0.22, 55, 42, 0.14, "sine", 0.18, "exp_decay", 14)],
    "nightfall": [(0.0, 220, 196, 1.2, "triangle", 0.09, "exp_decay", 2),
                  (0.0, 262, 233, 1.2, "sine", 0.06, "exp_decay", 2),
                  (0.4, 147, 139, 1.0, "triangle", 0.07, "exp_decay", 2.5)],
    "dawn": [(0.0, 392, 392, 0.4, "sine", 0.08, "exp_decay", 5), (0.25, 494, 494, 0.4, "sine", 0.08, "exp_decay", 5),
             (0.5, 587, 587, 0.8, "sine", 0.08, "exp_decay", 3)],
    "blood_moon_rise": [(0.0, 0, 0, 1.4, "noise", 0.06, "exp_decay", 1.6),
                        (0.0, 98, 92, 1.4, "square", 0.08, "exp_decay", 1.8),
                        (0.3, 104, 98, 1.2, "sine", 0.1, "exp_decay", 2),
                        (0.9, 62, 48, 0.12, "sine", 0.2, "exp_decay", 16), (1.1, 55, 42, 0.14, "sine", 0.16, "exp_decay", 14)],
    "night_fog": [(0.0, 0, 0, 1.5, "noise", 0.07, "linear", 0), (0.0, 110, 98, 1.5, "sine", 0.05, "linear", 0)],
    "night_hunter": [(0.0, 700, 300, 0.6, "triangle", 0.07, "exp_decay", 4),
                     (0.5, 660, 280, 0.6, "triangle", 0.06, "exp_decay", 4)],
    "night_lanterns_out": [(0.0, 0, 0, 0.25, "noise", 0.09, "exp_decay", 14), (0.15, 0, 0, 0.25, "noise", 0.07, "exp_decay", 14),
                           (0.3, 0, 0, 0.25, "noise", 0.05, "exp_decay", 14)],
    "night_market": [(0.0, 880, 880, 0.9, "sine", 0.07, "exp_decay", 3), (0.0, 1320, 1320, 0.7, "sine", 0.03, "exp_decay", 4),
                     (0.35, 784, 784, 0.9, "sine", 0.06, "exp_decay", 3)],
    "night_blood_moon": [(0.0, 98, 92, 0.8, "square", 0.08, "exp_decay", 3)],
    # night realism pass 2: weather, shooting stars, herbs, owls
    "thunder": [(0.0, 0, 0, 0.12, "noise", 0.22, "exp_decay", 30), (0.08, 70, 40, 1.4, "noise", 0.18, "exp_decay", 2),
                (0.3, 55, 35, 1.6, "sine", 0.12, "exp_decay", 2)],
    "rain_start": [(0.0, 0, 0, 1.2, "noise", 0.05, "linear", 0)],
    "rain_patter": [(0.0, 0, 0, 0.9, "noise", 0.025, "linear", 0)],
    "shooting_star": [(0.0, 2400, 900, 0.7, "sine", 0.05, "exp_decay", 4), (0.05, 3600, 1800, 0.5, "sine", 0.025,
                                                                             "exp_decay", 5)],
    "owl_flap": [(0.0, 0, 0, 0.07, "noise", 0.06, "exp_decay", 30), (0.12, 0, 0, 0.07, "noise", 0.05, "exp_decay", 30),
                 (0.24, 0, 0, 0.07, "noise", 0.04, "exp_decay", 30)],
    "herb_pick": [(0.0, 1320, 1320, 0.25, "sine", 0.05, "exp_decay", 8), (0.08, 1760, 1760, 0.3, "sine", 0.04,
                                                                         "exp_decay", 8)],
    # the Lamplighter: a match strike, then a warm lantern swell
    "night_lamplighter": [(0.0, 0, 0, 0.06, "noise", 0.12, "exp_decay", 40), (0.05, 0, 0, 0.3, "noise", 0.05, "exp_decay", 8),
                          (0.2, 392, 392, 0.9, "triangle", 0.06, "exp_decay", 3), (0.35, 587, 587, 0.8, "triangle", 0.04, "exp_decay", 3)],
    "mimic_snap": [(0.0, 0, 0, 0.08, "noise", 0.14, "exp_decay", 50), (0.02, 120, 60, 0.18, "square", 0.12, "exp_decay", 14)],
    "watcher_shriek": [(0.0, 1500, 2600, 0.5, "square", 0.06, "linear", 0), (0.0, 1520, 2650, 0.5, "triangle", 0.05, "linear", 0),
                       (0.0, 0, 0, 0.5, "noise", 0.04, "exp_decay", 4)],
    "lantern_snuff": [(0.0, 0, 0, 0.18, "noise", 0.08, "exp_decay", 20), (0.0, 600, 200, 0.18, "sine", 0.05, "exp_decay", 12)],
    "harvester_roar": [(0.0, 0, 0, 1.2, "noise", 0.12, "exp_decay", 2.2), (0.0, 130, 40, 1.2, "square", 0.12, "exp_decay", 2.2),
                       (0.2, 65, 45, 1.0, "triangle", 0.1, "exp_decay", 2.5)],
    # a heroic trial / island "calmed" / quest completion sting
    "trial_done": [(0.0, 392, 392, 0.15, "triangle", 0.1, "exp_decay", 10),
                   (0.12, 523, 523, 0.15, "triangle", 0.1, "exp_decay", 10),
                   (0.24, 784, 784, 0.4, "triangle", 0.1, "exp_decay", 5)],
}


def _event_sound(key):
    notes = EVENT_SOUND[key]
    total = max(n[0] + n[3] for n in notes)
    layers = []
    for delay, f0, f1, dur, wave, vol, env, decay in notes:
        pad = [0] * int(SAMPLE_RATE * delay)
        layers.append(pad + _samples(f0, dur, vol, wave, f1 if f1 != f0 else None, envelope=env,
                                     decay_rate=decay or 8.0))
    out = _mix(*layers)
    return out[:int(SAMPLE_RATE * (total + 0.02))]


_AMB = {"t": 0.0, "owl": 9.0, "howl": 14.0, "phase": None}


def night_ambience(dt, clock):
    """Call every frame in the Realm with RealmSim.clock_info(): crickets at night, an owl now
    and then, distant howls under a Blood Moon, and a bird chorus when dawn breaks."""
    if not clock:
        return
    import random as _r
    phase = clock.get("phase")
    if _AMB["phase"] == "night" and phase == "dawn":
        play_event("dawn_chorus")
    _AMB["phase"] = phase
    if not clock.get("night"):
        return
    _AMB["t"] -= dt
    _AMB["owl"] -= dt
    _AMB["howl"] -= dt
    if _AMB["t"] <= 0:
        _AMB["t"] = _r.uniform(1.6, 3.5)
        play_event("crickets")
    if _AMB["owl"] <= 0:
        _AMB["owl"] = _r.uniform(14, 30)
        play_event("owl")
    if clock.get("sky") in ("rain", "storm"):
        _AMB["rain"] = _AMB.get("rain", 0.0) - dt
        if _AMB["rain"] <= 0:
            _AMB["rain"] = 0.85
            play_event("rain_patter")
    if clock.get("blood") and _AMB["howl"] <= 0:
        _AMB["howl"] = _r.uniform(12, 22)
        play_event("howl")


def play_event(key):
    """One of EVENT_SOUND's endgame stingers (unknown keys are ignored)."""
    if key not in EVENT_SOUND:
        return
    _play(f"event_{key}", lambda: _sound_from(_event_sound(key)))

"""
Admin / testing chat commands - one registry shared by single-player (main.py), the co-op
server (server.py, authoritative) and the co-op client (coop_client.py, display-only bits).

Every command is a Command(name, aliases, usage, desc, category, handler, side, admin):
- handler(ctx, args) -> list of (text, color) lines (or a Panel for long output)
- side "sim": changes the game - single-player runs it directly; in co-op the client sends
  it to the server ("admin" action), which runs it and replies with an "admin_result".
- side "client": only touches the local view (help, minimap reveal, FPS, hitboxes, position)
  - always runs where it was typed.
- admin=False: an ordinary player command (/nexus, /trade...) - listed by /help, handled by
  the existing code in main.py / coop_client.py, never by this module.

ctx wraps "where am I and who am I" so one handler works in both modes - see SPCtx (here,
wrapping main.Game), ServerCtx (wrapping server.ServerState + Session) and ClientCtx
(coop_client.CoopClient, client-side commands only).

Co-op servers only accept admin commands when started with --admin (or RR_ADMIN=1).
"""
import difflib
import os
import random

import pygame

from game.constants import TILE

INFO, GOOD, WARN, BAD, HEAD = (200, 210, 230), (150, 235, 160), (240, 200, 120), (235, 120, 120), (255, 215, 120)
PANEL_LINES = 4  # more output lines than this opens the scrollable command panel instead of the feed
FEED_MAX_CHARS = 84  # ...and so does any line longer than this (the feed is centred and doesn't wrap)


def wants_panel(res):
    return isinstance(res, Panel) or len(res) > PANEL_LINES or any(len(t) > FEED_MAX_CHARS for t, _c in res)

CATEGORIES = [
    ("player", "Player"),
    ("items", "Items"),
    ("world", "World & time"),
    ("night", "Night & weather"),
    ("mobs", "Mobs"),
    ("dungeons", "Dungeons & story"),
    ("debug", "Debug"),
    ("normal", "Everyday commands"),
]


class Panel:
    """Long command output: shown in the scrollable command panel (Esc closes, wheel scrolls)."""

    def __init__(self, title, lines):
        self.title = title
        self.lines = lines

    def __iter__(self):
        return iter(self.lines)

    def __len__(self):
        return len(self.lines)


class Command:
    def __init__(self, name, handler, usage="", desc="", category="debug", aliases=(), side="sim", admin=True,
                 details=""):
        self.name, self.handler, self.usage, self.desc = name, handler, usage, desc
        self.category, self.aliases, self.side, self.admin, self.details = category, tuple(aliases), side, admin, details


COMMANDS = {}
_ALIASES = {}


def command(name, usage="", desc="", category="debug", aliases=(), side="sim", details=""):
    def deco(fn):
        cmd = Command(name, fn, usage, desc, category, aliases, side, True, details)
        COMMANDS[name] = cmd
        for a in aliases:
            _ALIASES[a] = name
        return fn
    return deco


# the everyday (non-admin) commands - handled by main.py / coop_client.py, only listed here
NORMAL_COMMANDS = [
    ("nexus", "/nexus", "go back to the Nexus (also leaves a dungeon)"),
    ("realm", "/realm", "from the Nexus: into the Realm"),
    ("vault", "/vault", "from the Nexus: open your vault"),
    ("bazaar", "/bazaar", "from the Nexus: the Bazaar"),
    ("trade", "/trade", "co-op: trade with the nearest player"),
    ("accept", "/accept  /decline", "co-op: answer a trade invite"),
    ("crew", "/crew create|join|leave <name>", "co-op: crews"),
    ("msg", "/msg <name> <text>", "co-op: whisper (also /w, /tell)"),
    ("help", "/help [page | category | command]", "this list"),
]
for _n, _u, _d in NORMAL_COMMANDS:
    COMMANDS.setdefault(_n, Command(_n, None, _u, _d, "normal", side="client", admin=False))


def resolve(name):
    name = (name or "").lower()
    name = _ALIASES.get(name, name)
    return COMMANDS.get(name)


def is_admin_command(name):
    c = resolve(name)
    return c is not None and c.admin


def runs_on_client(name):
    c = resolve(name)
    return c is not None and c.side == "client"


def run(ctx, text):
    """Runs one '/command args' line (without the slash). Returns a list of (text, color)
    or a Panel. Unknown / non-admin commands return None (the caller handles those)."""
    parts = (text or "").strip().split()
    if not parts:
        return None
    cmd = resolve(parts[0])
    if cmd is None or not cmd.admin:
        return None
    try:
        out = cmd.handler(ctx, parts[1:])
    except _Usage as e:
        return [(f"Usage: {cmd.usage}" + (f" - {e}" if str(e) else ""), WARN)]
    except Exception as e:  # a test tool must never take the game down
        return [(f"/{cmd.name} failed: {type(e).__name__}: {e}", BAD)]
    return out if out is not None else []


class _Usage(Exception):
    pass


def _need(args, n, msg=""):
    if len(args) < n:
        raise _Usage(msg)


def _int(s, lo=None, hi=None, name="number"):
    try:
        v = int(float(s))
    except (TypeError, ValueError):
        raise _Usage(f"{name} must be a number")
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _float(s, lo=None, hi=None, name="number"):
    try:
        v = float(s)
    except (TypeError, ValueError):
        raise _Usage(f"{name} must be a number")
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _pick(query, options, what="option"):
    """Fuzzy-picks one of `options` (strings) for `query`: exact, prefix, substring, close match."""
    q = (query or "").lower().replace(" ", "_")
    opts = list(options)
    low = {o.lower(): o for o in opts}
    if q in low:
        return low[q]
    pre = [o for o in opts if o.lower().startswith(q)]
    if len(pre) >= 1:
        return min(pre, key=len)
    sub = [o for o in opts if q in o.lower()]
    if sub:
        return min(sub, key=len)
    close = difflib.get_close_matches(q, [o.lower() for o in opts], n=1, cutoff=0.5)
    if close:
        return low[close[0]]
    raise _Usage(f"no {what} like '{query}' (try: {', '.join(sorted(opts)[:12])}{'...' if len(opts) > 12 else ''})")


def _toggle(args, current):
    if not args:
        return not current
    a = args[0].lower()
    if a in ("on", "1", "true", "yes"):
        return True
    if a in ("off", "0", "false", "no"):
        return False
    return not current


def _on_off(v):
    return "ON" if v else "OFF"


# ============================================================================ contexts
class BaseCtx:
    coop = False
    is_server = False

    # --- overridden ------------------------------------------------------
    player = None

    @property
    def zone(self):
        return "nexus"

    @property
    def sim(self):
        """The RealmSim you're in (Realm or a dungeon), or None in a hub."""
        return None

    @property
    def realm_sim(self):
        return None

    def players_in(self, sim):
        return [self.player]

    def goto(self, where):
        return False

    def enter_dungeon(self, theme, difficulty):
        return False

    def account_name(self):
        return self.player.name

    def minimap(self):
        return None

    def tilemap(self):
        sim = self.sim
        if sim is not None:
            return sim.realm_map
        return None

    def toggle_flag(self, name, args):
        cur = getattr(self, "_flags", {}).get(name, False)
        return _toggle(args, cur)

    # --- shared helpers --------------------------------------------------
    def need_sim(self):
        sim = self.sim
        if sim is None:
            raise _Usage("you need to be in the Realm or a dungeon")
        return sim

    def need_realm(self):
        """The open Realm's sim (day/night lives there) - even from a hub or dungeon."""
        sim = self.realm_sim
        if sim is None:
            raise _Usage("enter the Realm first (/goto realm)")
        return sim

    def give(self, items):
        """Backpack -> Bag 2 -> a bag at your feet (or pending rewards in a hub)."""
        p, where = self.player, {"backpack": 0, "bag2": 0, "ground": 0, "pending": 0}
        floor = []
        for it in items:
            if p.try_pickup(it):
                where["backpack" if it in p.backpack else "bag2"] += 1
            else:
                floor.append(it)
        if floor:
            sim = self.sim
            if sim is not None:
                sim._spawn_loot_bag([("white", it) for it in floor], pygame.Vector2(p.pos), owner_pid=p.pid)
                where["ground"] += len(floor)
            else:
                p.sidequests.pending_items.extend(floor)
                where["pending"] += len(floor)
        bits = [f"{n} in {k}" for k, n in where.items() if n]
        return ", ".join(bits) if bits else "nothing"


class SPCtx(BaseCtx):
    """Single-player: wraps main.Game."""

    def __init__(self, game):
        self.g = game

    @property
    def _m(self):
        import sys
        return sys.modules[type(self.g).__module__]  # main.py (also when it runs as __main__)

    @property
    def player(self):
        return self.g.player

    @property
    def zone(self):
        _m = self._m
        return {_m.STATE_REALM: "realm", _m.STATE_BONUS: "bonus", _m.STATE_NEXUS: "nexus",
                _m.STATE_BAZAAR: "bazaar", _m.STATE_VAULT_ROOM: "vault_room"}.get(self.g.state, "other")

    @property
    def sim(self):
        z = self.zone
        return self.g.realm_sim if z == "realm" else self.g.bonus_sim if z == "bonus" else None

    @property
    def realm_sim(self):
        return self.g.realm_sim

    def goto(self, where):
        g = self.g
        if where == "nexus":
            g.bonus_sim = None
            g.go_nexus()
        elif where == "realm":
            if g.realm_sim is None:
                g.enter_realm()
            else:
                g.bonus_sim = None
                g.player.pos = g.realm_sim.spawn_point()
                g.state = self._m.STATE_REALM
        elif where == "vault":
            g.enter_vault_room()
        elif where == "bazaar":
            g.enter_bazaar()
        elif where == "forge":
            g.enter_forge()
        else:
            return False
        return True

    def enter_dungeon(self, theme, difficulty):
        _m = self._m
        from game.realm_sim import RealmSim
        from game import minimap
        g = self.g
        g.bonus_sim = RealmSim(bonus=True, theme=theme, difficulty_name=difficulty, story_act=g.player.story.act)
        g._bonus_from_nexus = g.realm_sim is None
        g.bonus_minimap = minimap.MinimapState()
        g._pre_bonus_pos = pygame.Vector2(g.player.pos) if g.state == _m.STATE_REALM else None
        g.player.pos = g.bonus_sim.spawn_point()
        g.state = _m.STATE_BONUS
        return True

    def account_name(self):
        return self.g.player_name or self.player.name

    def minimap(self):
        return self.g._current_minimap()

    def tilemap(self):
        _m = self._m
        g = self.g
        if g.state == _m.STATE_NEXUS:
            return g.nexus_map
        if g.state == _m.STATE_BAZAAR:
            return g.bazaar_map
        if g.state == _m.STATE_VAULT_ROOM:
            return g.vault_room_map
        return BaseCtx.tilemap(self)

    def set_flag(self, name, value):
        setattr(self.g, name, value)

    def get_flag(self, name):
        return getattr(self.g, name, False)

    def set_act(self, act):
        from game import accounts, story
        self.player.story = story.StoryProgress(act)
        accounts.set_story_act(self.account_name(), act)


class ServerCtx(BaseCtx):
    """Co-op server: wraps server.ServerState + the typing player's Session."""
    coop = True
    is_server = True

    def __init__(self, state, session):
        self.state, self.s = state, session

    @property
    def player(self):
        return self.s.player

    @property
    def zone(self):
        return self.s.zone

    @property
    def sim(self):
        if self.s.zone == "realm":
            return self.state.realm_sim
        if self.s.zone == "bonus":
            return self.state.bonus_sims.get(self.s.bonus_sim_id)
        return None

    @property
    def realm_sim(self):
        return self.state.realm_sim

    def players_in(self, sim):
        out = []
        for o in self.state.sessions.values():
            osim = self.state.realm_sim if o.zone == "realm" else (
                self.state.bonus_sims.get(o.bonus_sim_id) if o.zone == "bonus" else None)
            if osim is sim and o.player.alive:
                out.append(o.player)
        return out or [self.player]

    def goto(self, where):
        import server as _sv
        s, st, p = self.s, self.state, self.s.player
        if where == "nexus":
            s.zone, s.bonus_sim_id = _sv.ZONE_NEXUS, None
            p.pos = _sv._nexus_spawn_pos(st)
        elif where == "realm":
            s.zone, s.bonus_sim_id = _sv.ZONE_REALM, None
            p.pos = st.realm_sim.spawn_point()
        elif where == "vault":
            s.zone, s.bonus_sim_id = _sv.ZONE_VAULT_ROOM, None
            p.pos = _sv._vault_room_spawn_pos(st)
        elif where == "bazaar":
            s.zone, s.bonus_sim_id = _sv.ZONE_BAZAAR, None
            p.pos = st.bazaar_map.center_world_pos()
        elif where == "forge":
            _sv._enter_forge(st, s)
        else:
            return False
        return True

    def enter_dungeon(self, theme, difficulty):
        import server as _sv
        from game.realm_sim import RealmSim
        st, s = self.state, self.s
        bsim_id = st._next_bonus_sim_id
        st._next_bonus_sim_id += 1
        st.bonus_sims[bsim_id] = RealmSim(bonus=True, theme=theme, difficulty_name=difficulty,
                                          story_act=s.player.story.act)
        s.pre_bonus_pos = pygame.Vector2(s.player.pos) if s.zone == _sv.ZONE_REALM else None
        s.bonus_from_nexus = s.zone != _sv.ZONE_REALM
        s.player.pos = st.bonus_sims[bsim_id].spawn_point()
        s.zone, s.bonus_sim_id = _sv.ZONE_BONUS, bsim_id
        return True

    def tilemap(self):
        st, z = self.state, self.s.zone
        if z == "nexus":
            return st.nexus_map
        if z == "bazaar":
            return st.bazaar_map
        if z == "vault_room":
            return st.vault_room_map
        return BaseCtx.tilemap(self)

    def set_act(self, act):
        from game import accounts, story
        self.player.story = story.StoryProgress(act)
        accounts.set_story_act(self.player.name, act)


class ClientCtx(BaseCtx):
    """Co-op client: only client-side commands run here (help, minimap, FPS, hitboxes, pos)."""
    coop = True

    def __init__(self, client):
        self.c = client

    @property
    def player(self):
        return self.c.you

    @property
    def zone(self):
        return self.c.zone

    def minimap(self):
        return self.c._current_minimap()

    def tilemap(self):
        z = self.c.zone
        if z == "nexus":
            return self.c.nexus_map
        if z == "bazaar":
            return getattr(self.c, "bazaar_map", None)
        if z == "vault_room":
            return getattr(self.c, "vault_room_map", None)
        return self.c.tilemap

    def set_flag(self, name, value):
        setattr(self.c, name, value)

    def get_flag(self, name):
        return getattr(self.c, name, False)


# ============================================================================ /help
def _help_lines_for(cmds):
    out = []
    for c in cmds:
        alias = f"  (also /{', /'.join(c.aliases)})" if c.aliases else ""
        out.append((f"{c.usage}{alias}", INFO if c.admin else (180, 200, 180)))
        out.append((f"      {c.desc}", (150, 160, 180)))
    return out


def help_panel(arg=None, admin_on=True, coop=False):
    by_cat = {}
    for c in COMMANDS.values():
        by_cat.setdefault(c.category, []).append(c)
    for v in by_cat.values():
        v.sort(key=lambda c: c.name)
    if arg:
        a = arg.lower().lstrip("/")
        cmd = resolve(a)
        if cmd is not None:
            lines = [(cmd.usage, HEAD), (cmd.desc, INFO)]
            if cmd.aliases:
                lines.append(("Also: /" + ", /".join(cmd.aliases), INFO))
            if cmd.details:
                lines += [(ln, (170, 180, 200)) for ln in cmd.details.split("\n")]
            if cmd.admin and coop:
                lines.append(("(co-op: needs a server started with --admin)", WARN))
            return Panel(f"/help {cmd.name}", lines)
        for key, label in CATEGORIES:
            if a in (key, label.lower()) or label.lower().startswith(a):
                return Panel(f"/help {key} - {label}", _help_lines_for(by_cat.get(key, [])))
        if a.isdigit():
            pages = [k for k, _l in CATEGORIES]
            i = int(a) - 1
            if 0 <= i < len(pages):
                key = pages[i]
                return Panel(f"/help {a} - {dict(CATEGORIES)[key]}", _help_lines_for(by_cat.get(key, [])))
        return Panel("/help", [(f"No command or category '{arg}'.", WARN)])
    lines = [("Type /help <category> (or a page number) for details, /help <command> for one command.", HEAD),
             ("Scroll with the mouse wheel / PgUp PgDn, Esc closes.", (170, 180, 200))]
    if coop and not admin_on:
        lines.append(("Admin commands need a server started with --admin (or RR_ADMIN=1).", WARN))
    for i, (key, label) in enumerate(CATEGORIES):
        cmds = by_cat.get(key, [])
        if not cmds:
            continue
        lines.append(("", INFO))
        lines.append((f"{i + 1}. {label}  ({len(cmds)})", HEAD))
        names = [f"/{c.name}" for c in cmds]
        row = ""
        for n in names:
            if len(row) + len(n) + 2 > 70:
                lines.append(("   " + row, INFO))
                row = ""
            row += n + "  "
        if row:
            lines.append(("   " + row, INFO))
    return Panel("/help - commands", lines)


@command("help", "/help [page | category | command]", "list every command (paged by category)",
         "normal", aliases=("?", "commands"), side="client")
def _cmd_help(ctx, args):
    return help_panel(" ".join(args) if args else None, coop=ctx.coop,
                      admin_on=getattr(ctx, "admin_on", True))


COMMANDS["help"].admin = True  # handled here (it must list the registry), still shown under "Everyday"


# ============================================================================ player
STAT_ALIASES = {"att": "att", "attack": "att", "def": "deF", "defense": "deF", "spd": "spd", "speed": "spd",
                "dex": "dex", "dexterity": "dex", "vit": "vit", "vitality": "vit", "wis": "wis", "wisdom": "wis",
                "hp": "hp_max", "mp": "mp_max", "life": "hp_max", "mana": "mp_max"}
ADMIN_MAX_STATS = {"att": 75, "deF": 40, "spd": 75, "dex": 75, "vit": 75, "wis": 75}
ADMIN_MAX_HP_MP = (770, 385)


@command("xp", "/xp <amount>", "gain XP (levels up as normal)", "player")
def _cmd_xp(ctx, args):
    _need(args, 1)
    n = _int(args[0], 0, 10 ** 7, "amount")
    p = ctx.player
    before = p.level
    p.gain_xp(n)
    return [(f"+{n} XP - level {before} -> {p.level} ({p.xp} into this level)", GOOD)]


@command("level", "/level <1-20>", "level up to that level (stats roll as normal)", "player", aliases=("lvl",))
def _cmd_level(ctx, args):
    from game import constants as C
    from game.entities import LEVEL_CAP
    _need(args, 1)
    n = _int(args[0], 1, LEVEL_CAP, "level")
    p = ctx.player
    if n < p.level:
        return [(f"Can't level down (you're {p.level}). Start a new character for a low level.", WARN)]
    while p.level < n:
        p.gain_xp(C.xp_to_next(p.level) - p.xp)
    return [(f"Level {p.level}. HP {p.hp_max}, MP {p.mp_max}", GOOD)]


@command("maxstats", "/maxstats", "level 20 and every stat at a high cap (HP 770, MP 385)", "player",
         aliases=("max",))
def _cmd_maxstats(ctx, args):
    _cmd_level(ctx, ["20"])
    p = ctx.player
    for k, v in ADMIN_MAX_STATS.items():
        setattr(p, k, max(getattr(p, k), v))
    p.hp_max, p.mp_max = max(p.hp_max, ADMIN_MAX_HP_MP[0]), max(p.mp_max, ADMIN_MAX_HP_MP[1])
    p.hp, p.mp = p.hp_max, p.mp_max
    return [("Maxed: level 20, " + ", ".join(f"{k.upper()} {getattr(p, k)}" for k in ADMIN_MAX_STATS), GOOD)]


@command("stat", "/stat <att|def|spd|dex|vit|wis|hp|mp> <value>", "set one base stat", "player")
def _cmd_stat(ctx, args):
    _need(args, 2)
    key = STAT_ALIASES.get(args[0].lower())
    if key is None:
        raise _Usage("stat must be att, def, spd, dex, vit, wis, hp or mp")
    v = _int(args[1], 0, 100000, "value")
    p = ctx.player
    setattr(p, key, v)
    if key == "hp_max":
        p.hp = min(p.hp, v) if p.hp > v else v
    if key == "mp_max":
        p.mp = v
    return [(f"{args[0].upper()} = {v}", GOOD)]


@command("heal", "/heal", "full HP and MP, clears slow/root", "player")
def _cmd_heal(ctx, args):
    p = ctx.player
    p.hp, p.mp = p.hp_max, p.mp_max
    p.root_time = 0.0
    for k in ("slow_time", "_slow_t"):
        if hasattr(p, k):
            setattr(p, k, 0.0)
    return [(f"Healed: {p.hp}/{p.hp_max} HP, {p.mp}/{p.mp_max} MP", GOOD)]


@command("god", "/god [on|off]", "invulnerable: no damage at all", "player", aliases=("invuln",))
def _cmd_god(ctx, args):
    p = ctx.player
    p.god = _toggle(args, getattr(p, "god", False))
    return [(f"God mode {_on_off(p.god)}", GOOD if p.god else INFO)]


@command("speed", "/speed <0.25-10>", "walk-speed multiplier (1 = normal)", "player", aliases=("fast",))
def _cmd_speed(ctx, args):
    p = ctx.player
    m = _float(args[0], 0.25, 10.0, "multiplier") if args else (1.0 if getattr(p, "admin_speed", 1.0) != 1.0 else 3.0)
    p.admin_speed = m
    return [(f"Speed x{m:g}", GOOD)]


@command("noclip", "/noclip [on|off]", "walk through walls, water and doors", "player", aliases=("ghost",))
def _cmd_noclip(ctx, args):
    p = ctx.player
    p.noclip = _toggle(args, getattr(p, "noclip", False))
    return [(f"Noclip {_on_off(p.noclip)}", GOOD if p.noclip else INFO)]


@command("kill", "/kill", "kill yourself (tests death / permadeath - the character is deleted!)", "player",
         aliases=("suicide",))
def _cmd_kill(ctx, args):
    if ctx.sim is None:
        return [("You can only die in the Realm or a dungeon.", WARN)]
    p = ctx.player
    p.god = False
    p.hp = 0
    p.alive = False
    return [("You died. (On purpose.)", BAD)]


@command("clearbag", "/clearbag [all]", "empty the backpack (and Bag 2 + Shards with 'all')", "player",
         aliases=("clearinv",))
def _cmd_clearbag(ctx, args):
    p = ctx.player
    n = len(p.backpack)
    p.backpack.clear()
    if args and args[0].lower() == "all":
        n += len(p.backpack2) + sum(1 for r in p.rune_slots if r is not None)
        p.backpack2.clear()
        p.rune_slots = [None] * len(p.rune_slots)
    return [(f"Removed {n} item(s).", GOOD)]


@command("echoes", "/echoes <amount>", "add Echoes to your account (the Echo Keeper's currency)", "player")
def _cmd_echoes(ctx, args):
    from game import accounts
    _need(args, 1)
    n = _int(args[0], -10 ** 6, 10 ** 6, "amount")
    accounts.add_echoes(ctx.account_name(), n)
    return [(f"+{n} Echoes (account total {accounts.get_echoes(ctx.account_name())})", GOOD)]


@command("potions", "/potions reset", "reset the permanent-potion cap counter", "player")
def _cmd_potions(ctx, args):
    if not args or args[0].lower() != "reset":
        p = ctx.player
        return [(f"Permanent potions drunk: {sum(p.potions_used.values())} "
                 f"({', '.join(f'{k} {v}' for k, v in p.potions_used.items() if v)})", INFO)]
    p = ctx.player
    p.potions_used = {k: 0 for k in p.potions_used}
    return [("Potion cap reset - drink away.", GOOD)]


@command("buffs", "/buffs [clear]", "list (or clear) your timed buffs", "player")
def _cmd_buffs(ctx, args):
    p = ctx.player
    if args and args[0].lower() == "clear":
        p.temp_buffs = {}
        p.haste_time = p.root_time = 0.0
        return [("Buffs cleared.", GOOD)]
    if not p.temp_buffs:
        return [("No timed buffs.", INFO)]
    return [(", ".join(f"{k} +{a} ({t:.0f}s)" for k, (a, t) in p.temp_buffs.items()), INFO)]


# ============================================================================ items
_CATALOG = None


def _item_catalog():
    """[(display name, kind label, factory(cls_name) -> Item)] - every item the game can make."""
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    from game import items as I, runes, gems
    from game.realm_sim import DUNGEON_THEMES
    out = []
    for cls, rows in I.WEAPONS.items():
        for i, (n, shape, t, (mn, mx)) in enumerate(rows):
            out.append((n, f"T{t} {cls} weapon",
                        (lambda n=n, shape=shape, t=t, mn=mn, mx=mx, cls=cls, i=i:
                         lambda _c: I.Item(n, I.SLOT_WEAPON, t, shape, min_dmg=mn, max_dmg=mx,
                                           description=I._weapon_description(cls, min(i, 10))))()))
    for arch, table in I._ARMOR_TABLE_BY_ARCHETYPE.items():
        for n, t, bonus, desc in table:
            out.append((n, f"T{t} {arch} armor", (lambda n=n, t=t, bonus=bonus, desc=desc:
                       lambda _c: I.Item(n, I.SLOT_ARMOR, t, "armor", stat_bonus=dict(bonus), description=desc))()))
    for n, t, bonus, desc in I.RINGS:
        out.append((n, f"T{t} ring", (lambda n=n, t=t, bonus=bonus, desc=desc:
                   lambda _c: I.Item(n, I.SLOT_RING, t, "ring", stat_bonus=dict(bonus), description=desc))()))
    for cls, rows in I.ABILITIES.items():
        for n, effect, t, mp, mag, desc in rows:
            out.append((n, f"T{t} {cls} ability", (lambda n=n, effect=effect, t=t, mp=mp, mag=mag, desc=desc:
                       lambda _c: I.Item(n, I.SLOT_ABILITY, t, "ability", effect=effect, mp_cost=mp,
                                         magnitude=mag, description=desc))()))
    for cls, uts in I.UT_WEAPONS.items():
        for ut in uts:
            n, shape, (mn, mx) = ut[0], ut[1], ut[2]
            proc, desc = (ut[3] if len(ut) > 3 else ""), (ut[4] if len(ut) > 4 else "")
            out.append((n, f"UT {cls} weapon", (lambda n=n, shape=shape, mn=mn, mx=mx, proc=proc, desc=desc:
                       lambda _c: I.Item(n, I.SLOT_WEAPON, 0, shape, is_ut=True, min_dmg=mn, max_dmg=mx, proc=proc,
                                         description=desc))()))
    for piece in ("weapon", "armor", "ring", "ability"):
        out.append((f"Divine {piece}", "Divine (your class)",
                    (lambda piece=piece: lambda c: I.make_divine(c, piece))()))
    for stat in I.STAT_KEYS:
        out.append((I._POTION_NAMES[stat], "permanent potion", (lambda s=stat: lambda _c: I.make_potion(s))()))
        out.append((I.make_temp_potion(stat).name, "temp potion", (lambda s=stat: lambda _c: I.make_temp_potion(s))()))
    for kind, d in I.PET_KINDS.items():
        out.append((f"{d['name']} Egg", f"{d['rarity']} pet egg", (lambda k=kind: lambda _c: I.make_egg(k))()))
    for theme, th in DUNGEON_THEMES.items():
        if th.get("mg_room") or theme == "forge":
            continue
        out.append((f"{th['label']} Shard", "dungeon shard",
                    (lambda t=theme, lab=th["label"]: lambda _c: I.make_dungeon_shard(t, lab))()))
    for n, fn in (("Mad God's Room Key", I.make_mad_god_key), ("Forge Ingot", I.make_forge_ingot),
                  ("Light of RDV", I.make_rdv_ring), ("Moonpetal", I.make_moonpetal),
                  ("Ghostbloom", I.make_ghostbloom), ("Star Fragment", I.make_star_fragment),
                  ("Old Boot", I.make_old_boot), ("Rubber Duck", I.make_rubber_duck),
                  ("Cursed Ring", I.make_cursed_ring), ("Fishing Net", I.make_fishing_net_weapon),
                  ("Waterlogged Sandwich", I.make_waterlogged_sandwich)):
        out.append((fn().name if n in ("Rubber Duck", "Cursed Ring", "Fishing Net") else n, "special",
                    (lambda f=fn: lambda _c: f())()))
    for kind in gems.KINDS:
        for grade in gems.GRADES:
            out.append((gems.stone_name(kind, grade), "gemstone", (lambda k=kind, g=grade: lambda _c: gems.make_gem(k, g))()))
    for eff in runes.EFFECT_KEYS:
        for rar in runes.RARITIES:
            out.append((runes.make_rune(rar, eff).name, "weapon shard",
                        (lambda r=rar, e=eff: lambda _c: runes.make_rune(r, e))()))
    _CATALOG = out
    return out


def find_items(query, tier=None):
    """Catalog rows matching a free-text query, best first."""
    q = query.lower().strip()
    toks = [t for t in q.replace("'", "").split() if t]
    scored = []
    for row in _item_catalog():
        name, label = row[0].lower().replace("'", ""), row[1].lower()
        hay = name + " " + label
        if tier is not None and f"t{tier} " not in label + " ":
            continue
        if name == q.replace("'", ""):
            s = 1000
        elif name.startswith(q.replace("'", "")):
            s = 500 - len(name)
        elif toks and all(t in hay for t in toks):
            s = 300 - len(name) + (50 if all(t in name for t in toks) else 0)
        else:
            r = difflib.SequenceMatcher(None, q, name).ratio()
            s = int(r * 200) if r > 0.6 else -1
        if s >= 0:
            scored.append((s, row))
    scored.sort(key=lambda x: -x[0])
    return [r for _s, r in scored]


def _split_count_tier(args):
    """Trailing numbers: '<query> [tier] [count]' and 'x<n>' anywhere for a count."""
    args = list(args)
    count, tier = 1, None
    for a in list(args):
        if a.lower().startswith("x") and a[1:].isdigit():
            count = int(a[1:])
            args.remove(a)
    nums = []
    while args and args[-1].lstrip("-").isdigit():
        nums.insert(0, int(args.pop()))
    if len(nums) == 1:
        tier = nums[0]
    elif len(nums) >= 2:
        tier, count = nums[-2], nums[-1]
    return " ".join(args), tier, max(1, min(64, count))


@command("give", "/give <item name or words> [tier] [count]", "give yourself any item (fuzzy search)", "items",
         aliases=("i", "item"),
         details="Searches every weapon, armor, ring and ability (all classes, all tiers), UTs, Divine items, "
                 "potions, eggs, dungeon / Heroic shards, gemstones, Weapon Shards, keys, ingots, herbs, the Star "
                 "Fragment and the Light of RDV.\n"
                 "A trailing number is a TIER, two numbers are tier + count, x<n> is a count.\n"
                 "Examples:\n"
                 "  /give doomstaff\n  /give staff 11\n  /give perfect ruby x3\n  /give heavy armor 14\n"
                 "  /give divine weapon\n  /give heroic shard\n  /give potion of attack x5\n"
                 "  /give list ruby   (shows the matches without giving anything)")
def _cmd_give(ctx, args):
    _need(args, 1)
    if args[0].lower() in ("list", "search", "find"):
        q, tier, _c = _split_count_tier(args[1:])
        rows = find_items(q, tier)[:40]
        if not rows:
            return [(f"Nothing matches '{q}'.", WARN)]
        return Panel(f"/give list {q}", [(f"{n}  -  {lab}", INFO) for n, lab, _f in rows])
    q, tier, count = _split_count_tier(args)
    rows = find_items(q, tier) if q else []
    if not rows and tier is not None:  # "/give potion of attack 5" - a trailing number was a count
        rows, count, tier = find_items(q), max(1, min(64, tier)), None
    if not rows:
        return [(f"No item matches '{q}'" + (f" at tier {tier}" if tier else "") + ". Try /give list <words>.", WARN)]
    name, label, fac = rows[0]
    items = [fac(ctx.player.cls_name) for _ in range(count)]
    where = ctx.give(items)
    out = [(f"Gave {count}x {items[0].display_name} ({label}) - {where}", GOOD)]
    if len(rows) > 1:
        out.append(("Also matched: " + ", ".join(r[0] for r in rows[1:4]), (150, 160, 180)))
    return out


@command("gem", "/gem <stone|all> [grade] [count]", "give gemstones (ruby, sapphire, topaz, emerald, amethyst, "
         "onyx, diamond; chipped..perfect)", "items", aliases=("gems", "stone"))
def _cmd_gem(ctx, args):
    from game import gems
    _need(args, 1)
    grade = gems.GRADES[-1]
    count = 1
    rest = args[1:]
    if rest and not rest[0].isdigit():
        grade = _pick(rest[0], gems.GRADES, "grade")
        rest = rest[1:]
    if rest:
        count = _int(rest[0], 1, 64, "count")
    kinds = gems.KINDS if args[0].lower() == "all" else [_pick(args[0], gems.KINDS, "stone")]
    items = [gems.make_gem(k, grade) for k in kinds for _ in range(count)]
    return [(f"Gave {len(items)} {grade} stone(s): {', '.join(kinds)} - {ctx.give(items)}", GOOD)]


@command("shard", "/shard <effect|all> [rarity] [count]", "give Weapon Shards (bleed, burn, chain, keen, leech, "
         "echo...; common..mythic)", "items", aliases=("rune", "shards"))
def _cmd_shard(ctx, args):
    from game import runes
    _need(args, 1)
    rarity = "mythic"
    count = 1
    rest = args[1:]
    if rest and not rest[0].isdigit():
        rarity = _pick(rest[0], runes.RARITIES, "rarity")
        rest = rest[1:]
    if rest:
        count = _int(rest[0], 1, 64, "count")
    effs = runes.EFFECT_KEYS if args[0].lower() == "all" else [_pick(args[0], runes.EFFECT_KEYS, "effect")]
    items = [runes.make_rune(rarity, e) for e in effs for _ in range(count)]
    return [(f"Gave {len(items)} {rarity} Weapon Shard(s) - {ctx.give(items)}", GOOD)]


@command("ingots", "/ingots [count]", "give Forge Ingots (the Anvil's currency)", "items", aliases=("ingot",))
def _cmd_ingots(ctx, args):
    from game import items as I
    n = _int(args[0], 1, 64, "count") if args else 5
    return [(f"Gave {n} Forge Ingot(s) - {ctx.give([I.make_forge_ingot() for _ in range(n)])}", GOOD)]


@command("key", "/key [count]", "give the Mad God's Room Key", "items", aliases=("mgkey",))
def _cmd_key(ctx, args):
    from game import items as I
    n = _int(args[0], 1, 16, "count") if args else 1
    return [(f"Gave {n} Mad God's Room Key(s) - {ctx.give([I.make_mad_god_key() for _ in range(n)])}", GOOD)]


def _themes(heroic=None):
    from game.realm_sim import DUNGEON_THEMES
    out = {}
    for k, th in DUNGEON_THEMES.items():
        if heroic is True and not k.startswith("heroic_"):
            continue
        if heroic is False and k.startswith("heroic_"):
            continue
        out[k] = th
    return out


@command("dshard", "/dshard <theme> [count]", "give a normal Dungeon Shard (use it in the Realm to open a portal)",
         "items", aliases=("dungeonshard",))
def _cmd_dshard(ctx, args):
    from game import items as I
    _need(args, 1)
    th = _themes(False)
    key = _pick(args[0], [k for k in th if not th[k].get("mg_room") and k != "forge"], "dungeon")
    n = _int(args[1], 1, 16, "count") if len(args) > 1 else 1
    return [(f"Gave {n}x {th[key]['label']} Shard - {ctx.give([I.make_dungeon_shard(key, th[key]['label']) for _ in range(n)])}",
             GOOD)]


@command("heroicshard", "/heroicshard <theme> [count]", "give a Heroic Shard (opens that dungeon's Heroic version)",
         "items", aliases=("hshard",))
def _cmd_heroicshard(ctx, args):
    from game import items as I
    th = _themes(True)
    key = _pick(("heroic_" + args[0]) if args and not args[0].startswith("heroic_") else (args[0] if args else ""),
                list(th), "Heroic dungeon") if args else random.choice(list(th))
    n = _int(args[1], 1, 16, "count") if len(args) > 1 else 1
    return [(f"Gave {n}x {th[key]['label']} Shard - {ctx.give([I.make_dungeon_shard(key, th[key]['label']) for _ in range(n)])}",
             GOOD)]


@command("egg", "/egg <pet kind|list>", "give a pet egg", "items")
def _cmd_egg(ctx, args):
    from game import items as I
    _need(args, 1)
    if args[0].lower() == "list":
        return Panel("Pet kinds", [(f"{k}  -  {d['name']} ({d['rarity']})", INFO) for k, d in I.PET_KINDS.items()])
    kind = _pick(" ".join(args), list(I.PET_KINDS), "pet")
    return [(f"Gave a {I.PET_KINDS[kind]['name']} Egg - {ctx.give([I.make_egg(kind)])}", GOOD)]


@command("pet", "/pet <pet kind|none>", "hatch a pet straight away (replaces your current one)", "items")
def _cmd_pet(ctx, args):
    from game import items as I
    from game.entities import Pet
    _need(args, 1)
    p = ctx.player
    if args[0].lower() in ("none", "off", "remove"):
        p.pet = None
        return [("Pet removed.", GOOD)]
    kind = _pick(" ".join(args), list(I.PET_KINDS), "pet")
    p.pet = Pet(kind, pygame.Vector2(p.pos) + pygame.Vector2(-22, 18))
    return [(f"{I.PET_KINDS[kind]['name']} ({I.PET_KINDS[kind]['rarity']}) is now your pet.", GOOD)]


def _tier_set(cls, tier):
    from game import items as I
    def best(rows, t_of):
        rows = list(rows)
        under = [r for r in rows if t_of(r) <= tier]
        return max(under, key=t_of) if under else min(rows, key=t_of)
    w = best(enumerate(I.WEAPONS[cls]), lambda r: r[1][2])
    i, (n, shape, t, (mn, mx)) = w
    weapon = I.Item(n, I.SLOT_WEAPON, t, shape, min_dmg=mn, max_dmg=mx,
                    description=I._weapon_description(cls, min(i, 10)))
    an, at, ab, ad = best(I._ARMOR_TABLE_BY_ARCHETYPE[I.CLASS_ARMOR_ARCHETYPE[cls]], lambda r: r[1])
    armor = I.Item(an, I.SLOT_ARMOR, at, "armor", stat_bonus=dict(ab), description=ad)
    rn, rt, rb, rd = best(I.RINGS, lambda r: r[1])
    ring = I.Item(rn, I.SLOT_RING, rt, "ring", stat_bonus=dict(rb), description=rd)
    bn, be, bt, bmp, bmag, bd = best(I.ABILITIES[cls], lambda r: r[2])
    ability = I.Item(bn, I.SLOT_ABILITY, bt, "ability", effect=be, mp_cost=bmp, magnitude=bmag, description=bd)
    return weapon, armor, ring, ability


@command("tier", "/tier <1-14 | divine>", "equip a full gear set of that tier for your class (old gear goes to your bags)",
         "items", aliases=("gear", "kit"))
def _cmd_tier(ctx, args):
    from game import items as I
    _need(args, 1)
    p = ctx.player
    if args[0].lower() == "divine":
        new = [I.make_divine(p.cls_name, piece) for piece in ("weapon", "armor", "ring", "ability")]
    else:
        new = list(_tier_set(p.cls_name, _int(args[0], 1, 14, "tier")))
    old = [getattr(p, s) for s in ("weapon", "armor", "ring", "ability") if getattr(p, s) is not None]
    p.weapon, p.armor, p.ring, p.ability = new
    moved = ctx.give(old) if old else "nothing"
    label = "Divine" if args[0].lower() == "divine" else f"T{new[0].tier}"
    return [(f"Equipped a {label} set: {new[0].name} + armor, ring, ability", GOOD), (f"Old gear: {moved}", INFO)]


# ============================================================================ world & time
def _phase_times():
    from game import realm_sim as rs
    return {"day": 100.0, "morning": rs.DAWN_END + 5, "noon": 150.0, "goldenhour": rs.DUSK_START - 60,
            "dusk": rs.DUSK_START, "night": rs.NIGHT_START + 1, "midnight": (rs.NIGHT_START + rs.NIGHT_END) / 2,
            "dawn": rs.NIGHT_END}


@command("time", "/time <day|goldenhour|dusk|night|midnight|dawn|morning|seconds 0-600>",
         "set the time of day (night starts at 330 s, dawn at 540 s)", "world", aliases=("t",))
def _cmd_time(ctx, args):
    from game import realm_sim as rs
    sim = ctx.need_realm()
    if not args:
        c = sim.clock_info()
        return [(f"Time {sim.day_time:.0f}s / {rs.DAY_LENGTH:.0f} - {c['phase']}, {c['until']} in {c['left']:.0f}s, "
                 f"moon phase {c.get('moon_phase')}, sky {c.get('sky', 'clear')}", INFO)]
    a = args[0].lower()
    t = _phase_times().get(a)
    if t is None:
        t = _float(a, 0, rs.DAY_LENGTH - 0.01, "time")
    sim.day_time = t
    return [(f"Time set to {t:.0f}s ({sim.phase()}).", GOOD)]


@command("day", "/day", "jump to midday", "world")
def _cmd_day(ctx, args):
    return _cmd_time(ctx, ["day"])


@command("night", "/night", "jump to nightfall (a fresh night: events, weather, Blood Moon roll)", "world")
def _cmd_night(ctx, args):
    return _restart_night(ctx, None, None, None, "Night falls.")


@command("skip", "/skip", "skip to the start of the next phase (day -> dusk -> night -> dawn -> day)", "world")
def _cmd_skip(ctx, args):
    from game import realm_sim as rs
    sim = ctx.need_realm()
    nxt = {"day": rs.DUSK_START, "dusk": rs.NIGHT_START + 1, "night": rs.NIGHT_END, "dawn": rs.DAWN_END}
    ph = sim.phase()
    sim.day_time = nxt.get(ph, 0.0) % rs.DAY_LENGTH
    return [(f"{ph} -> {sim.phase()} (time {sim.day_time:.0f}s)", GOOD)]


def _restart_night(ctx, blood, event, weather, msg):
    """Ends tonight (if it's night) and starts a fresh nightfall with forced settings."""
    from game import realm_sim as rs
    sim = ctx.need_realm()
    alive = ctx.players_in(sim)
    if sim.is_night and sim.night is not None and sim.night._was_night:
        sim.night._end_night(alive)
    sim.force_blood_moon = blood if blood is not None else False
    if sim.night is not None:
        sim.night.force_event = event
    if getattr(sim, "sky", None) is not None:
        sim.sky.force_weather = weather
    sim.blood_moon_active = False
    sim.day_time = rs.NIGHTFALL_T - 0.05
    sim._was_night = False
    if sim.night is not None:
        sim.night._was_night = False
    if getattr(sim, "sky", None) is not None:
        sim.sky._was_night = False
    return [(msg + " (takes effect on the next tick)", GOOD)]


@command("bloodmoon", "/bloodmoon [on|off]", "start a Blood Moon night now (off: a normal night instead)", "night",
         aliases=("bm",))
def _cmd_bloodmoon(ctx, args):
    on = not (args and args[0].lower() in ("off", "0", "no"))
    return _restart_night(ctx, on, None, None, "The Blood Moon rises." if on else "A normal night falls.")


@command("weather", "/weather <clear|cloudy|rain|storm>", "tonight's weather (starts a night if it's day)", "night")
def _cmd_weather(ctx, args):
    from game import night_sky as NS
    _need(args, 1)
    w = _pick(args[0], list(NS.CLOUD_DARK), "weather")
    sim = ctx.need_realm()
    if sim.is_night and getattr(sim, "sky", None) is not None and not sim.blood_moon_active:
        sim.sky.weather = w
        return [(f"Weather now: {w}", GOOD)]
    return _restart_night(ctx, False, None, w, f"Night falls - weather: {w}.")


@command("nightevent", "/nightevent <fog|hunter|lanterns_out|market|lamplighter>",
         "start a fresh night with that night event", "night", aliases=("event", "ne"))
def _cmd_nightevent(ctx, args):
    from game import night as N
    _need(args, 1)
    ev = _pick(args[0], list(N.EVENTS), "night event")
    return _restart_night(ctx, False, ev, None, f"Night falls - event: {ev}.")


@command("moon", "/moon <0-7>", "set the moon phase (0 new .. 4 full .. 7)", "night")
def _cmd_moon(ctx, args):
    _need(args, 1)
    sim = ctx.need_realm()
    n = _int(args[0], 0, 7, "phase")
    sim.night_count = n
    return [(f"Moon phase {n} ({'new' if n == 0 else 'full' if n == 4 else 'waxing' if n < 4 else 'waning'}).", GOOD)]


@command("star", "/star [fall]", "a shooting star now ('fall' drops a Star Fragment nearby)", "night")
def _cmd_star(ctx, args):
    sim = ctx.need_realm()
    if getattr(sim, "sky", None) is None:
        return [("No sky here.", WARN)]
    fall = bool(args and args[0].lower() in ("fall", "land", "drop"))
    sim.sky._shooting_star(ctx.players_in(sim), fall=fall)
    return [("A shooting star" + (" falls - check the feed for where." if fall else " streaks across the sky."), GOOD)]


@command("lightning", "/lightning", "a lightning strike near you (flash + thunder)", "night", aliases=("bolt",))
def _cmd_lightning(ctx, args):
    sim = ctx.need_realm()
    if getattr(sim, "sky", None) is None:
        return [("No sky here.", WARN)]
    sim.sky._strike(ctx.player)
    return [("Lightning!", GOOD)]


def _walkable(tmap, pos):
    from game import npcs
    return npcs._walkable_near(tmap, pygame.Vector2(pos), 20) or pygame.Vector2(pos)


def _find_biome(sim, biome, near):
    from game import world
    grid = sim.realm_map.grid
    h, w = len(grid), len(grid[0])
    cx, cy = int(near.x // TILE), int(near.y // TILE)
    best, bd = None, 10 ** 12
    for y in range(0, h, 6):
        row = grid[y]
        for x in range(0, w, 6):
            if world.TILE_TO_BIOME_NAME.get(row[x]) == biome:
                d = (x - cx) ** 2 + (y - cy) ** 2
                if d < bd:
                    best, bd = (x, y), d
    return None if best is None else pygame.Vector2((best[0] + 0.5) * TILE, (best[1] + 0.5) * TILE)


def tp_targets(ctx):
    """{lowercase name: world pos or callable} - everything /tp can find by name."""
    from game import npcs, world
    out = {}
    sim = ctx.sim
    if sim is not None and not sim.is_bonus_room:
        out["spawn"] = sim.spawn_point()
        for a in getattr(sim, "areas", ()):
            c = pygame.Vector2((a["rect"].centerx + 0.5) * TILE, (a["rect"].centery + 0.5) * TILE)
            out[a["name"].lower()] = c
            out[a["key"].lower()] = c
        for isl in getattr(sim, "islands", ()):
            out[isl["label"].lower()] = pygame.Vector2(isl["pos"])
        for n in sim.npcs:
            out[npcs.NPCS.get(n.npc_id, {}).get("name", n.npc_id).lower()] = pygame.Vector2(n.pos)
        for b in sorted(set(world.TILE_TO_BIOME_NAME.values())):
            out.setdefault(b, (lambda b=b: _find_biome(sim, b, ctx.player.pos)))
        if getattr(sim, "boss", None) is not None and sim.boss.alive:
            out["boss"] = pygame.Vector2(sim.boss.pos)
        for v in getattr(sim, "gem_veins", ())[:1]:
            out["gem vein"] = (lambda: min((vv["pos"] for vv in sim.gem_veins),
                                           key=lambda q: q.distance_squared_to(ctx.player.pos)))
    elif sim is not None:
        out["spawn"] = sim.spawn_point()
        if getattr(sim, "boss", None) is not None and sim.boss.alive:
            out["boss"] = pygame.Vector2(sim.boss.pos)
    if ctx.is_server:
        for o in ctx.state.sessions.values():
            if o is not ctx.s and o.zone == ctx.s.zone:
                out[o.player.name.lower()] = pygame.Vector2(o.player.pos)
    return out


@command("tp", "/tp <x> <y> (tiles) | /tp <area, island, NPC, biome, boss, spawn, player>",
         "teleport (by tile coordinates or by name)", "world", aliases=("teleport",),
         details="By name: any named area (Tavern Town...), an island, an NPC, a biome (forest, tundra...), "
                 "'boss' (a live boss), 'spawn', 'gem vein', or another player (co-op).\n"
                 "By tiles: /tp 300 310 (the map is 1560 x 1560 tiles).\n"
                 "/tp list shows every name on this map.")
def _cmd_tp(ctx, args):
    _need(args, 1)
    tmap = ctx.tilemap()
    if tmap is None:
        return [("Nowhere to teleport here.", WARN)]
    if len(args) >= 2 and args[0].lstrip("-").replace(".", "").isdigit() and args[1].lstrip("-").replace(".", "").isdigit():
        pos = pygame.Vector2((_float(args[0]) + 0.5) * TILE, (_float(args[1]) + 0.5) * TILE)
    else:
        targets = tp_targets(ctx)
        if args[0].lower() == "list":
            return Panel("/tp names", [(n, INFO) for n in sorted(targets)])
        name = _pick(" ".join(args).lower(), list(targets), "place")
        pos = targets[name]
        if callable(pos):
            pos = pos()
        if pos is None:
            return [(f"No {name} on this map.", WARN)]
    pos = _walkable(tmap, pos)
    ctx.player.pos = pygame.Vector2(pos)
    return [(f"Teleported to tile ({int(pos.x // TILE)}, {int(pos.y // TILE)}).", GOOD)]


@command("island", "/island <1-N>", "teleport to an island's landmark plaza", "world")
def _cmd_island(ctx, args):
    sim = ctx.need_realm()
    if ctx.sim is not sim:
        ctx.goto("realm")
    isl = sorted(sim.islands, key=lambda i: i["idx"])
    if not isl:
        return [("This map has no islands.", WARN)]
    if not args:
        return Panel("Islands", [(f"{i + 1}. {d['label']}", INFO) for i, d in enumerate(isl)])
    n = _int(args[0], 1, len(isl), "island")
    d = isl[n - 1]
    ctx.player.pos = _walkable(sim.realm_map, d["pos"])
    return [(f"Island {n}: {d['label']}", GOOD)]


@command("goto", "/goto <nexus|realm|vault|bazaar|forge>", "go straight to a zone (no portal needed)", "world",
         aliases=("zone",))
def _cmd_goto(ctx, args):
    _need(args, 1)
    where = _pick(args[0], ["nexus", "realm", "vault", "bazaar", "forge"], "zone")
    ctx.goto(where)
    return [(f"Went to the {where}.", GOOD)]


@command("liveevent", "/liveevent <name|off|auto|list>", "force a live event (double loot, Blood Moon week...)",
         "world", aliases=("le",))
def _cmd_liveevent(ctx, args):
    from game import live_events as L
    if not args or args[0].lower() == "list":
        cur = L.current_event()
        return Panel("Live events", [(f"{k}  -  {d['label']}" + ("   (active)" if k == cur else ""), INFO)
                                     for k, d in L.EVENTS.items()])
    a = args[0].lower()
    if a in ("off", "none"):
        L._forced, L.ACTIVE_EVENT = "none", None
        return [("Live events off.", GOOD)]
    if a == "auto":
        L._forced, L.ACTIVE_EVENT = None, None
        return [("Live events back on the normal rotation.", GOOD)]
    key = _pick(a, list(L.EVENTS), "live event")
    L._forced, L.ACTIVE_EVENT = key, key
    return [(f"Live event: {L.EVENTS[key]['label']}", GOOD)]


@command("reveal", "/reveal", "reveal the whole minimap / full map", "world", side="client", aliases=("map",))
def _cmd_reveal(ctx, args):
    mm, tmap = ctx.minimap(), ctx.tilemap()
    if mm is None or tmap is None:
        return [("No map here.", WARN)]
    mm.reveal_all(tmap)
    return [("Map revealed.", GOOD)]


# ============================================================================ mobs
def _enemy_kind(q):
    from game.entities import ENEMY_KINDS
    return _pick(q, list(ENEMY_KINDS), "mob")


@command("spawn", "/spawn <mob kind> [count] [moonlit]", "spawn mobs around you (5 tiles out)", "mobs",
         aliases=("summon", "mob"),
         details="Any kind from the Dictionary (goblin, shade_stalker, red_harvester, owl...).\n"
                 "'moonlit' makes them the tougher silver night variant (x1.6 HP, an extra loot roll).\n"
                 "/spawn list shows every kind.")
def _cmd_spawn(ctx, args):
    from game.entities import Enemy, ENEMY_KINDS
    _need(args, 1)
    if args[0].lower() == "list":
        return Panel("Mob kinds", [(f"{k}  ({d.get('rank', 'trash')}{', night' if d.get('night_only') else ''}"
                                    f"{', neutral' if d.get('neutral') else ''})", INFO)
                                   for k, d in sorted(ENEMY_KINDS.items())])
    sim = ctx.need_sim()
    moon = any(a.lower() == "moonlit" for a in args)
    rest = [a for a in args if a.lower() != "moonlit"]
    count = 1
    if len(rest) > 1 and rest[-1].isdigit():
        count = _int(rest.pop(), 1, 50, "count")
    kind = _enemy_kind("_".join(rest))
    p = ctx.player
    scale = getattr(sim, "story_scale", 1.0) * (1.6 if moon else 1.0)
    made = 0
    for i in range(count):
        ang = 360.0 * i / count + random.uniform(-10, 10)
        pos = _walkable(sim.realm_map, p.pos + pygame.Vector2(1, 0).rotate(ang) * 5 * TILE)
        e = Enemy(kind, pos, scale, home_pos=pygame.Vector2(pos))
        e.moonlit = moon
        if not ENEMY_KINDS[kind].get("neutral"):
            e.aggro = True
        sim.enemies.append(e)
        made += 1
    return [(f"Spawned {made}x {kind}" + (" (moonlit)" if moon else ""), GOOD)]


@command("boss", "/boss [kind]", "summon a boss next to you (random world boss if no kind)", "mobs")
def _cmd_boss(ctx, args):
    from game.entities import Enemy, ENEMY_KINDS
    from game.realm_sim import BOSS_KINDS
    sim = ctx.need_sim()
    kind = _enemy_kind("_".join(args)) if args else random.choice(BOSS_KINDS)
    p = ctx.player
    pos = _walkable(sim.realm_map, p.pos + pygame.Vector2(0, -7 * TILE))
    e = Enemy(kind, pos, getattr(sim, "story_scale", 1.0) * (1.0 + p.level * 0.15))
    e.aggro = True
    sim.enemies.append(e)
    if not sim.is_bonus_room and sim.boss is None and ENEMY_KINDS[kind].get("rank") == "boss":
        sim.boss = e
    sim.vfx_events.append(("boss_appear", e.pos.x, e.pos.y, (255, 140, 0)))
    return [(f"{kind} rises ({int(e.hp_max)} HP).", GOOD)]


def _hostiles(sim, p=None, radius=None):
    out = []
    for e in sim.enemies:
        if not e.alive or getattr(e, "neutral", False):
            continue
        if radius is not None and p is not None and e.pos.distance_to(p.pos) > radius:
            continue
        out.append(e)
    return out


@command("killall", "/killall [radius tiles]", "kill every hostile mob (with loot and kill credit)", "mobs",
         aliases=("nuke",))
def _cmd_killall(ctx, args):
    sim = ctx.need_sim()
    p = ctx.player
    radius = _int(args[0], 1, 2000, "radius") * TILE if args else None
    victims = _hostiles(sim, p, radius)
    for e in victims:
        e.hp = 0
        e.alive = False
        sim._reward(e, p)
    sim.enemies = [e for e in sim.enemies if e.alive]
    if sim.boss is not None and not sim.boss.alive:
        sim.boss = None
    return [(f"Killed {len(victims)} mob(s).", GOOD)]


@command("clearmobs", "/clearmobs [radius tiles]", "remove every hostile mob (no loot)", "mobs", aliases=("clear",))
def _cmd_clearmobs(ctx, args):
    sim = ctx.need_sim()
    p = ctx.player
    radius = _int(args[0], 1, 2000, "radius") * TILE if args else None
    victims = set(id(e) for e in _hostiles(sim, p, radius))
    sim.enemies = [e for e in sim.enemies if id(e) not in victims]
    if sim.boss is not None and id(sim.boss) in victims:
        sim.boss = None
    return [(f"Removed {len(victims)} mob(s).", GOOD)]


# ============================================================================ dungeons & story
_DIFFS = {"easy": "Easy", "medium": "Medium", "hard": "Hard", "heroic": "Heroic", "godly": "Godly"}


@command("dungeon", "/dungeon <theme|list> [easy|medium|hard|heroic|godly]",
         "enter any dungeon straight away (skips level / gear gates)", "dungeons", aliases=("dg",))
def _cmd_dungeon(ctx, args):
    from game.realm_sim import DUNGEON_THEMES
    _need(args, 1)
    if args[0].lower() == "list":
        return Panel("Dungeons", [(f"{k}  -  {th['label']}", INFO) for k, th in DUNGEON_THEMES.items()])
    diff = _DIFFS.get(args[1].lower(), None) if len(args) > 1 else None
    if len(args) > 1 and diff is None:
        diff = _DIFFS[_pick(args[1], list(_DIFFS), "difficulty")]
    q = args[0].lower()
    keys = list(DUNGEON_THEMES)
    if diff == "Heroic" and not q.startswith("heroic_") and ("heroic_" + q) in DUNGEON_THEMES:
        q = "heroic_" + q
    labels = {th["label"].lower().replace(" ", "_"): k for k, th in DUNGEON_THEMES.items()}
    try:
        theme = _pick(q, keys, "dungeon")
    except _Usage:
        theme = labels[_pick(q, list(labels), "dungeon")]
    if diff is None:
        diff = "Heroic" if theme.startswith("heroic_") else "Godly" if DUNGEON_THEMES[theme].get("mg_room") else "Medium"
    ctx.enter_dungeon(theme, diff)
    return [(f"Entered {DUNGEON_THEMES[theme]['label']} ({diff}). /nexus to leave.", GOOD)]


@command("mgroom", "/mgroom", "enter the Mad God's Room (3 forms)", "dungeons", aliases=("madgod",))
def _cmd_mgroom(ctx, args):
    from game.items import MAD_GOD_ROOM_THEME
    return _cmd_dungeon(ctx, [MAD_GOD_ROOM_THEME, "godly"])


@command("act", "/act <0-7>", "jump the story to that act (0 = Prologue; saved on the account)", "dungeons",
         aliases=("story",))
def _cmd_act(ctx, args):
    from game import story
    if not args:
        a = ctx.player.story.act
        return Panel("Story acts", [(f"{i}. {act['title']}" + ("   <- you" if i == a else ""), INFO)
                                    for i, act in enumerate(story.ACTS)])
    n = _int(args[0], 0, story.FINAL_ACT, "act")
    ctx.set_act(n)
    title = story.ACTS[n]["title"] if n < len(story.ACTS) else "Finished"
    return [(f"Story act {n}: {title}", GOOD)]


@command("quest", "/quest list | done <id|all> | reset | give <id>", "side quests: list, complete, reset, accept",
         "dungeons", aliases=("q",))
def _cmd_quest(ctx, args):
    from game import sidequests as SQ
    p = ctx.player
    sq = p.sidequests
    sub = args[0].lower() if args else "list"
    if sub == "list":
        lines = []
        for qid, q in SQ.QUESTS.items():
            st = "ACTIVE" if qid in sq.active else "done" if qid in sq.done else "-"
            have = f" {int(sq.progress(qid, p))}/{q['need']}" if qid in sq.active else ""
            lines.append((f"{qid}  [{st}{have}]  {q['title']}", GOOD if st == "ACTIVE" else INFO))
        return Panel("Side quests", lines)
    if sub == "reset":
        p.sidequests = SQ.SideQuestProgress()
        p.sidequests.ensure_board()
        return [("Side quests reset (a fresh board of 3).", GOOD)]
    if sub in ("give", "accept", "start"):
        _need(args, 2)
        qid = _pick(args[1], list(SQ.QUESTS), "quest")
        if qid in sq.done:
            sq.done.remove(qid)
        msgs = sq.accept(qid)
        return msgs or [(f"{qid} is already active.", INFO)]
    if sub in ("done", "complete", "finish"):
        _need(args, 2)
        ids = list(sq.active) if args[1].lower() == "all" else [_pick(args[1], list(SQ.QUESTS), "quest")]
        out = []
        for qid in ids:
            if qid not in sq.active:
                if qid in sq.done:
                    sq.done.remove(qid)
                sq.active[qid] = {"have": 0.0, "seen": []}
            out += sq._complete(qid, p)
        out += sq.flush(p)
        return Panel("Quests completed", out) if len(out) > PANEL_LINES else out
    raise _Usage()


@command("achievement", "/achievement <id|all|list>", "unlock an achievement (and its title)", "dungeons",
         aliases=("ach",))
def _cmd_achievement(ctx, args):
    from game import achievements as A
    name = ctx.account_name()
    if not args or args[0].lower() == "list":
        have = A.load(name)
        return Panel("Achievements", [(f"{aid}  -  {title}: {desc}" + ("   (unlocked)" if aid in have else ""),
                                       GOOD if aid in have else INFO) for aid, title, desc in A.ACHIEVEMENTS])
    ids = [a[0] for a in A.ACHIEVEMENTS] if args[0].lower() == "all" else [_pick(args[0], [a[0] for a in A.ACHIEVEMENTS], "achievement")]
    got = []
    for aid in ids:
        changed, title = A.unlock(name, aid)
        if changed:
            got.append(aid)
            if title:
                ctx.player.title = title
    return [(f"Unlocked: {', '.join(got) if got else 'nothing new'}", GOOD)]


# ============================================================================ debug
@command("fps", "/fps [on|off]", "toggle the FPS counter", "debug", side="client")
def _cmd_fps(ctx, args):
    from game import settings
    v = _toggle(args, settings.get("show_fps"))
    settings.change("show_fps", v)
    return [(f"FPS counter {_on_off(v)}", GOOD)]


@command("hitboxes", "/hitboxes [on|off]", "draw the real hit circles of players, mobs and bullets", "debug",
         side="client", aliases=("hb",))
def _cmd_hitboxes(ctx, args):
    v = _toggle(args, ctx.get_flag("debug_hitboxes"))
    ctx.set_flag("debug_hitboxes", v)
    return [(f"Hitboxes {_on_off(v)}", GOOD)]


@command("pos", "/pos", "your position (tiles and pixels), zone and biome", "debug", side="client",
         aliases=("where", "coords"))
def _cmd_pos(ctx, args):
    from game import world
    p = ctx.player
    tmap = ctx.tilemap()
    biome = world.TILE_TO_BIOME_NAME.get(tmap.tile_at(p.pos.x, p.pos.y)) if tmap is not None else None
    return [(f"{ctx.zone}: tile ({int(p.pos.x // TILE)}, {int(p.pos.y // TILE)}), px ({p.pos.x:.0f}, {p.pos.y:.0f})"
             + (f", {biome}" if biome else ""), INFO)]


@command("danger", "/danger", "the danger tier where you stand and what it does to monsters here", "debug")
def _cmd_danger(ctx, args):
    from game import danger
    sim = ctx.need_sim()
    f = sim.danger_at(ctx.player.pos) if hasattr(sim, "danger_at") else None
    if f is None:
        return [("No danger scale here (dungeon, ocean or a big island - those have their own scaling).", INFO)]
    name, col, tier = danger.label(f)
    m = danger.mults(f)
    return [(f"Danger here: {name} (tier {tier}/5, {f:.2f} of the way to the centre)", col),
            (f"  mobs: HP x{m['hp']:.2f}  dmg x{m['dmg']:.2f}  speed x{m['speed']:.2f}  attacks x{1 / m['cd']:.2f}"
             f"  aggro x{m['aggro']:.2f}", INFO),
            (f"  rewards: XP x{m['xp']:.2f}  extra loot {int(m['loot_extra'] * 100)}%  shard {int(m['portal'] * 100)}%",
             INFO)]


@command("seed", "/seed [n]", "show or set the random seed (reproduce a fight / a drop)", "debug")
def _cmd_seed(ctx, args):
    if not args:
        return [("Random state is live. /seed <n> to make the next rolls repeatable.", INFO)]
    n = _int(args[0], name="seed")
    random.seed(n)
    return [(f"random.seed({n})", GOOD)]


@command("stats", "/stats", "everything about your character (stats, gear, buffs, flags)", "debug",
         aliases=("me", "info"))
def _cmd_stats(ctx, args):
    p = ctx.player
    lines = [(f"{p.name} - level {p.level} {p.cls_name}, XP {p.xp}", HEAD),
             (f"HP {p.hp:.0f}/{p.hp_max}  MP {p.mp:.0f}/{p.mp_max}", INFO),
             ("  ".join(f"{k.upper()} {getattr(p, k)} ({p.total_stat(k)})" for k in ("att", "deF", "spd", "dex",
                                                                                     "vit", "wis")), INFO)]
    for slot in ("weapon", "armor", "ring", "ability"):
        it = getattr(p, slot)
        lines.append((f"{slot}: {it.display_name if it else '-'}", INFO))
    lines.append((f"Bags: {len(p.backpack)}/{p.backpack_size} + {len(p.backpack2)}/{p.backpack2_size}, "
                  f"shards {sum(1 for r in p.rune_slots if r)}", INFO))
    lines.append((f"Flags: god {_on_off(getattr(p, 'god', False))}, noclip {_on_off(getattr(p, 'noclip', False))}, "
                  f"speed x{getattr(p, 'admin_speed', 1.0):g}", INFO))
    if p.temp_buffs:
        lines.append(("Buffs: " + ", ".join(f"{k} +{a} ({t:.0f}s)" for k, (a, t) in p.temp_buffs.items()), INFO))
    return Panel("/stats", lines)


ADMIN_ENV = "RR_ADMIN"


def server_admin_default():
    return os.environ.get(ADMIN_ENV, "") not in ("", "0", "false", "no")



@command("forecast", "/forecast [reroll | blood <n> | calm]",
         "the coming nights (as the Calendar, K, shows them); reroll them, make night n a Blood Moon, or none",
         "night", aliases=("calendar", "fc"))
def _cmd_forecast(ctx, args):
    from game import realm_sim as rs
    sim = ctx.need_realm()
    sim._ensure_forecast()
    sub = args[0].lower() if args else ""
    if sub == "reroll":
        sim.reroll_forecast()
    elif sub in ("blood", "bloodmoon", "bm"):
        n = _int(args[1], 1, rs.FORECAST_NIGHTS, "night") if len(args) > 1 else 1
        sim.forecast[n - 1]["u_blood"] = -1.0  # always under the chance
    elif sub == "calm":
        for e in sim.forecast:
            e["u_blood"] = 2.0  # never under the chance
    elif sub:
        raise _Usage("/forecast [reroll | blood <n> | calm]")
    out = [("The coming nights:", HEAD)]
    for i, f in enumerate(sim.forecast_view()):
        m, sec = divmod(int(f["eta"]), 60)
        what = "BLOOD MOON" if f["blood"] else f"{f['weather']}, {f['label']}"
        out.append((f"  {i + 1}. night {f['n']} in {m}:{sec:02d} - {f['moon']} - {what}", BAD if f["blood"] else INFO))
    return out

"""
Realm Reforged co-op server.

Authoritative host for a shared Nexus / Bazaar / Realm / Bonus-room session.
Run this once (on whichever machine will host), then have every player -
including you - run `coop_client.py --host <server-ip>` to join.

No auth, no encryption: this is a LAN/trusted-friend protocol, not a
hardened multiplayer backend. Movement is client-trusted (the server does
not re-simulate physics per client); everything that actually matters for
fairness - enemy HP, damage rolls, loot rolls, XP - is authoritative here.

Usage:
    python server.py [--host 0.0.0.0] [--port 50777]
"""
import argparse
import random
import socket
import threading
import time
import uuid

import pygame  # for Vector2 math only - no display/audio subsystem is touched

from game import constants as C
from game import world
from game import accounts
from game import characters
from game import story
from game import vault
from game import dialogue
from game import npcs
from game import live_events
from game import codex
from game import sidequests
from game.entities import (Player, Bag, Portal, NexusBot, find_nearby_bag, bag_by_id,
                            withdraw_from_bag, BazaarChest, deposit_to_bag, spawn_bazaar_chests)
from game.realm_sim import RealmSim, DUNGEON_THEMES, BONUS_DIFFICULTIES, FORGE_DIFFICULTY, audible_mob_speech
from game.items import (load_vault, save_vault, VAULT_SLOTS, VAULT_CHEST_SIZE, VAULT_CHEST_COUNT,
                         wish_fountain, apply_socket, PET_KINDS)
from game.netmsg import send_msg, MessageReader

FIRE_BUFFER_WINDOW = 0.1  # seconds - an early "fire" input within this window of the weapon's
# cooldown clearing still fires, instead of being silently dropped (see _maybe_fire) - matches
# main.py's identical single-player constant
AUTOSAVE_INTERVAL = 60.0  # seconds between background character-progress saves for
# every live (non-dead) session - same rationale/cadence as main.py's single-player
# autosave: covers long stretches between natural checkpoints so a server crash or
# ungraceful disconnect doesn't lose much progress

ZONE_NEXUS, ZONE_BAZAAR, ZONE_VAULT_ROOM, ZONE_REALM, ZONE_BONUS, ZONE_DEAD = (
    "nexus", "bazaar", "vault_room", "realm", "bonus", "dead")


class Session:
    def __init__(self, pid, sock, player):
        self.pid = pid
        self.sock = sock
        self.player = player
        self.zone = ZONE_NEXUS
        self.last_input = {"move": [0.0, 0.0], "aim": [0.0, 0.0], "fire": False}
        self.fire_buffer = 0.0  # seconds left to auto-fire an early "fire" input that arrived
        # just before the weapon's cooldown cleared - see _maybe_fire / FIRE_BUFFER_WINDOW
        self.pre_bonus_pos = None
        self.story_feed = []  # [(msg, color)] story lines for this player's next snapshot (any zone)
        self.story_banners = []  # completed-act titles for this player's next snapshot
        self.given_heard = set()  # acts whose intro Father Given already told this session
        self.bonus_from_nexus = False  # in the Forge (entered from the Nexus) - leaving returns there
        self.portal_prompt = None  # (theme, kind, difficulty, portal_id) while standing on/near a portal
        # this tick, or None - refreshed every tick in step(), consumed only by an explicit "enter_portal"
        # action (see _apply_action) - entering is a deliberate key press, not an automatic walk-over.
        # portal_id (the touched Portal object's own .id) is what lets multiple players who touch the
        # SAME physical portal land in the SAME dungeon instance - see ServerState.portal_instance_map.
        self.death_info = None
        self.vault_items = []
        self.vault_chest = 0  # which of the VAULT_CHEST_COUNT chests this session is currently
        # viewing (set by "open_vault") - a plain-click deposit fills THIS chest specifically
        self.sent_map_id = None  # id() of the last RealmSim whose map we've already sent this session
        self.alive_conn = True
        self.trade_id = None  # key into ServerState.trades, or None
        self.conversation = None  # dialogue.Conversation while talking to an NPC, else None
        self.conversation_zone = None
        self.bonus_sim_id = None  # key into ServerState.bonus_sims - which of possibly SEVERAL
        # concurrently-active co-op dungeon instances this session is currently in, or None if not
        # in ZONE_BONUS. Multiple instances exist so two players opening differently-themed (or even
        # same-themed but separately-dropped) dungeon-shard portals each get their own real dungeon
        # instead of being silently forced into whichever one happened to be created first.


# RotMG-style trade window: a request is only an INVITE until the other player
# accepts it (see ServerState.trade_invites); then both sides offer items, both hit
# accept, and only after a short anti-scam confirmation countdown (any change resets
# it) does the swap actually happen - see step()'s trade-tick block and
# _apply_action's trade_* branches. Offered items never leave the backpack until the
# swap itself (offers are references to backpack Items), so a cancel, a disconnect
# or a mid-trade pickup can never lose anything.
TRADE_RANGE = 110
BOT_TALK_RADIUS = 55  # matches main.py's Game.BOT_TALK_RADIUS
TRADE_CONFIRM_SECONDS = 3.0
TRADE_IDLE_TIMEOUT = 90.0
TRADE_MAX_ITEMS = 8
TRADE_INVITE_SECONDS = 20.0


class Trade:
    def __init__(self, trade_id, a_pid, b_pid):
        self.id = trade_id
        self.a_pid = a_pid
        self.b_pid = b_pid
        self.offer_a = []
        self.offer_b = []
        self.accept_a = False
        self.accept_b = False
        self.confirm_timer = None
        self.idle_time = 0.0
        self.status = None  # visible reason the swap didn't go through (e.g. a full backpack)

    def other(self, pid):
        return self.b_pid if pid == self.a_pid else self.a_pid

    def offer_of(self, pid):
        return self.offer_a if pid == self.a_pid else self.offer_b

    def set_accept(self, pid, value):
        if pid == self.a_pid:
            self.accept_a = value
        else:
            self.accept_b = value

    def reset_accept(self):
        self.accept_a = False
        self.accept_b = False
        self.confirm_timer = None


class ServerState:
    def __init__(self):
        self.lock = threading.Lock()
        self.nexus_map = world.TileMap(world.make_nexus())
        self.bazaar_map = world.TileMap(world.make_bazaar())
        self.vault_room_map = world.TileMap(world.make_vault_room())
        self.realm_sim = RealmSim(bonus=False)
        self.bonus_sims = {}          # bonus_sim_id -> RealmSim, one per concurrently-active
        # co-op dungeon instance (see Session.bonus_sim_id) - was a single shared `bonus_sim`
        # before, which silently forced every player entering ANY dungeon-shard portal into
        # whichever ONE instance happened to exist, even a totally different theme.
        self._next_bonus_sim_id = 1
        self.portal_instance_map = {}  # dungeon-shard Portal.id -> bonus_sim_id, so players who
        # touch the SAME physical portal join the SAME instance instead of each getting their own -
        # pruned in step() whenever the instance it points to is cleaned up
        self.sessions = {}  # pid -> Session
        self.pending_actions = []  # [(pid, action_dict), ...]
        self.bazaar_ground_items = spawn_bazaar_chests()  # permanent chests + whatever players dropped
        self.chat_queue = []  # [(pid, zone, text), ...] - broadcast to same-zone snapshots this tick, then cleared
        self.trades = {}  # trade_id -> Trade
        self.trade_invites = {}  # target pid -> {"from": requester pid, "t": seconds left}
        self._next_trade_id = 1
        self.nexus_bot = NexusBot(self.nexus_map.center_world_pos())
        self.nexus_npcs = npcs.spawn_nexus_npcs(self.nexus_map)  # Batch 15 friendly NPCs
        self.autosave_cd = AUTOSAVE_INTERVAL  # see step()'s periodic character-progress save


def _nexus_spawn_pos(state):
    # a couple tiles off the exact center, which is where the Realm portal tile
    # sits - the client auto-triggers goto_realm just by standing on that tile
    # (see coop_client.py), so spawning exactly on it would bounce a player
    # straight back into the Realm before they ever see the Nexus
    c = state.nexus_map.center_world_pos()
    return pygame.Vector2(c.x, c.y + C.TILE * 2)


def _vault_room_spawn_pos(state):
    c = state.vault_room_map.center_world_pos()
    return pygame.Vector2(c.x, c.y + C.TILE * 4)


def _vault_room_chest_index(state, pos):
    """Chests are numbered in row-major grid order, matching make_vault_room()'s
    layout - mirrors main.py's identical single-player helper exactly, so a
    given chest tile always maps to the same vault "page" in both modes."""
    grid = state.vault_room_map.grid
    tx, ty = int(pos.x // C.TILE), int(pos.y // C.TILE)
    idx = 0
    for y in range(len(grid)):
        for x in range(len(grid[0])):
            if grid[y][x] == world.CHEST:
                if (x, y) == (tx, ty):
                    return idx
                idx += 1
    return 0


def _bag_list_for_zone(state, s):
    """The ground-Bag list backing session `s`'s current zone - None for zones with no
    ground loot at all (Nexus, Vault room, Dead). Takes the session (not just the zone
    string) because ZONE_BONUS now needs to know WHICH of possibly several concurrent
    dungeon instances this specific session is in."""
    if s.zone == ZONE_REALM:
        return state.realm_sim.ground_items
    if s.zone == ZONE_BONUS:
        bsim = state.bonus_sims.get(s.bonus_sim_id)
        return bsim.ground_items if bsim is not None else None
    if s.zone == ZONE_BAZAAR:
        return state.bazaar_ground_items
    return None


def _realm_players(state):
    return {s.pid: s.player for s in state.sessions.values() if s.zone == ZONE_REALM}


def _bonus_players(state, bonus_sim_id):
    return {s.pid: s.player for s in state.sessions.values()
            if s.zone == ZONE_BONUS and s.bonus_sim_id == bonus_sim_id}


def _pet_result(s, p):
    """Sends the feed/pack/fuse/hatch result Player left in pet_msg (see
    entities.Player.feed_pet/pack_pet) to that player's client, plus whether it
    was a fusion so the client can play the burst."""
    if s is None or not p.pet_msg:
        return
    text, color = p.pet_msg
    fused, p.pet_msg, p.pet_fused = p.pet_fused, None, False
    try:
        send_msg(s.sock, {"type": "pet_result", "message": text, "color": list(color), "fused": fused})
    except OSError:
        pass


def _trade_notice(s, message):
    if s is not None:
        try:
            send_msg(s.sock, {"type": "trade_notice", "message": message})
        except OSError:
            pass


def _cancel_trade(state, trade, reason=None):
    """Tears the trade down - nothing to refund, offered items never left their
    owner's backpack (see Trade / trade_offer)."""
    for pid in (trade.a_pid, trade.b_pid):
        s = state.sessions.get(pid)
        if s is None:
            continue
        s.trade_id = None
        if reason:
            _trade_notice(s, reason)
    state.trades.pop(trade.id, None)


def _in_backpack(p, it):
    return any(b is it for b in p.backpack)


def _prune_offer(p, offer):
    """Drops offer entries whose Item is no longer in the backpack (equipped, dropped,
    used, ...). Returns True if anything was removed."""
    kept = [it for it in offer if _in_backpack(p, it)]
    if len(kept) == len(offer):
        return False
    offer[:] = kept
    return True


def _execute_trade(state, trade):
    sa, sb = state.sessions.get(trade.a_pid), state.sessions.get(trade.b_pid)
    if sa is None or sb is None:
        _cancel_trade(state, trade)
        return
    pa, pb = sa.player, sb.player
    if _prune_offer(pa, trade.offer_a) | _prune_offer(pb, trade.offer_b):
        trade.reset_accept()
        trade.status = "An offered item moved - check the offers and accept again"
        return
    for p, give, get in ((pa, trade.offer_a, trade.offer_b), (pb, trade.offer_b, trade.offer_a)):
        if len(p.backpack) - len(give) + len(get) > p.backpack_size:
            trade.reset_accept()
            trade.status = f"{p.name}'s backpack is too full"
            return
    for p, give in ((pa, trade.offer_a), (pb, trade.offer_b)):
        p.backpack[:] = [bp for bp in p.backpack if not any(bp is it for it in give)]
    pa.backpack.extend(trade.offer_b)
    pb.backpack.extend(trade.offer_a)
    sa.trade_id = None
    sb.trade_id = None
    state.trades.pop(trade.id, None)
    state.chat_queue.append((None, sa.zone, f"[Trade complete between {pa.name} and {pb.name}]"))


def _can_trade_together(a, b):
    return (a is not None and b is not None and a.zone == b.zone and a.zone != ZONE_DEAD
            and a.player.alive and b.player.alive
            and a.player.pos.distance_to(b.player.pos) <= TRADE_RANGE * 2.5)


def _open_trade(state, a, b):
    state.trade_invites.pop(a.pid, None)
    state.trade_invites.pop(b.pid, None)
    trade_id = state._next_trade_id
    state._next_trade_id += 1
    state.trades[trade_id] = Trade(trade_id, a.pid, b.pid)
    a.trade_id = trade_id
    b.trade_id = trade_id
    state.chat_queue.append((None, a.zone, f"[{a.player.name} and {b.player.name} are trading]"))


def _tick_trade_invites(state, dt):
    for target_pid, inv in list(state.trade_invites.items()):
        target, sender = state.sessions.get(target_pid), state.sessions.get(inv["from"])
        inv["t"] -= dt
        if sender is None or target is None:
            state.trade_invites.pop(target_pid, None)
            _trade_notice(sender, "Trade request cancelled - they left")
        elif inv["t"] <= 0:
            state.trade_invites.pop(target_pid, None)
            _trade_notice(sender, f"Trade request to {target.player.name} expired")
        elif not _can_trade_together(sender, target) or sender.trade_id is not None or target.trade_id is not None:
            state.trade_invites.pop(target_pid, None)
            _trade_notice(sender, f"Trade request to {target.player.name} cancelled")


def _tick_trades(state, dt):
    _tick_trade_invites(state, dt)
    for trade in list(state.trades.values()):
        sa, sb = state.sessions.get(trade.a_pid), state.sessions.get(trade.b_pid)
        if sa is None or sb is None:
            _cancel_trade(state, trade, "Trade cancelled - the other player left")
            continue
        if not _can_trade_together(sa, sb):
            _cancel_trade(state, trade, "Trade cancelled - too far apart")
            continue
        trade.idle_time += dt
        if trade.idle_time > TRADE_IDLE_TIMEOUT:
            _cancel_trade(state, trade, "Trade cancelled - idle too long")
            continue
        if _prune_offer(sa.player, trade.offer_a) | _prune_offer(sb.player, trade.offer_b):
            trade.reset_accept()
        if trade.accept_a and trade.accept_b:
            if trade.confirm_timer is None:
                trade.confirm_timer = TRADE_CONFIRM_SECONDS
            trade.confirm_timer -= dt
            if trade.confirm_timer <= 0:
                _execute_trade(state, trade)
        else:
            trade.confirm_timer = None


def _story_event(s, kind, key=None):
    s.story_feed.extend(s.player.story.on_event(kind, key))


def _drain_story(state):
    """Act checkpoints for every session: bank newly completed acts on the account
    right away and queue the banner for the client (see game/story.py)."""
    for s in state.sessions.values():
        progress = s.player.story
        if not progress.just_completed:
            continue
        for act_idx in progress.just_completed:
            accounts.set_story_act(s.player.name, act_idx + 1)
            s.story_banners.append(story.ACTS[act_idx]["title"])
        progress.just_completed = []
        if s.player.alive:
            characters.save_character(s.player.name, s.player)


def _fresh_story(name):
    return story.StoryProgress(accounts.get_story_act(name))


def _enter_forge(state, s):
    """Father Given's finale portal - a private Forge instance for this player."""
    bsim_id = state._next_bonus_sim_id
    state._next_bonus_sim_id += 1
    state.bonus_sims[bsim_id] = RealmSim(bonus=True, theme="forge", difficulty_name=FORGE_DIFFICULTY,
                                         story_act=s.player.story.act)
    s.pre_bonus_pos = None
    s.bonus_from_nexus = True
    s.player.pos = state.bonus_sims[bsim_id].spawn_point()
    s.zone = ZONE_BONUS
    s.bonus_sim_id = bsim_id
    s.story_feed.append(("Father Given snaps his fingers. The floor is suddenly a portal. Rude.", (255, 200, 120)))


def step(state, dt):
    # reset per-tick event/popup lists BEFORE processing actions - see
    # RealmSim.begin_tick()'s docstring for why this can't happen inside update()
    state.realm_sim.begin_tick()
    for bsim in state.bonus_sims.values():
        bsim.begin_tick()

    # 1) discrete actions (equip, zone changes, vault ops, respawn) first
    actions, state.pending_actions = state.pending_actions, []
    for pid, action in actions:
        s = state.sessions.get(pid)
        if s is not None:
            _apply_action(state, s, action)

    # 2) continuous movement + firing input, per current zone
    for s in state.sessions.values():
        if s.zone == ZONE_DEAD:
            continue
        move = pygame.Vector2(s.last_input.get("move", [0, 0]))
        if s.zone in (ZONE_NEXUS, ZONE_BAZAAR, ZONE_VAULT_ROOM) and s.player.pet is not None:
            # hubs have no RealmSim.tick_pets - without this the pet stayed frozen where the
            # player left the Realm (usually off-screen); no enemies, so only follow + heal/mana
            s.player.pet.update(dt, s.player, [], [])
        if s.zone == ZONE_NEXUS:
            s.player.net_update(dt, move, state.nexus_map.bounds(), state.nexus_map.is_solid,
                                 state.nexus_map.speed_multiplier)
        elif s.zone == ZONE_BAZAAR:
            s.player.net_update(dt, move, state.bazaar_map.bounds(), state.bazaar_map.is_solid,
                                 state.bazaar_map.speed_multiplier)
        elif s.zone == ZONE_VAULT_ROOM:
            s.player.net_update(dt, move, state.vault_room_map.bounds(), state.vault_room_map.is_solid,
                                 state.vault_room_map.speed_multiplier)
        elif s.zone == ZONE_REALM:
            s.player.net_update(dt, move, state.realm_sim.realm_map.bounds(), state.realm_sim.is_solid_at,
                                 state.realm_sim.realm_map.speed_multiplier)
            if s.last_input.get("dash"):
                s.player.try_dash()
            _maybe_fire(state, state.realm_sim, s, dt)
        elif s.zone == ZONE_BONUS:
            bsim = state.bonus_sims.get(s.bonus_sim_id)
            if bsim is not None:
                s.player.net_update(dt, move, bsim.realm_map.bounds(), bsim.is_solid_at,
                                     bsim.realm_map.speed_multiplier)
                if s.last_input.get("dash"):
                    s.player.try_dash()
                _maybe_fire(state, bsim, s, dt)

    # 3) tick the realm sim plus EVERY currently-active dungeon instance (there can be
    # several at once now - each themed/separately-dropped dungeon-shard portal gets
    # its own, see ServerState.bonus_sims)
    state.realm_sim.update(dt, _realm_players(state))
    for bsim_id, bsim in state.bonus_sims.items():
        bsim.update(dt, _bonus_players(state, bsim_id))

    # the Bazaar has no combat, just item drops decaying / being opened+dragged-from by
    # anyone there - same open-a-bag-window model as Realm/Bonus now, no more auto-pickup
    # by walking over one
    state.bazaar_ground_items = [g for g in state.bazaar_ground_items if g.update(dt)]

    # 4) portal proximity just refreshes each session's prompt (shown client-side as
    # "press ENTER") - it no longer auto-transitions on walk-over. The actual zone
    # change happens in _apply_action's "enter_portal" handler, only on that key press.
    realm_prompts = {pid: (theme, kind, diff, pt_id, target_pos)
                      for pid, theme, kind, diff, pt_id, target_pos in state.realm_sim.portal_entries}
    for s in state.sessions.values():
        if s.zone == ZONE_REALM:
            s.portal_prompt = realm_prompts.get(s.pid)
    for bsim_id, bsim in state.bonus_sims.items():
        bonus_prompts = {pid: (theme, kind, diff, pt_id, target_pos)
                          for pid, theme, kind, diff, pt_id, target_pos in bsim.portal_entries}
        for s in state.sessions.values():
            if s.zone == ZONE_BONUS and s.bonus_sim_id == bsim_id:
                s.portal_prompt = bonus_prompts.get(s.pid)

    # drop each dungeon instance once nobody's left in it specifically (not just
    # "nobody's in ANY dungeon anymore" - other instances may still have players)
    occupied_ids = {s.bonus_sim_id for s in state.sessions.values() if s.zone == ZONE_BONUS}
    empty_ids = [bsim_id for bsim_id in state.bonus_sims if bsim_id not in occupied_ids]
    for bsim_id in empty_ids:
        del state.bonus_sims[bsim_id]
    if empty_ids:
        # prune the now-stale portal->instance mappings too, so a long-running server
        # doesn't slowly accumulate dead entries pointing at instances that no longer exist
        stale_portals = [pt_id for pt_id, bsim_id in state.portal_instance_map.items() if bsim_id in empty_ids]
        for pt_id in stale_portals:
            del state.portal_instance_map[pt_id]

    # 5) deaths - permadeath, same as single-player
    for s in state.sessions.values():
        if s.zone in (ZONE_REALM, ZONE_BONUS) and not s.player.alive:
            earned = accounts.award_echoes_for_death(s.player.name, s.player._echoes_this_life)
            s.death_info = dict(level=s.player.level, kills=s.player.kills, cls=s.player.cls_name,
                                 earned_echoes=earned)
            s.zone = ZONE_DEAD
            # the saved character (if any) is gone for good, same as single-player's
            # die() - the next join/respawn starts completely fresh, not a corpse
            characters.delete_character(s.player.name)

    # 5b) periodic character-progress autosave - covers long stretches between
    # natural checkpoints (join/disconnect/death) so a server crash doesn't lose much
    state.autosave_cd -= dt
    if state.autosave_cd <= 0:
        state.autosave_cd = AUTOSAVE_INTERVAL
        for s in state.sessions.values():
            if s.zone != ZONE_DEAD and s.player.alive:
                characters.save_character(s.player.name, s.player)

    # 5c) story act checkpoints (see game/story.py)
    _drain_story(state)

    # 6) trade windows - confirmation countdown, idle/out-of-range/death auto-cancel
    _tick_trades(state, dt)

    # 6b) Batch 15: Nexus NPCs, side-quest lines raised on the Player, stale conversations
    for n in state.nexus_npcs:
        n.update(dt, state.nexus_map.is_solid)
    for s in state.sessions.values():
        if s.player.quest_msgs:
            s.story_feed.extend(s.player.quest_msgs)
            s.player.quest_msgs = []
        if s.conversation is not None and s.zone != s.conversation_zone:
            s.conversation = None

    # 7) the wandering Nexus NPC - ticks even with nobody there, cheap and simple
    nexus_players = [s.player for s in state.sessions.values() if s.zone == ZONE_NEXUS]
    nearest = min((p.pos.distance_to(state.nexus_bot.pos) for p in nexus_players), default=None)
    state.nexus_bot.update(dt, state.nexus_map, nearest)


def _send_dialogue(s):
    conv = s.conversation
    view = conv.view() if conv is not None else None
    if conv is not None:
        s.story_feed.extend(conv.msgs)
        conv.msgs = []
        if view is None:
            s.conversation = None
    send_msg(s.sock, {"type": "dialogue", "view": view})


def _npcs_for_session(state, s):
    if s.zone == ZONE_NEXUS:
        return state.nexus_npcs
    if s.zone == ZONE_REALM:
        return state.realm_sim.npcs
    return []


def _try_talk(state, s):
    """F next to a friendly NPC / ambient wildlife: opens a conversation (True)."""
    p = s.player
    npc = npcs.nearest_npc(_npcs_for_session(state, s), p.pos)
    wild = None
    if npc is None and s.zone in (ZONE_REALM, ZONE_BONUS):
        sim = state.realm_sim if s.zone == ZONE_REALM else state.bonus_sims.get(s.bonus_sim_id)
        wild = npcs.nearest_wildlife(sim.enemies, p.pos) if sim is not None else None
    if npc is None and wild is None:
        return False
    s.conversation = dialogue.start_conversation(p, npc=npc, wildlife=wild)
    s.conversation_zone = s.zone
    _send_dialogue(s)
    return True


def _maybe_fire(state, sim, s, dt):
    wants_fire = bool(s.last_input.get("fire"))
    if wants_fire:
        s.fire_buffer = FIRE_BUFFER_WINDOW
    elif s.fire_buffer > 0:
        s.fire_buffer = max(0.0, s.fire_buffer - dt)
    # no weapon equipped (dragged onto the ground) - RealmSim.player_fire would
    # dereference None and take the whole co-op server down with it
    if s.fire_buffer > 0 and s.player.can_fire() and s.player.weapon is not None:
        s.fire_buffer = 0.0
        aim = pygame.Vector2(s.last_input.get("aim", [0, 1]))
        if aim.length_squared() < 1e-6:
            aim = pygame.Vector2(s.player.facing)
        s.player.register_fire()
        sim.player_fire(s.player, aim.normalize())


def _apply_action(state, s, action):
    kind = action.get("action")
    p = s.player
    if kind == "equip":
        idx = action.get("idx", -1)
        if 0 <= idx < len(p.backpack):
            it = p.backpack[idx]
            if it.slot in ("consumable", "temp_potion", "egg"):
                had_pet = p.pet is not None
                if p.use_potion(idx) and it.slot == "egg":
                    verb = "is back out" if it.pet_state else "hatched"
                    p.pet_msg = (f"{PET_KINDS.get(it.pet_kind, {}).get('name', it.name)} {verb}!"
                                 + (" (your old pet went into a carrier)" if had_pet else ""), (170, 220, 255))
                    _pet_result(s, p)
            elif it.slot == "shard" and s.zone == ZONE_REALM:
                theme_name = p.use_shard(idx)
                if theme_name is not None:
                    theme_label = DUNGEON_THEMES.get(theme_name, DUNGEON_THEMES["generic"])["label"]
                    # rolled NOW (not on arrival) so the difficulty can be shown as a
                    # label on the portal itself before anyone steps through it
                    diff_name = random.choices(BONUS_DIFFICULTIES,
                                                weights=[d["weight"] for d in BONUS_DIFFICULTIES])[0]["name"]
                    state.realm_sim.portals.append(Portal(p.pos, theme=theme_name, kind="dungeon_shard",
                                                           difficulty=diff_name))
                    state.chat_queue.append((None, s.zone,
                                              f"[A {diff_name} portal to the {theme_label} tears open!]"))
            elif it.slot == action.get("slot", it.slot):
                p.backpack.pop(idx)
                p.equip(it, backpack_idx=idx)
    elif kind == "feed_pet":
        idx = action.get("idx", -1)
        p.feed_pet(idx)
        _pet_result(s, p)
    elif kind == "pack_pet":
        p.pack_pet()
        _pet_result(s, p)
    elif kind == "unequip":
        p.unequip(action.get("slot", ""))
    elif kind == "swap_backpack":
        p.swap_backpack(action.get("i", -1), action.get("j", -1))
    elif kind == "socket_proc":
        idx, target_idx = action.get("idx", -1), action.get("target_idx", -1)
        if 0 <= idx < len(p.backpack) and 0 <= target_idx < len(p.backpack) and idx != target_idx:
            ok, msg = apply_socket(p.backpack[idx], p.backpack[target_idx])
            if ok:
                p.backpack.pop(idx)
            send_msg(s.sock, {"type": "socket_result", "ok": ok, "message": msg})
    elif kind == "open_bag":
        # right-click: find the nearest bag in range and send its full contents back -
        # opening a drag-and-drop window client-side, not an instant grab (see the
        # analogous "vault_state" flow for the Vault)
        bags = _bag_list_for_zone(state, s)
        if bags is not None:
            bag = find_nearby_bag(bags, p.pos, p.pid)
            if bag is not None:
                send_msg(s.sock, {"type": "bag_state", "id": bag.id,
                                   "items": [it.to_json() for it in bag.items]})
    elif kind == "bag_withdraw":
        bags = _bag_list_for_zone(state, s)
        if bags is not None:
            bag_id, idx = action.get("bag_id", -1), action.get("idx", -1)
            target_idx = action.get("target_idx")
            bag = bag_by_id(bags, bag_id)
            item = withdraw_from_bag(bags, bag_id, idx, p, target_idx=target_idx)
            if item is not None:
                send_msg(s.sock, {"type": "bag_state", "id": bag_id,
                                   "items": [it.to_json() for it in bag.items] if bag.items else []})
    elif kind == "chest_deposit":
        # only a BazaarChest can receive deposits - see deposit_to_bag's own
        # docstring for why this isn't just folded into bag_withdraw's shape
        bags = _bag_list_for_zone(state, s)
        if bags is not None:
            bag_id, source_idx = action.get("bag_id", -1), action.get("idx", -1)
            bag = bag_by_id(bags, bag_id)
            if isinstance(bag, BazaarChest):
                item = deposit_to_bag(bags, bag_id, source_idx, p)
                if item is not None:
                    send_msg(s.sock, {"type": "bag_state", "id": bag_id,
                                       "items": [it.to_json() for it in bag.items]})
    elif kind == "use_ability" and s.zone in (ZONE_REALM, ZONE_BONUS):
        sim = state.realm_sim if s.zone == ZONE_REALM else state.bonus_sims.get(s.bonus_sim_id)
        if sim is not None:
            target = pygame.Vector2(action.get("target", [p.pos.x, p.pos.y]))
            # for ZONE_BONUS, "allies" must be scoped to the SAME dungeon instance -
            # with several concurrent instances now possible, a bare zone match would
            # incorrectly heal/haste players in a totally different dungeon
            allies = [o.player for o in state.sessions.values()
                      if o.zone == s.zone and (s.zone != ZONE_BONUS or o.bonus_sim_id == s.bonus_sim_id)]
            sim.use_ability(p, target, allies)
    elif kind == "drop_item" and s.zone in (ZONE_REALM, ZONE_BONUS, ZONE_BAZAAR):
        slot = action.get("slot")
        item = None
        if slot:
            item = getattr(p, slot, None)
            if item is not None:
                setattr(p, slot, None)
        else:
            idx = action.get("idx", -1)
            if 0 <= idx < len(p.backpack):
                item = p.backpack.pop(idx)
        if item is not None:
            rarity_key = "white" if item.is_ut else "purple" if (item.tier or 0) >= 7 else "brown"
            g = Bag([item], p.pos, dropped_by=p.pid, rarity_key=rarity_key)
            bags = _bag_list_for_zone(state, s)
            if bags is not None:
                bags.append(g)
    elif kind == "goto_realm" and s.zone == ZONE_NEXUS:
        if state.nexus_map.tile_at(p.pos.x, p.pos.y) == world.PORTAL:
            s.zone = ZONE_REALM
            p.pos = state.realm_sim.spawn_point()
            _story_event(s, "zone", "realm")
    elif kind == "goto_bazaar" and s.zone == ZONE_NEXUS:
        if state.nexus_map.tile_at(p.pos.x, p.pos.y) == world.BAZAAR_PORTAL:
            s.zone = ZONE_BAZAAR
            p.pos = state.bazaar_map.center_world_pos()
    elif kind == "goto_nexus" and s.zone in (ZONE_REALM, ZONE_BAZAAR, ZONE_VAULT_ROOM, ZONE_BONUS):
        s.bonus_from_nexus = False
        s.zone = ZONE_NEXUS
        p.pos = _nexus_spawn_pos(state)
    elif kind == "goto_vault_room" and s.zone == ZONE_NEXUS:
        if state.nexus_map.tile_at(p.pos.x, p.pos.y) == world.VAULT_TILE:
            s.zone = ZONE_VAULT_ROOM
            p.pos = _vault_room_spawn_pos(state)
            # fill counts for the 12 chests (chest=None: nothing opens yet)
            s.vault_items = load_vault(p.name)
            send_msg(s.sock, {"type": "vault_state", "chest": None,
                               "items": [(it.to_json() if it is not None else None) for it in s.vault_items]})
    elif kind == "leave_bonus" and s.zone == ZONE_BONUS:
        s.zone = ZONE_REALM
        p.pos = s.pre_bonus_pos or state.realm_sim.spawn_point()
    elif kind == "open_vault" and s.zone == ZONE_VAULT_ROOM:
        # F/Enter next to one of the 12 vault-room chests opens THAT chest (game/vault.py)
        near = vault.nearest_chest(state.vault_room_map, p.pos)
        if near is not None:
            chest_idx = near[0]
            s.vault_items = load_vault(p.name)
            s.vault_chest = chest_idx
            send_msg(s.sock, {"type": "vault_state",
                               "items": [(it.to_json() if it is not None else None) for it in s.vault_items],
                               "chest": chest_idx})
    elif kind == "vault_select_chest":
        s.vault_chest = max(0, min(VAULT_CHEST_COUNT - 1, action.get("chest", 0)))
    elif kind == "vault_deposit":
        # each chest is real, independent 8-slot storage (see items.load_vault) - a
        # plain deposit (no target_idx) fills the first empty slot of the session's
        # CURRENTLY VIEWED chest specifically; a target_idx (dragged onto a
        # specific, occupied vault slot) swaps instead of failing
        idx = action.get("idx", -1)
        target_idx = action.get("target_idx")
        if 0 <= idx < len(p.backpack):
            if target_idx is not None and 0 <= target_idx < len(s.vault_items):
                if s.vault_items[target_idx] is None:
                    s.vault_items[target_idx] = p.backpack.pop(idx)
                else:
                    p.backpack[idx], s.vault_items[target_idx] = s.vault_items[target_idx], p.backpack[idx]
                save_vault(p.name, s.vault_items)
                send_msg(s.sock, {"type": "vault_state",
                                   "items": [(it.to_json() if it is not None else None) for it in s.vault_items]})
            else:
                lo = s.vault_chest * VAULT_CHEST_SIZE
                slot = next((i for i in range(lo, lo + VAULT_CHEST_SIZE) if s.vault_items[i] is None), None)
                if slot is not None:
                    s.vault_items[slot] = p.backpack.pop(idx)
                    save_vault(p.name, s.vault_items)
                    send_msg(s.sock, {"type": "vault_state",
                                       "items": [(it.to_json() if it is not None else None)
                                                 for it in s.vault_items]})
    elif kind == "vault_withdraw":
        idx = action.get("idx", -1)
        target_idx = action.get("target_idx")
        if 0 <= idx < len(s.vault_items) and s.vault_items[idx] is not None:
            if target_idx is not None and 0 <= target_idx < len(p.backpack):
                p.backpack[target_idx], s.vault_items[idx] = s.vault_items[idx], p.backpack[target_idx]
                save_vault(p.name, s.vault_items)
                send_msg(s.sock, {"type": "vault_state",
                                   "items": [(it.to_json() if it is not None else None) for it in s.vault_items]})
            elif len(p.backpack) < p.backpack_size:
                p.backpack.append(s.vault_items[idx])
                s.vault_items[idx] = None
                save_vault(p.name, s.vault_items)
                send_msg(s.sock, {"type": "vault_state",
                                   "items": [(it.to_json() if it is not None else None) for it in s.vault_items]})
    elif kind == "trade_request":
        if s.trade_id is None:
            nearest, best = None, TRADE_RANGE
            wanted_pid = action.get("pid")
            for o in state.sessions.values():
                if o is s or o.zone != s.zone or o.trade_id is not None or not o.player.alive:
                    continue
                dist = o.player.pos.distance_to(p.pos)
                if dist > TRADE_RANGE:
                    continue
                # a right-click-a-specific-player trade request always wins over
                # "whoever's nearest" once that player is confirmed in range
                if o.pid == wanted_pid:
                    nearest = o
                    break
                if dist <= best:
                    nearest, best = o, dist
            if nearest is None:
                _trade_notice(s, "No nearby player to trade with")
            elif state.trade_invites.get(s.pid, {}).get("from") == nearest.pid:
                _open_trade(state, nearest, s)  # they already asked us - mutual, open now
            else:
                state.trade_invites[nearest.pid] = {"from": s.pid, "t": TRADE_INVITE_SECONDS}
                _trade_notice(s, f"Trade request sent to {nearest.player.name}")
    elif kind == "trade_invite_accept":
        inv = state.trade_invites.pop(s.pid, None)
        sender = state.sessions.get(inv["from"]) if inv else None
        if sender is None:
            _trade_notice(s, "No pending trade request")
        elif s.trade_id is None and sender.trade_id is None and _can_trade_together(sender, s):
            _open_trade(state, sender, s)
        else:
            _trade_notice(s, "That trade request is no longer valid")
            _trade_notice(sender, f"{p.name} couldn't accept your trade")
    elif kind == "trade_invite_decline":
        inv = state.trade_invites.pop(s.pid, None)
        if inv:
            _trade_notice(state.sessions.get(inv["from"]), f"{p.name} declined your trade")
    elif kind == "trade_offer":
        trade = state.trades.get(s.trade_id)
        if trade is not None:
            idx = action.get("idx", -1)
            offer = trade.offer_of(s.pid)
            if (0 <= idx < len(p.backpack) and len(offer) < TRADE_MAX_ITEMS
                    and not any(it is p.backpack[idx] for it in offer)):
                offer.append(p.backpack[idx])  # a reference - the item stays in the backpack
                trade.reset_accept()
                trade.status = None
                trade.idle_time = 0.0
    elif kind == "trade_withdraw":
        trade = state.trades.get(s.trade_id)
        if trade is not None:
            idx = action.get("idx", -1)
            offer = trade.offer_of(s.pid)
            if 0 <= idx < len(offer):
                offer.pop(idx)
                trade.reset_accept()
                trade.status = None
                trade.idle_time = 0.0
    elif kind == "trade_accept":
        trade = state.trades.get(s.trade_id)
        if trade is not None:
            trade.set_accept(s.pid, True)
            trade.status = None
            trade.idle_time = 0.0
    elif kind == "trade_cancel":
        trade = state.trades.get(s.trade_id)
        if trade is not None:
            _cancel_trade(state, trade, f"{p.name} cancelled the trade")
    elif kind == "enter_portal":
        # the actual zone transition a portal offers - only ever runs on this
        # explicit action (sent when the client's ENTER key press matches an
        # active prompt), never from mere proximity (see step()'s prompt refresh)
        if s.portal_prompt is None:
            return
        theme, pkind, difficulty, pt_id, target_pos = s.portal_prompt
        if pkind == "island_link":
            # a same-map teleport (see RealmSim._stamp_islands), not a dungeon-
            # instance swap - s.zone/s.bonus_sim_id untouched
            if target_pos is not None:
                s.player.pos = pygame.Vector2(target_pos)
            s.portal_prompt = None
            return
        if s.zone == ZONE_REALM:
            # each dungeon-shard portal gets its OWN instance, keyed by the specific
            # Portal object's own id - a second player who touches the SAME physical
            # portal joins the SAME instance (portal_instance_map already has it);
            # a player who opens a DIFFERENT portal (different theme, or even the
            # same theme from a separate kill) gets a genuinely separate dungeon,
            # instead of everyone silently sharing whichever one was created first.
            bsim_id = state.portal_instance_map.get(pt_id)
            if bsim_id is None or bsim_id not in state.bonus_sims:
                bsim_id = state._next_bonus_sim_id
                state._next_bonus_sim_id += 1
                state.bonus_sims[bsim_id] = RealmSim(bonus=True, theme=theme, difficulty_name=difficulty,
                                                     story_act=s.player.story.act)
                state.portal_instance_map[pt_id] = bsim_id
            s.pre_bonus_pos = pygame.Vector2(s.player.pos)
            s.player.pos = state.bonus_sims[bsim_id].spawn_point()
            s.zone = ZONE_BONUS
            s.bonus_sim_id = bsim_id
        elif s.zone == ZONE_BONUS and s.bonus_sim_id in state.bonus_sims:
            # phase-2 access is now a walked-through door (see world.open_phase2_door,
            # RealmSim._maybe_open_phase2_door) opened by its own quest, not a portal-
            # teleport kind - no special-case needed here anymore.
            s.bonus_sim_id = None
            if s.bonus_from_nexus:
                s.bonus_from_nexus = False
                s.zone = ZONE_NEXUS
                s.player.pos = _nexus_spawn_pos(state)
            else:
                s.zone = ZONE_REALM
                s.player.pos = s.pre_bonus_pos or state.realm_sim.spawn_point()
        s.portal_prompt = None
    elif kind == "tp_to_player":
        target = state.sessions.get(action.get("pid"))
        if target is not None and target.zone == s.zone and target.zone != ZONE_DEAD:
            offset = pygame.Vector2(random.uniform(-30, 30), random.uniform(-30, 30))
            p.pos = pygame.Vector2(target.player.pos) + offset
            state.chat_queue.append((None, s.zone, f"[{p.name} teleported to {target.player.name}]"))
    elif kind == "whisper":
        # /msg or /w: by pid, or by NAME across every session in every zone (Realm,
        # dungeons, Vault...) - a whisper isn't limited to who's on your screen
        target = state.sessions.get(action.get("pid"))
        wanted = str(action.get("name", "")).strip().lower()
        if target is None and wanted:
            target = next((o for o in state.sessions.values() if o.player.name.lower() == wanted), None)
        text = str(action.get("text", ""))[:1000].strip()
        if target is None and wanted:
            send_msg(s.sock, {"type": "whisper", "error": f"No player named '{action.get('name')}' is online"})
        elif target is s:
            send_msg(s.sock, {"type": "whisper", "error": "Talking to yourself? Bold."})
        elif target is not None and text:
            send_msg(target.sock, {"type": "whisper", "from": p.name, "text": text})
            send_msg(s.sock, {"type": "whisper", "from": p.name, "text": text,
                               "to": target.player.name, "echo": True})
    elif kind == "dialogue_choice":
        if s.conversation is not None:
            s.conversation.choose(int(action.get("idx", -1)))
            _send_dialogue(s)
    elif kind == "dialogue_close":
        if s.conversation is not None:
            s.conversation.bye()
            _send_dialogue(s)
    elif kind == "fish" and s.zone in (ZONE_REALM, ZONE_BONUS):
        sim = state.realm_sim if s.zone == ZONE_REALM else state.bonus_sims.get(s.bonus_sim_id)
        if _try_talk(state, s):
            pass
        elif sim is not None and sim.open_island_chest(p):
            pass
        elif sim is not None:
            sim.fish_action(p)  # feed messages ride the normal sim.events -> snapshot feed pipeline
    elif kind == "wish" and s.zone == ZONE_NEXUS and _try_talk(state, s):
        pass
    elif kind == "wish" and s.zone == ZONE_NEXUS:
        on_fountain = state.nexus_map.tile_at(p.pos.x, p.pos.y) == world.NEXUS_FOUNTAIN
        near_bot = p.pos.distance_to(state.nexus_bot.pos) <= BOT_TALK_RADIUS
        if not on_fountain and not near_bot:
            send_msg(s.sock, {"type": "wish_result",
                               "error": "Stand in the fountain to wish, or walk up to Father Given to talk"})
        elif near_bot:  # talking wins - Father Given starts out standing in the fountain plaza
            # talking to Father Given: the story hint (and the Forge, in the Finale)
            _story_event(s, "talk")
            line = story.given_line(p.story, s.given_heard)
            state.nexus_bot.speech = line
            state.nexus_bot.speech_age = 0.0
            if p.story.current() is story.ACTS[-1]:
                _enter_forge(state, s)
        else:
            old, new, err = wish_fountain(p)
            if err:
                send_msg(s.sock, {"type": "wish_result", "error": err})
            else:
                send_msg(s.sock, {"type": "wish_result", "old_name": old.name, "new_name": new.display_name,
                                   "new_color": list(new.color), "is_ut": new.is_ut,
                                   "upgrade": new.tier > (old.tier or 0), "same_tier": new.tier == (old.tier or 0)})
    elif kind in ("echo_shop_open", "echo_buy") and s.zone == ZONE_NEXUS:
        # the Echo Keeper (co-op): server-authoritative, same account functions as main.py
        on_keeper = state.nexus_map.tile_at(p.pos.x, p.pos.y) == world.ECHO_KEEPER_TILE
        msg, ok = None, True
        if kind == "echo_buy" and on_keeper:
            if action.get("item") == "backpack_slot":
                ok, msg = accounts.buy_backpack_slot(p.name)
                if ok:
                    p.backpack_size += 1
            elif action.get("item") == "starting_xp":
                ok, msg = accounts.buy_starting_xp_boost(p.name)
        send_msg(s.sock, {"type": "echo_shop_state", "echoes": accounts.get_echoes(p.name),
                           "unlocks": accounts.get_unlocks(p.name), "message": msg, "ok": ok})
    elif kind == "respawn" and s.zone == ZONE_DEAD:
        s.player = Player(action.get("cls", "wizard"), name=p.name, pid=s.pid)
        s.player.story = _fresh_story(p.name)
        s.player.pos = _nexus_spawn_pos(state)
        s.zone = ZONE_NEXUS
        s.death_info = None


INTEREST_RADIUS = 1400  # only entities within this range of the player are worth sending


def _nearby(entities, pos, radius=INTEREST_RADIUS):
    r2 = radius * radius
    return [e for e in entities if (e.pos.x - pos.x) ** 2 + (e.pos.y - pos.y) ** 2 <= r2]


def _trade_info_for(state, s):
    trade = state.trades.get(s.trade_id)
    if trade is None:
        return None
    other = state.sessions.get(trade.other(s.pid))
    mine, theirs = trade.offer_of(s.pid), trade.offer_of(trade.other(s.pid))
    mine_accept = trade.accept_a if s.pid == trade.a_pid else trade.accept_b
    their_accept = trade.accept_b if s.pid == trade.a_pid else trade.accept_a
    return {
        "other_name": other.player.name if other else "?",
        "my_offer": [it.to_json() for it in mine],
        "their_offer": [it.to_json() for it in theirs],
        "my_accept": mine_accept, "their_accept": their_accept,
        "timer": trade.confirm_timer,
        "status": trade.status,
        # backpack indices of my offered items, so the client can highlight them in place
        "my_offer_idx": [i for i, bp in enumerate(s.player.backpack) if any(bp is it for it in mine)],
    }


def _trade_invite_for(state, s):
    inv = state.trade_invites.get(s.pid)
    sender = state.sessions.get(inv["from"]) if inv else None
    if sender is None:
        return None
    return {"from_name": sender.player.name, "time_left": round(inv["t"], 1)}


def _snapshot_for(state, s):
    snap = _snapshot_core(state, s)
    snap["live_event"] = live_events.current_event()  # clients show the HOST's event, not their own
    if s.zone != ZONE_DEAD:
        # story: every zone carries the quest log; feed lines/banners ride exactly one snapshot
        snap["quest_log"] = s.player.story.quest_log()
        snap["sidequests"] = s.player.sidequests.log(s.player)
        snap["sidequests_done"] = [sidequests.QUESTS[q]["title"] for q in s.player.sidequests.done
                                   if q in sidequests.QUESTS]
        snap["story_feed"] = [[msg, list(color)] for msg, color in s.story_feed]
        snap["story_banners"] = list(s.story_banners)
        s.story_feed, s.story_banners = [], []
    return snap


def _snapshot_core(state, s):
    if s.zone == ZONE_DEAD:
        return {"type": "snapshot", "zone": "dead", "death_info": s.death_info}
    chats = [[pid, text] for pid, zone, text in state.chat_queue if zone == s.zone]
    trade_info = _trade_info_for(state, s)
    if s.zone in (ZONE_NEXUS, ZONE_BAZAAR, ZONE_VAULT_ROOM):
        peers = [o.player.net_state() for o in state.sessions.values() if o.zone == s.zone and o is not s]
        payload = {"type": "snapshot", "zone": s.zone, "you": s.player.full_state(), "players": peers,
                   "chats": chats, "trade": trade_info,
                   "trade_invite": _trade_invite_for(state, s)}
        if s.zone == ZONE_BAZAAR:
            payload["ground_items"] = [g.net_state() for g in state.bazaar_ground_items]
        elif s.zone == ZONE_NEXUS:
            payload["bot"] = state.nexus_bot.net_state()
            payload["npcs"] = [n.net_state() for n in state.nexus_npcs]
        return payload
    sim = state.realm_sim if s.zone == ZONE_REALM else state.bonus_sims.get(s.bonus_sim_id)
    # for ZONE_BONUS, peers must be scoped to the SAME dungeon instance - with several
    # concurrent instances now possible, a bare zone match would show a player peers
    # who are actually in a totally different dungeon
    peers = [o.player.net_state() for o in state.sessions.values()
             if o.zone == s.zone and o is not s
             and (s.zone != ZONE_BONUS or o.bonus_sim_id == s.bonus_sim_id)]
    feed = [[msg, color] for pid, msg, color in sim.events if pid in (None, s.pid)]
    # The realm/bonus map is static per instance (~15KB as JSON) - sending it every tick at
    # 20Hz was ~300KB/s per client and could make a slow receiver's socket buffer fall behind,
    # which looks exactly like "shots keep missing" (client acts on stale-but-self-consistent
    # positions). Send it once per zone-instance instead; the client caches it by zone.
    map_payload = None
    if s.sent_map_id != id(sim):
        map_payload = sim.realm_map.grid
        s.sent_map_id = id(sim)
    # the realm can now hold up to ~250 enemies map-wide (see game/realm_sim.py's
    # pre-populated ecosystem) - sending literally all of them to every client every
    # tick doesn't scale (both bandwidth and how much a single JSON message balloons),
    # and none of them are relevant to a player who isn't near them anyway, so each
    # client only gets what's actually within range of their own position.
    p_pos = s.player.pos
    visible_enemies = _nearby(sim.enemies, p_pos)
    if sim.boss is not None and sim.boss.alive and sim.boss not in visible_enemies:
        # the boss is always sent regardless of distance - it's meant to show as an
        # always-on minimap directional aid ("boss can be seen only on the minimap
        # even if you're not in the room next to him"), which the ordinary distance
        # cull above would otherwise silently defeat for a player far across a
        # 60x60-tile dungeon (bigger than INTEREST_RADIUS)
        visible_enemies = visible_enemies + [sim.boss]
    # real line-of-sight (walls + live obstacles), not a room-tag match - the old
    # room_idx approach hid enemies that had physically wandered/chased into the
    # player's own room (tag set once at spawn, never updated) and hid an entire
    # room's pod the instant the player stood one tile outside its rect even with
    # a clear sightline in (no doors in this dungeon style). Computed server-side
    # (not left to the client to self-filter) both to avoid a client trusting
    # itself about what it "should" see, and because the server already knows
    # both positions for free - same reasoning as the old room filter, just a
    # correct occlusion test instead of a stale tag. Tagged per-entry (`visible`)
    # rather than dropped from the list entirely, so the boss (always included
    # above) can still reach the client for its minimap blip even while not
    # currently in LOS - only the MAIN VIEW draw loop respects this flag
    # (see coop_client.py), the minimap ignores it exactly as before.
    enemy_payloads = []
    for e in visible_enemies:
        d = e.net_state()
        d["visible"] = (not sim.is_bonus_room) or sim.has_line_of_sight(p_pos.x, p_pos.y, e.pos.x, e.pos.y)
        enemy_payloads.append(d)
    return {
        "type": "snapshot", "zone": s.zone, "you": s.player.full_state(), "players": peers,
        "map": map_payload,
        # the quest map / dictionary's area info (game/codex.realm_areas) rides with the map, once
        "areas": codex.realm_areas(sim) if map_payload is not None and not sim.is_bonus_room else None,
        "enemies": enemy_payloads,
        "bullets": [b.net_state() for b in _nearby(sim.bullets, p_pos)],
        # personal loot (Batch 15): a player only ever sees shared bags and their OWN
        "ground_items": [g.net_state() for g in _nearby(sim.ground_items, p_pos)
                         if getattr(g, "owner_pid", None) in (None, s.pid)],
        "npcs": [n.net_state() for n in _nearby(sim.npcs, p_pos)],
        "island_chests": [{"x": ch["pos"].x, "y": ch["pos"].y, "skin": ch["skin"], "opened": s.pid in ch["opened"]}
                          for ch in sim.island_chests if ch["pos"].distance_to(p_pos) <= INTEREST_RADIUS],
        "portals": [pt.net_state() for pt in sim.portals],
        "obstacles": [ob.net_state() for ob in sim.obstacles],
        "portal_prompt": s.portal_prompt is not None,
        "boss": sim.boss is not None, "kill_count": sim.kill_count, "feed": feed,
        "popups": [list(p) for p in sim.damage_popups],
        "vfx": [list(v) for v in sim.vfx_events],
        "sound": [list(sd) for sd in sim.sound_events],
        "mob_speech": [list(sp) for sp in audible_mob_speech(sim.mob_speech_events, p_pos)],
        "difficulty": sim.difficulty["name"] if sim.difficulty else None,
        "theme_name": sim.theme_name if s.zone == ZONE_BONUS else None,
        "secret_quest": sim.secret_quest if s.zone == ZONE_BONUS else None,
        "secret_quest_progress": sim.secret_quest_progress if s.zone == ZONE_BONUS else 0,
        "secret_quest_timer": sim._quest_timer if s.zone == ZONE_BONUS else 0.0,
        "secret_quest_target": sim._secret_quest_target if s.zone == ZONE_BONUS else 0,
        "phase2_quest": sim.phase2_quest if s.zone == ZONE_BONUS else None,
        "phase2_quest_progress": sim.phase2_quest_progress if s.zone == ZONE_BONUS else 0,
        "phase2_quest_target": sim._phase2_quest_target if s.zone == ZONE_BONUS else 0,
        "light_level": sim.light_level, "blood_moon": sim.blood_moon_active,
        "chats": chats,
        "trade": trade_info,
        "trade_invite": _trade_invite_for(state, s),
    }


def tick_loop(state, stop_event):
    interval = 1.0 / C.NET_TICK_HZ
    last = time.perf_counter()
    while not stop_event.is_set():
        now = time.perf_counter()
        dt = min(now - last, 0.1)
        last = now
        try:
            with state.lock:
                step(state, dt)
                snapshots = [(s, _snapshot_for(state, s)) for s in state.sessions.values()]
                state.chat_queue = []  # each chat message rides exactly one tick's worth of snapshots
            for s, snap in snapshots:
                try:
                    send_msg(s.sock, snap)
                except OSError:
                    pass  # that client's recv thread will notice the disconnect and clean up
        except Exception:
            # a bug in one tick must never take the whole co-op session down silently
            import traceback
            traceback.print_exc()
        elapsed = time.perf_counter() - now
        time.sleep(max(0.0, interval - elapsed))


def handle_client(sock, addr, state):
    reader = MessageReader(sock)
    pid = uuid.uuid4().hex[:8]
    try:
        msgs = reader.read_available()
        join = next((m for m in msgs if m.get("type") == "join"), None)
        while join is None:
            msgs = reader.read_available()
            join = next((m for m in msgs if m.get("type") == "join"), None)
        name = str(join.get("name", "Player"))[:16] or "Player"
        cls_name = join.get("cls", "wizard")
        accounts.touch_account(name)
        saved = characters.load_character(name)
        if saved is not None:
            player = Player.from_full_state(dict(saved, pid=pid, name=name))
            player.alive = True  # a dead character is never saved - see characters.delete_character
            player.story = story.StoryProgress.from_json(saved.get("story"), accounts.get_story_act(name))
        else:
            player = Player(cls_name, name=name, pid=pid)
            accounts.apply_unlocks(player, name)
            player.story = _fresh_story(name)
        with state.lock:
            player.pos = _nexus_spawn_pos(state)
            session = Session(pid, sock, player)
            state.sessions[pid] = session
        send_msg(sock, {"type": "welcome", "pid": pid})
        print(f"[server] {name} ({cls_name}) joined from {addr} as {pid}")

        while True:
            for msg in reader.read_available():
                t = msg.get("type")
                if t == "input":
                    with state.lock:
                        session.last_input = msg
                elif t == "action":
                    with state.lock:
                        state.pending_actions.append((pid, msg))
                elif t == "chat":
                    text = str(msg.get("text", ""))[:1000].strip()
                    if text:
                        with state.lock:
                            state.chat_queue.append((pid, session.zone, text))
    except (ConnectionError, OSError):
        pass
    finally:
        with state.lock:
            sess = state.sessions.pop(pid, None)
        if sess is not None and sess.player.alive:
            characters.save_character(sess.player.name, sess.player)
        try:
            sock.close()
        except OSError:
            pass
        print(f"[server] {pid} disconnected")


def run_server(host="0.0.0.0", port=C.NET_PORT):
    state = ServerState()
    stop_event = threading.Event()
    threading.Thread(target=tick_loop, args=(state, stop_event), daemon=True).start()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, port))
    listener.listen(8)
    print(f"[server] listening on {host}:{port} - share your LAN/public IP with friends")
    try:
        while True:
            conn, addr = listener.accept()
            threading.Thread(target=handle_client, args=(conn, addr, state), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[server] shutting down")
    finally:
        stop_event.set()
        listener.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Realm Reforged co-op server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=C.NET_PORT)
    args = parser.parse_args()
    run_server(args.host, args.port)

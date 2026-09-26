"""
Realm Reforged co-op client.

Connects to a running server.py and plays the shared Nexus / Bazaar /
Realm / Bonus-room session. Rendering reuses the exact same sprites/world/ui
code as the single-player game; only where the state comes from differs
(server snapshots instead of local simulation).

Known v0 limitation: movement is NOT client-predicted - your own player's
position is whatever the last server snapshot said, so there is roughly one
network tick (50ms) plus round-trip latency of input lag. Fine on a LAN,
noticeable over the open internet.

Usage:
    python coop_client.py --host 127.0.0.1 --port 50777 --name Alex
"""
import argparse
import math
import random
import socket
import sys
import threading

import pygame

from game import constants as C
from game import world
from game import ui
from game import sprites
from game import audio
from game import minimap
from game import vault
from game import weather
from game import vfx
from game import clipboard
from game import friends
from game import crews
from game import live_events
from game import zone_banner
from game import accounts
from game import settings
from game import options_menu
from game.panel_drag import PanelDrag
from game.chat_input import ChatInput, LogSelection
from game import story
from game import journal
from game.npcs import NPC
from game.entities import Player, Enemy, Bullet, Bag, Portal, Obstacle, NexusBot, BAG_CAPACITY, CHEST_SKIN_NAMES
from game.netmsg import send_msg, MessageReader
from game.items import VAULT_SLOTS, VAULT_CHEST_SIZE, identify_proc_kind, SLOT_WEAPON
from game.realm_sim import auto_aim_direction, AUTO_AIM_CONE_DEG, DUNGEON_THEMES

STATE_INTRO, STATE_CLASS_SELECT, STATE_CONNECTING, STATE_ERROR, STATE_PLAY = range(5)
SPEECH_BUBBLE_LIFETIME = 4.0
CHAT_MAX_LEN = 1000
SOUND_HEARING_RADIUS = 900  # matches main.py's single-player constant - see its comment
CHAT_LOG_LIFETIME = 120.0  # chat log entries expire after 2 minutes
NEARBY_PLAYER_RADIUS = 2 * max(C.SCREEN_W, C.SCREEN_H)  # "see players within double my screen", for the panel + TP


# ---------------------------------------------------------- display-only "ghosts" --
# These reuse the real classes' draw() methods (which only touch a handful of
# attributes) without needing the full simulation objects on the client.
class GhostEnemy:
    draw = Enemy.draw

    def __init__(self, d):
        self.kind = d["kind"]
        self.pos = pygame.Vector2(d["x"], d["y"])
        self.hp, self.hp_max, self.rank = d["hp"], d["hp_max"], d["rank"]
        self._hit_flash = 0.0  # not synced over the network - cosmetic only, defaults off
        self._pretelegraph = d.get("pretelegraph", False)
        self.frozen_time = 1.0 if d.get("frozen") else 0.0
        self.moonlit = d.get("moonlit", False)
        self.invulnerable = d.get("invulnerable", False)
        self.speech = d.get("speech", "")
        self.speech_age = d.get("speech_age", 999.0)
        self.neutral = d.get("neutral", False)
        self.scale = d.get("scale")  # per-instance sprite/hitbox scale (e.g. landmark guardians)
        self.visible = d.get("visible", True)  # server-computed real LOS - see server.py::_snapshot_for


class GhostBullet:
    draw = Bullet.draw

    def __init__(self, d):
        self.pos = pygame.Vector2(d["x"], d["y"])
        self.color, self.radius = tuple(d["color"]), d["radius"]
        self.shape = d.get("shape", "bolt")
        self.vel = pygame.Vector2(d.get("vel", (0, 0)))


class GhostBag:
    # a ghost carries only an item COUNT (the items themselves ride bag_state when
    # opened) - borrowing Bag.draw crashed on len(self.items) the first time a loot
    # bag came into view (fuzz-found), so mirror it with the count instead
    def draw(self, surf, cam):
        p = cam(self.pos)
        img = sprites.bag_sprite(self.count / BAG_CAPACITY > 0.5, self.bag_color)
        surf.blit(img, (p[0] - img.get_width() // 2, p[1] - img.get_height() // 2 + 3))

    def __init__(self, d):
        self.id = d["id"]
        self.pos = pygame.Vector2(d["x"], d["y"])
        self.bag_color = tuple(d["bag_color"])
        self.name = d.get("name")
        self.count = d.get("count", 1)
        self.tier_color = tuple(d["tier_color"]) if d.get("tier_color") else (200, 200, 200)


class GhostChest:
    """Client-side mirror of a server-owned BazaarChest - separate from
    GhostBag since a chest's net_state() carries a skin index, not a
    bag_color/tier_color/name (see BazaarChest.net_state)."""
    def __init__(self, d):
        self.id = d["id"]
        self.pos = pygame.Vector2(d["x"], d["y"])
        self.skin_idx = d.get("skin_idx", 0)
        self.count = d.get("count", 0)
        # what a real BazaarChest (a "brown" Bag subclass) exposes to the Bazaar's
        # nearby-loot panel / hover tooltip - missing bag_color crashed the client
        # the moment you walked near a chest (fuzz-found)
        self.bag_color = C.BAG_COLORS["brown"]
        self.name = f"{CHEST_SKIN_NAMES[self.skin_idx % len(CHEST_SKIN_NAMES)].title()} chest"

    def draw(self, surf, cam):
        p = cam(self.pos)
        img = sprites.chest_sprite(self.skin_idx, filled=self.count > 0)
        surf.blit(img, (p[0] - img.get_width() // 2, p[1] - img.get_height() // 2 + 3))


class GhostBot:
    draw = NexusBot.draw

    def __init__(self, d):
        self.pos = pygame.Vector2(d["x"], d["y"])
        self.name = d.get("name", "Father Given")
        self.speech = d.get("speech", "")
        self.speech_age = d.get("speech_age", 0.0)
        self.SPEECH_LIFETIME = NexusBot.SPEECH_LIFETIME


class GhostPortal(Portal):
    # subclass (not just `draw = Portal.draw`): draw() also needs Portal's class-level
    # KIND_COLORS/ARCH_STONE and its _draw_* helpers - copying draw alone crashed the
    # client with AttributeError the first time a portal came into view (fuzz-found)

    def __init__(self, d, t=0.0):  # deliberately skips Portal.__init__ (no life/id/sim state)
        self.pos = pygame.Vector2(d["x"], d["y"])
        self.t = t
        self.kind = d.get("kind", "ambient")
        self.difficulty = d.get("difficulty")
        self.label = d.get("label")


class GhostObstacle:
    draw = Obstacle.draw

    def __init__(self, d):
        self.pos = pygame.Vector2(d["x"], d["y"])
        self.radius = C.TILE * 0.42
        self.kind = d.get("kind", "crate")



def _split_msg_target(rest):
    """'/msg "Two Words" hi there' or '/msg Bob hi' -> (name, message)."""
    rest = rest.strip()
    if rest.startswith('"'):
        end = rest.find('"', 1)
        if end > 0:
            return rest[1:end].strip(), rest[end + 1:].strip()
    name, _, msg = rest.partition(" ")
    return name.strip('"'), msg.strip()

class NetLink:
    """Background thread that keeps the latest server messages ready for the render loop."""

    def __init__(self, sock):
        self.sock = sock
        self.reader = MessageReader(sock)
        self.lock = threading.Lock()
        self.latest_snapshot = None
        self.pending_map = None
        self.pending_areas = None
        self.vault_items = None
        self.vault_chest_hint = None
        self.bag_state = None  # {"id": bag_id, "items": [json, ...]} - the last opened/withdrawn-from bag
        self.whispers = []  # queued incoming/echoed whisper messages, drained each frame
        self.wish_result = None
        self.socket_result = None
        self.trade_notices = []  # server "trade_notice" texts (request sent/declined/expired, ...)
        self.echo_shop_states = []  # server "echo_shop_state" dicts (Echo Keeper shop, see server.py)
        self.pet_results = []  # server "pet_result" dicts (feed/pack/fuse/hatch outcome, see server._pet_result)
        self.story_feed = []  # story lines/banners ride ONE snapshot each - collected here as each
        self.story_banners = []  # snapshot is seen, same reason as pending_map below
        self.dialogue_msgs = []  # server "dialogue" messages ({"view": dict | None}), in order
        self.welcome_pid = None
        self.error = None
        self._stop = False
        self.thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.thread.start()

    def _recv_loop(self):
        try:
            while not self._stop:
                for msg in self.reader.read_available():
                    t = msg.get("type")
                    if t == "snapshot":
                        with self.lock:
                            self.latest_snapshot = msg
                            # the realm/bonus map rides inside a snapshot message but is only
                            # sent once per zone-instance (see server.py's sent_map_id) - it's
                            # ~2-3MB of JSON at the current map size, big enough to take longer
                            # than one tick to arrive+parse over the socket. Because this class
                            # only ever exposes the LATEST snapshot (see get_snapshot()), a
                            # smaller, faster-arriving snapshot from a tick or two later could
                            # otherwise overwrite latest_snapshot before the main thread ever
                            # reads the map-bearing one - permanently losing the map for this
                            # session, since the server never resends it. Stashing it separately
                            # the moment it's SEEN (not the moment it's consumed) fixes that.
                            if msg.get("map") is not None:
                                self.pending_map = msg["map"]
                                self.pending_areas = msg.get("areas")
                            self.story_feed.extend(msg.get("story_feed", ()))
                            self.story_banners.extend(msg.get("story_banners", ()))
                    elif t == "vault_state":
                        with self.lock:
                            self.vault_items = msg["items"]
                            self.vault_chest_hint = msg.get("chest")
                    elif t == "bag_state":
                        with self.lock:
                            self.bag_state = msg
                    elif t == "whisper":
                        with self.lock:
                            self.whispers.append(msg)
                    elif t == "wish_result":
                        with self.lock:
                            self.wish_result = msg
                    elif t == "socket_result":
                        with self.lock:
                            self.socket_result = msg
                    elif t in ("trade_notice", "trade_error"):
                        with self.lock:
                            self.trade_notices.append(msg.get("message", ""))
                    elif t == "pet_result":
                        with self.lock:
                            self.pet_results.append(msg)
                    elif t == "echo_shop_state":
                        with self.lock:
                            self.echo_shop_states.append(msg)
                    elif t == "dialogue":
                        with self.lock:
                            self.dialogue_msgs.append(msg)
                    elif t == "welcome":
                        self.welcome_pid = msg["pid"]
        except (ConnectionError, OSError) as e:
            self.error = str(e) or "connection lost"

    def send(self, obj):
        try:
            send_msg(self.sock, obj)
        except OSError as e:
            self.error = str(e) or "send failed"

    def get_snapshot(self):
        with self.lock:
            return self.latest_snapshot

    def pop_pending_areas(self):
        with self.lock:
            v, self.pending_areas = self.pending_areas, None
            return v

    def pop_pending_map(self):
        with self.lock:
            v, self.pending_map = self.pending_map, None
            return v

    def pop_vault_items(self):
        with self.lock:
            v, self.vault_items = self.vault_items, None
            c, self.vault_chest_hint = self.vault_chest_hint, None
            return v, c

    def pop_bag_state(self):
        with self.lock:
            v, self.bag_state = self.bag_state, None
            return v

    def pop_whispers(self):
        with self.lock:
            v, self.whispers = self.whispers, []
            return v

    def pop_wish_result(self):
        with self.lock:
            v, self.wish_result = self.wish_result, None
            return v

    def pop_socket_result(self):
        with self.lock:
            v, self.socket_result = self.socket_result, None
            return v

    def pop_story(self):
        with self.lock:
            v = (self.story_feed, self.story_banners)
            self.story_feed, self.story_banners = [], []
            return v

    def pop_dialogue(self):
        """The newest dialogue message since the last call, or None if none arrived."""
        with self.lock:
            msgs, self.dialogue_msgs = self.dialogue_msgs, []
        return msgs[-1] if msgs else None

    def pop_echo_shop_states(self):
        with self.lock:
            v, self.echo_shop_states = self.echo_shop_states, []
        return v

    def pop_pet_results(self):
        with self.lock:
            v, self.pet_results = self.pet_results, []
        return v

    def pop_trade_notices(self):
        with self.lock:
            v, self.trade_notices = self.trade_notices, []
            return v

    def stop(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass


class CoopClient:
    def __init__(self, host, port, name):
        pygame.init()
        audio.init()
        settings.load()  # before the first theme plays, so saved volumes apply from the start
        audio.play_theme()
        self.fullscreen = False
        self.help_open = False
        self.menu_selected = 0
        self.quit_confirm_open = False  # Esc with nothing else open asks before quitting
        self.echo_shop_open = False  # the Echo Keeper's shop (Nexus) - see _echo_shop_items
        self.echo_shop_selected = 0
        self.echo_shop_data = {}  # last server "echo_shop_state": echoes + unlocks
        self.panel_drag = PanelDrag()  # mouse-draggable chat log / quest log
        self._base_size = (C.SCREEN_W, C.SCREEN_H)
        # RESIZABLE gives the window a real title bar with a native maximize button
        # (next to minimize/close) - clicking it, or F11, or dragging an edge all land
        # in the VIDEORESIZE handler in handle_events().
        self.window = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H), pygame.RESIZABLE)
        self.screen = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
        pygame.display.set_caption(C.TITLE + f" - co-op ({name})")
        self.clock = pygame.time.Clock()
        self.host, self.port, self.name = host, port, name

        self.state = STATE_INTRO
        self.intro_timer = 0.0
        self.intro_joke = random.choice(ui.INTRO_JOKES)
        self.select_idx = 0
        self.error_msg = ""
        self.link = None

        self.you = None
        self.peers = []
        self.zone = "nexus"
        self.tilemap = None
        self.enemies, self.bullets, self.ground_items, self.portals = [], [], [], []
        self.obstacles = []
        self.portal_prompt = False  # server says a portal is within range this tick - see _play_key
        self.secret_quest = None
        self.secret_quest_progress = 0
        self.secret_quest_timer = 0.0
        self.secret_quest_target = 0
        self.phase2_quest = None
        self.phase2_quest_progress = 0
        self.phase2_quest_target = 0
        self.boss_active = False
        self.kill_count = 0
        self.difficulty = None
        self.theme_name = None
        self.zone_tracker = zone_banner.ZoneTracker()  # zone-entry title cards + per-place music
        self.light_level = 1.0
        self.blood_moon = False
        self.weather_fx = weather.WeatherFX()
        self.realm_ambience = vfx.AmbientEvents([])  # open-Realm ambient flavor, client-side/cosmetic
        # like weather_fx - dungeon ambient instead comes from the server's RealmSim via sim.vfx_events
        self._dust_cd = 0.0
        self._prev_you_pos = None
        self.feed = []
        self.death_info = None
        self.cam = world.Camera(C.SCREEN_W, C.SCREEN_H)

        self.nexus_map = world.TileMap(world.make_nexus())    # deterministic, matches server exactly
        self.bazaar_map = world.TileMap(world.make_bazaar())  # deterministic, matches server exactly
        self.vault_room_map = world.TileMap(world.make_vault_room())  # deterministic, matches server exactly

        self.vault_chest_open = None  # index of the vault-room chest whose bag-style window is open
        self.vault_chest = 0  # which of the VAULT_CHEST_COUNT chests the server deposits into
        self._suppress_vault_trigger = False  # see _vault_click's close-button branch
        self.vault_items = []
        self.open_bag_id = None  # id of the ground Bag currently shown in the drag-and-drop window
        self.bag_items = []
        self.context_menu = None  # {"pid","name","pos"} - the right-click-a-player popup
        self.friends_panel_open = False
        self.friends = friends.load_friends(name)
        self.crew_name = crews.get_crew_for_player(name)
        self._last_nearby_rows = []  # [(row_rect, tp_rect, pid), ...] from the last draw, for click hit-testing
        self.bazaar_ground_items = []
        self.nexus_bot = None
        self._last_bot_speech = ""  # dedupe so the same line isn't re-pushed to chat_log every snapshot
        self.realm_minimap = None
        self.bonus_minimap = None
        self.auto_fire_enabled = settings.get("auto_fire")
        self.right_panel_mode = "inventory"  # Tab key: switches inventory vs. pet stats in the right dock
        self._dash_pending = False  # set on a Shift keydown, sent once then cleared - see _send_input().
        self.popups = []
        self._ui_click_active = False  # suppresses firing while a UI click (e.g. inventory) is held
        self._last_level = 1
        self.drag_from = None       # ("backpack", idx) or ("equip", slot_type) while a drag is in progress
        self.drag_start_pos = None
        self.pending_socket = None  # (source_idx, target_idx) awaiting an ENTER confirm - see
        # _inventory_mouse_up's backpack->backpack branch and identify_proc_kind's use there
        self._dblclick_slot = None  # ("backpack", idx) of the last plain click, for double-click-to-use
        self._dblclick_time = 0     # detection - equip/use now fires on a DOUBLE click, not a single one
        self.DBLCLICK_MS = 350
        self._prev_backpack_len = 0
        self._prev_boss_active = False
        self._local_fire_cd = 0.0  # client-side estimate only, purely to pace the shoot sound
        self.chat_open = False
        self.chat_buffer = ""
        self._chat_select_all = False
        self.chat_in = ChatInput()  # the input line's cursor/selection/history
        self.chat_log_sel = LogSelection()  # click-drag line selection in the chat log
        self._chat_box_dragging = False
        self._speech_bubbles = []  # [{pid, text, age}]
        self.chat_log = []  # [{name, text, age}] persistent left-side log, cap ui.CHAT_LOG_STORE_CAP, scrollable via self.chat_scroll
        self.chat_scroll = 0  # wrapped-line offset from the newest line, 0 = pinned to the bottom
        self.trade = None  # the server's per-viewer trade dict, or None (see server._trade_info_for)
        self.trade_invite = None  # incoming {"from_name", "time_left"} request, or None
        self.quest_log = None  # the server's story quest log (game/story.StoryProgress.quest_log())
        self.sidequest_log = []  # the server's side quests (game/sidequests.SideQuestProgress.log())
        self.dialogue_view = None  # the open conversation (server-owned, see server._send_dialogue)
        self.journal = journal.Journal()  # Quest Log / Dictionary / Quest Map windows (game/journal.py)
        self.sidequests_done = []  # completed side-quest titles (server snapshot)
        self.realm_grid = None  # the last open-Realm grid + its area info, kept for the journal
        self.realm_areas = None  # even while you're back in the Nexus
        self.npcs = []  # friendly NPCs in view (npcs.NPC rebuilt from snapshots)
        self.island_chests = []  # [(pos, skin, opened_for_me)]
        self.quest_log_expanded = True  # J toggles it between full and title-only
        self.story_banner = None  # [text, remaining_seconds]
        self.credits_t = None  # seconds into the end credits while they're showing
        self.inspect_pid = None  # peer shown in the Inspect panel (context menu -> Inspect)
        self.nexus_minimap = minimap.MinimapState()
        self.nexus_minimap.reveal_all(self.nexus_map)
        self.bazaar_minimap = minimap.MinimapState()
        self.bazaar_minimap.reveal_all(self.bazaar_map)
        self.vault_room_minimap = minimap.MinimapState()
        self.vault_room_minimap.reveal_all(self.vault_room_map)
        self.nexus_ambience = vfx.NexusAmbience()
        if settings.get("fullscreen"):
            self._toggle_fullscreen()

    # ---------------------------------------------------------------- run --
    def run(self):
        while True:
            dt = min(self.clock.tick(settings.fps_cap()) / 1000.0, 0.05)
            dt = vfx.apply_hitstop(dt)
            if not self.handle_events():
                break
            self.update(dt)
            self.draw()
            self._present()
        if self.link:
            self.link.stop()
        pygame.quit()
        sys.exit()

    def _present(self):
        # the game always renders onto a fixed-size canvas (self.screen), then that
        # canvas is scaled to whatever the real window/fullscreen size is - this works
        # on any display backend, unlike pygame.SCALED which needs a render backend
        # that isn't always available (it failed outright under headless test)
        if self.window.get_size() == self.screen.get_size():
            self.window.blit(self.screen, (0, 0))
        else:
            pygame.transform.scale(self.screen, self.window.get_size(), self.window)
        pygame.display.flip()

    def _toggle_fullscreen(self):
        # some display drivers/multi-monitor setups can raise pygame.error on a
        # FULLSCREEN mode switch - never let a display-mode change crash the game.
        wanted_fullscreen = not self.fullscreen
        try:
            if wanted_fullscreen:
                self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                self.window = pygame.display.set_mode(self._base_size, pygame.RESIZABLE)
            self.fullscreen = wanted_fullscreen
        except pygame.error:
            try:
                self.window = pygame.display.set_mode(self._base_size, pygame.RESIZABLE)
            except pygame.error:
                pass
            self.fullscreen = False
            self.feed.insert(0, ["Fullscreen unavailable on this display - staying windowed", (220, 140, 90), 4.0])
            self.feed = self.feed[:4]
        # read back the ACTUAL size the driver gave us, not the requested size, so
        # canvas/window/camera always stay consistent (also fixes mouse-aim being off
        # in fullscreen/resized windows - see _resize_canvas)
        self._resize_canvas(*self.window.get_size())
        if settings.get("fullscreen") != self.fullscreen:
            settings.change("fullscreen", self.fullscreen)

    MAX_CANVAS_DIM = 2560

    def _resize_canvas(self, w, h):
        w = max(320, min(self.MAX_CANVAS_DIM, w))
        h = max(240, min(self.MAX_CANVAS_DIM, h))
        C.SCREEN_W, C.SCREEN_H = w, h
        self.screen = pygame.Surface((w, h))
        self.cam.screen_w, self.cam.screen_h = w, h

    def _menu_items(self):
        """The O-key options menu rows (see game/options_menu.py) - persisted
        settings plus this client's own actions."""
        mm = self._current_minimap()
        return options_menu.build_rows(
            auto_fire_get=lambda: self.auto_fire_enabled, auto_fire_set=self._set_auto_fire,
            fullscreen_get=lambda: self.fullscreen, fullscreen_toggle=self._toggle_fullscreen,
            reset_camera=self.cam.reset_rotation, close=self._menu_close,
            full_map=(lambda: mm.full_map_open, self._menu_toggle_full_map) if mm is not None else None,
            leave=("Disconnect (return to Class Select)", self._menu_disconnect)
            if self.state == STATE_PLAY else None,
            journal=[("Quest Log", self._open_quest_log), ("Dictionary", self._open_dictionary)]
            if self.state == STATE_PLAY else None)

    def _open_quest_log(self):
        self.help_open = False
        self.journal.open_quest_log()

    def _open_dictionary(self):
        self.help_open = False
        self.journal.open_dictionary()

    def _journal_ctx(self):
        """What the Quest Log / Dictionary / Quest Map need (see game/journal.py)."""
        you = self.you
        in_realm = self.zone == "realm" and you is not None and self.realm_grid is not None
        return {
            "story": self.quest_log,
            "side": self.sidequest_log or [],
            "side_done": self.sidequests_done or [],
            "grid": self.realm_grid,
            "areas": self.realm_areas,
            "player_tile": (you.pos.x / C.TILE, you.pos.y / C.TILE) if in_realm else None,
        }

    def _set_auto_fire(self, enabled):
        self.auto_fire_enabled = bool(enabled)
        settings.change("auto_fire", self.auto_fire_enabled)

    def _menu_toggle_full_map(self):
        mm = self._current_minimap()
        if mm is not None:
            mm.full_map_open = not mm.full_map_open

    def _menu_disconnect(self):
        if self.link:
            self.link.stop()
        self.link = None
        self.state = STATE_CLASS_SELECT
        self.help_open = False

    def _cancel_drag(self):
        """Drops any in-progress drag / unconfirmed socket - called on every zone change
        and whenever an overlay opens, so a drag can never outlive the screen it started on."""
        self.drag_from = None
        self.drag_start_pos = None
        self.pending_socket = None
        self._ui_click_active = False

    def _menu_close(self):
        self.help_open = False

    # ------------------------------------------------------------- events --
    CHAT_ZONES = ("nexus", "bazaar", "vault_room", "realm", "bonus")

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if self.quit_confirm_open:
                verdict = options_menu.quit_confirm_verdict(event)
                if verdict is not None:
                    self.quit_confirm_open = False
                if verdict:
                    return False
                continue
            if self.journal.is_open() and self.journal.handle_event(event, self._journal_ctx()):
                continue
            if self.dialogue_view is not None and event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                choice = ui.dialogue_choice_for_event(event, self.dialogue_view)
                if choice is not None:
                    self.link.send({"type": "action", "action": "dialogue_choice", "idx": choice})
                    if choice == len(self.dialogue_view["options"]) - 1:
                        self.dialogue_view = None  # "Bye." - don't wait a round trip to close
                continue
            if self.state == STATE_INTRO:
                if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    self.state = STATE_CLASS_SELECT
                continue
            if self.state == STATE_CLASS_SELECT and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, cls in ui.class_select_tile_rects():
                    if rect.collidepoint(event.pos):
                        self.select_idx = ui.CLASS_ORDER.index(cls)
                        self._connect(cls)
                        break
                continue
            if (self.credits_t is not None and event.type == pygame.KEYDOWN
                    and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE)):
                self.credits_t = None  # skip the end credits
                continue
            if self._chat_mouse_event(event):
                continue
            if event.type == pygame.KEYDOWN:
                if self.chat_open:
                    self._handle_chat_key(event)
                elif (event.key == pygame.K_c and event.mod & pygame.KMOD_CTRL
                      and self.chat_log_sel.span() is not None):
                    self._copy_chat_selection()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.pending_socket is not None:
                    self._apply_pending_socket()
                elif (event.key in (pygame.K_RETURN, pygame.K_f) and self.state == STATE_PLAY
                      and self.zone == "vault_room" and self.vault_chest_open is None and not self.help_open
                      and self._try_open_vault_chest()):
                    pass
                elif (event.key == pygame.K_RETURN and self.state == STATE_PLAY
                      and self.zone in self.CHAT_ZONES and not self.help_open and not self.echo_shop_open
                      and not self.portal_prompt):
                    # standing near a portal takes priority over opening chat - see _play_key
                    self.chat_open = True
                    self.chat_buffer = ""
                elif event.key == pygame.K_F11:
                    self._toggle_fullscreen()
                elif event.key == pygame.K_x:
                    self.cam.reset_rotation()
                elif event.key == pygame.K_o:
                    self.help_open = not self.help_open
                    self.menu_selected = 0
                    self._cancel_drag()
                elif self.help_open and event.key in options_menu.MENU_KEYS:
                    new_sel = options_menu.handle_key(self._menu_items(), self.menu_selected, event.key)
                    if new_sel is not None:
                        self.menu_selected = new_sel
                elif self.echo_shop_open and event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_w, pygame.K_s):
                    step = -1 if event.key in (pygame.K_UP, pygame.K_w) else 1
                    self.echo_shop_selected = (self.echo_shop_selected + step) % len(self._echo_shop_items())
                elif self.echo_shop_open and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._echo_shop_items()[self.echo_shop_selected][1]()
                elif self.echo_shop_open and event.key == pygame.K_ESCAPE:
                    self.echo_shop_open = False
                elif event.key == pygame.K_SPACE and self.zone in ("realm", "bonus"):
                    self._use_ability()
                elif event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT) and self.zone in ("realm", "bonus"):
                    self._dash_pending = True
                elif event.key == pygame.K_m and self._current_minimap() is not None:
                    self._current_minimap().full_map_open = not self._current_minimap().full_map_open
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    self._zoom_minimap(minimap.ZOOM_STEP)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    self._zoom_minimap(-minimap.ZOOM_STEP)
                elif event.key == pygame.K_ESCAPE and self.pending_socket is not None:
                    self.pending_socket = None
                elif event.key == pygame.K_ESCAPE and self.drag_from is not None:
                    self._cancel_drag()
                elif event.key == pygame.K_ESCAPE:
                    if self._map_open():
                        self._current_minimap().full_map_open = False
                    elif self.context_menu is not None:
                        self.context_menu = None
                    elif self.inspect_pid is not None:
                        self.inspect_pid = None
                    elif self.friends_panel_open:
                        self.friends_panel_open = False
                    elif self.help_open:
                        self.help_open = False
                    elif self.trade_invite is not None:
                        self.link.send({"type": "action", "action": "trade_invite_decline"})
                        self.trade_invite = None
                    elif self.trade is not None:
                        self.link.send({"type": "action", "action": "trade_cancel"})
                    elif self.open_bag_id is not None:
                        self.open_bag_id = None
                    elif self.vault_chest_open is not None:
                        self._close_vault_chest()
                    else:
                        # nothing left to close - Esc asks before quitting (Esc again = quit)
                        self.quit_confirm_open = True
                elif self.state == STATE_CLASS_SELECT:
                    self._class_select_key(event.key)
                elif self.state == STATE_ERROR and event.key == pygame.K_RETURN:
                    self.state = STATE_CLASS_SELECT
                elif self.state == STATE_PLAY:
                    self._play_key(event.key)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.state == STATE_PLAY:
                if self.zone == "dead":
                    if ui.death_screen_button_rect().collidepoint(event.pos):
                        self._send_respawn()
                elif self.help_open and ui.help_close_button_rect(self._menu_items()).collidepoint(event.pos):
                    self.help_open = False
                elif self.help_open:
                    clicked = options_menu.handle_click(self._menu_items(), event.pos)
                    if clicked is not None:
                        self.menu_selected = clicked
                elif self.echo_shop_open and ui.echo_shop_close_button_rect(self._echo_shop_items()).collidepoint(event.pos):
                    self.echo_shop_open = False
                elif self.echo_shop_open:
                    items = self._echo_shop_items()
                    for i, rect in enumerate(ui.echo_shop_menu_item_rects(items)):
                        if rect.collidepoint(event.pos):
                            self.echo_shop_selected = i
                            items[i][1]()
                            break
                elif self.context_menu is not None:
                    self._context_menu_click(event.pos)
                elif self.trade_invite is not None and self._trade_invite_click(event.pos):
                    pass
                elif self.inspect_pid is not None and ui.inspect_close_button_rect().collidepoint(event.pos):
                    self.inspect_pid = None
                elif self.friends_panel_open:
                    self._friends_panel_click(event.pos)
                elif (self.vault_chest_open is not None and self.zone == "vault_room"
                      and ui.vault_chest_close_button_rect(self._vault_chest_screen_pos()).collidepoint(event.pos)):
                    self._close_vault_chest()
                elif self.trade is not None:
                    self._trade_click(event.pos)
                elif self._current_minimap() is not None and self._minimap_button_click(event.pos):
                    pass
                elif (self._current_bag() is not None
                      and ui.bag_window_close_button_rect(self.cam(self._current_bag().pos)).collidepoint(event.pos)):
                    self.open_bag_id = None
                    self.bag_items = []
                elif ui.quest_slot_rect() is not None and ui.quest_slot_rect().collidepoint(event.pos):
                    self.panel_drag.down("quest", event.pos)
                elif (self.zone in self.CHAT_ZONES
                      and ui.chat_log_rect(self.chat_log).collidepoint(event.pos)):
                    # its top strip moves the panel; the rest selects lines to copy
                    # (a plain click no longer opens chat - Enter does)
                    self._chat_log_mouse_down(event.pos)
                elif self._nearby_players_click(event.pos, self._last_nearby_rows):
                    pass
                elif (self.you and self.zone in ("nexus", "bazaar", "vault_room", "realm", "bonus")
                      and self._dock_mode() == "pet"
                      and ui.pet_pack_button_rect(self.you).collidepoint(event.pos)):
                    self.link.send({"type": "action", "action": "pack_pet"})
                elif self.you and self.zone in ("nexus", "bazaar", "vault_room", "realm", "bonus"):
                    self._inventory_mouse_down(event.pos)
            elif event.type == pygame.MOUSEMOTION:
                self.panel_drag.motion(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                dragged_panel, panel_moved = self.panel_drag.up()
                if dragged_panel == "quest" and not panel_moved and self.state == STATE_PLAY:
                    self.journal.open_quest_log()  # a plain click on the HUD log opens the full Quest Log
                if self.drag_from is not None and self.you is not None:
                    if self.vault_chest_open is not None and self.zone == "vault_room":
                        self._vault_mouse_up(event.pos)
                    else:
                        self._inventory_mouse_up(event.pos)
                self._ui_click_active = False
            elif (event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and self.state == STATE_PLAY
                  and self._chat_name_right_click(event.pos)):
                pass
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and self.state == STATE_PLAY:
                slot = self._slot_at(event.pos) if self.zone in ("realm", "bonus", "bazaar") else None
                peer = self._peer_near_mouse(event.pos) if self.you else None
                if slot is not None and slot[0] == "backpack" and self.you and slot[1] < len(self.you.backpack):
                    # right-click a backpack item = auto-drop it, RotMG's own convention
                    self.link.send({"type": "action", "action": "drop_item", "idx": slot[1]})
                elif peer is not None:
                    self._open_context_menu_for(peer, event.pos)
                elif self.zone in ("realm", "bonus", "bazaar"):
                    self.link.send({"type": "action", "action": "open_bag"})
            elif event.type == pygame.MOUSEWHEEL:
                if ui.chat_log_rect(self.chat_log).collidepoint(pygame.mouse.get_pos()):
                    max_scroll = ui.chat_log_max_scroll(self.chat_log)
                    self.chat_scroll = max(0, min(max_scroll, self.chat_scroll + event.y))
                else:
                    self._zoom_minimap(event.y * minimap.ZOOM_STEP)
            elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                self.window = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                self._base_size = self.window.get_size()
                self._resize_canvas(*self._base_size)
        return True

    # ------------------------------------------------------------ Echo Keeper --
    def _echo_shop_items(self):
        """Same rows as main.py's shop (accounts.echo_shop_rows), built from the last
        server "echo_shop_state" - buying is a server action, never a local change."""
        def buy(key):
            return lambda: self.link.send({"type": "action", "action": "echo_buy", "item": key})
        items = [(label, buy(key) if key else (lambda: None))
                 for label, key in accounts.echo_shop_rows(self.echo_shop_data.get("unlocks", {}))]
        items.append(("Close", self._close_echo_shop))
        return items

    def _close_echo_shop(self):
        self.echo_shop_open = False

    def _minimap_button_click(self, pos):
        mm = self._current_minimap()
        if mm is None or mm.full_map_open:
            return False
        for rect, delta in minimap.corner_zoom_button_rects():
            if rect.collidepoint(pos):
                mm.adjust_corner_zoom(delta)
                return True
        return False

    def _zoom_minimap(self, delta):
        mm = self._current_minimap()
        if mm is None:
            return
        if mm.full_map_open:
            mm.adjust_zoom(delta)
        else:
            mm.adjust_corner_zoom(delta)

    def _use_ability(self):
        if not self.you:
            return
        target = self.cam.inverse(pygame.mouse.get_pos())
        self.link.send({"type": "action", "action": "use_ability", "target": [target.x, target.y]})

    def _context_action(self):
        """F: fish near water in the Realm/Bonus room, or wish at the Nexus fountain -
        server is authoritative for both (range/tile checks happen there too)."""
        action = "wish" if self.zone == "nexus" else "fish"
        self.link.send({"type": "action", "action": action})

    def _handle_chat_key(self, event):
        """Keys while the chat input line is open - see game/chat_input.py (cursor,
        partial selection, Ctrl+A/C/X/V, Up/Down history of what you sent)."""
        ci = self.chat_in
        ci.sync_from(self.chat_buffer)
        result = ci.handle_key(event)
        self.chat_buffer = ci.text
        self._chat_select_all = ci.all_selected()
        if result == "submit":
            ci.remember(self.chat_buffer.strip())
            self._submit_chat()
            ci.set_text("")
        elif result == "cancel":
            self.chat_open = False
            self.chat_buffer = ""
            self._chat_select_all = False
            ci.set_text("")

    def _chat_log_mouse_down(self, pos):
        """Left press on the chat log: its top strip moves the panel, anywhere else
        starts a line selection (copy with Ctrl+C) - never opens chat mode."""
        if ui.chat_log_handle_rect(self.chat_log).collidepoint(pos):
            self.panel_drag.down("chat", pos)
            return
        hit = ui.chat_log_line_at(self.chat_log, self.chat_scroll, pos)
        if hit is not None:
            self.chat_log_sel.begin(hit[0])

    def _chat_mouse_event(self, event):
        """Mouse handling for the chat input line (click places the cursor, drag
        selects) and for extending a chat-log selection. True = event consumed."""
        if self.chat_open and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if ui.chat_box_rect().collidepoint(event.pos):
                ci = self.chat_in
                ci.sync_from(self.chat_buffer)
                tx, first = ui.chat_box_text_origin(ci.text, ci.cursor)
                ci.mouse_down(ci.index_at(ui._FONT_M, tx, event.pos[0], first))
                self._chat_box_dragging = True
                return True
        if event.type == pygame.MOUSEMOTION:
            if getattr(self, "_chat_box_dragging", False) and self.chat_open:
                ci = self.chat_in
                tx, first = ui.chat_box_text_origin(ci.text, ci.cursor)
                ci.mouse_drag(ci.index_at(ui._FONT_M, tx, event.pos[0], first))
                self._chat_select_all = ci.all_selected()
            if self.chat_log_sel.dragging:
                hit = ui.chat_log_line_at(self.chat_log, self.chat_scroll, event.pos)
                if hit is not None:
                    self.chat_log_sel.extend(hit[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if getattr(self, "_chat_box_dragging", False):
                self._chat_box_dragging = False
                return True
            self.chat_log_sel.finish()
        return False

    def _copy_chat_selection(self):
        if self.chat_log_sel.copy(self.chat_log):
            self._chat_notice("Copied chat to the clipboard")

    def _chat_notice(self, text):
        self.feed.insert(0, [text, (190, 220, 255), 4.0])
        self.feed = self.feed[:4]
    def _submit_chat(self):
        text = self.chat_buffer.strip()
        self.chat_open = False
        self.chat_buffer = ""
        if not text:
            return
        if text.startswith("/"):
            self._handle_chat_command(text[1:])
        else:
            self.link.send({"type": "chat", "text": text})

    def _handle_chat_command(self, cmd_text):
        parts = cmd_text.split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        if cmd == "nexus":
            action = "leave_bonus" if self.zone == "bonus" else "goto_nexus"
            if self.zone != "nexus":
                self.link.send({"type": "action", "action": action})
        elif cmd == "realm" and self.zone == "nexus":
            self.link.send({"type": "action", "action": "goto_realm"})
        elif cmd == "vault" and self.zone == "nexus":
            self.link.send({"type": "action", "action": "goto_vault_room"})
        elif cmd == "bazaar" and self.zone == "nexus":
            self.link.send({"type": "action", "action": "goto_bazaar"})
        elif cmd == "trade":
            self.link.send({"type": "action", "action": "trade_request"})
        elif cmd == "accept":
            self.link.send({"type": "action", "action": "trade_invite_accept"})
        elif cmd == "decline":
            self.link.send({"type": "action", "action": "trade_invite_decline"})
        elif cmd in ("w", "msg", "whisper", "tell"):
            name_part, message = _split_msg_target(parts[1] if len(parts) > 1 else "")
            if not name_part or not message:
                self.feed.insert(0, ['Usage: /msg <name> <message>  (or /msg "two words" <message>)',
                                     (220, 150, 90), 4.0])
                self.feed = self.feed[:4]
            else:
                # the server looks the name up across EVERY zone, so this reaches players
                # in the Realm, a dungeon, the Vault... not just whoever is on screen
                self.link.send({"type": "action", "action": "whisper", "name": name_part, "text": message})
        elif cmd == "crew":
            self._handle_crew_command(parts[1] if len(parts) > 1 else "")
        elif cmd == "help":
            self.feed.insert(0, ["Commands: /nexus /realm /vault /bazaar /trade /accept /decline /crew /w <name> <msg>",
                                  (200, 200, 215), 4.0])
            self.feed = self.feed[:4]
        else:
            self.feed.insert(0, [f"Unknown command: /{cmd}", (220, 120, 120), 4.0])
            self.feed = self.feed[:4]

    def _handle_crew_command(self, rest):
        sub_parts = rest.split(maxsplit=1)
        sub = sub_parts[0].lower() if sub_parts else ""
        arg = sub_parts[1].strip() if len(sub_parts) > 1 else ""
        if sub == "create" and arg:
            crews.create_crew(arg, self.name)
            self.crew_name = arg
            self.feed.insert(0, [f"Crew '{arg}' created.", (200, 220, 255), 4.0])
        elif sub == "join" and arg:
            crew = crews.join_crew(arg, self.name)
            if crew:
                self.crew_name = arg
                self.feed.insert(0, [f"Joined crew '{arg}'.", (200, 220, 255), 4.0])
            else:
                self.feed.insert(0, [f"No crew named '{arg}'.", (220, 150, 90), 4.0])
        elif sub == "leave":
            if self.crew_name:
                crews.leave_crew(self.crew_name, self.name)
                self.feed.insert(0, [f"Left crew '{self.crew_name}'.", (200, 220, 255), 4.0])
                self.crew_name = ""
            else:
                self.feed.insert(0, ["You're not in a crew.", (220, 150, 90), 4.0])
        else:
            self.feed.insert(0, ["Usage: /crew create <name> | /crew join <name> | /crew leave",
                                  (220, 150, 90), 4.0])
        self.feed = self.feed[:4]

    def _current_minimap(self):
        if self.zone == "realm":
            return self.realm_minimap
        if self.zone == "bonus":
            return self.bonus_minimap
        if self.zone == "nexus":
            return self.nexus_minimap
        if self.zone == "bazaar":
            return self.bazaar_minimap
        if self.zone == "vault_room":
            return self.vault_room_minimap
        return None

    def _map_open(self):
        mm = self._current_minimap()
        return mm is not None and mm.full_map_open

    BAG_AUTO_CLOSE_RADIUS = 220  # walk this far from an open bag and its window auto-closes

    def _current_bag_list(self):
        if self.zone in ("realm", "bonus"):
            return self.ground_items
        if self.zone == "bazaar":
            return self.bazaar_ground_items
        return []

    def _current_bag(self):
        """The (ghost) Bag backing the open drag-and-drop window, or None - also
        handles auto-close (walked away, or the bag emptied/expired from under us)."""
        if self.open_bag_id is None or self.you is None:
            return None
        bag = next((g for g in self._current_bag_list() if g.id == self.open_bag_id), None)
        if bag is None or bag.pos.distance_to(self.you.pos) > self.BAG_AUTO_CLOSE_RADIUS:
            self.open_bag_id = None
            self.bag_items = []
            return None
        return bag

    def _peer_near_mouse(self, screen_pos, radius=40):
        """Nearest peer whose on-screen position is within `radius` px of the
        cursor - used so right-click opens a context menu for "whatever player
        I'm pointing at" instead of needing an exact click on their sprite."""
        nearest, best = None, radius
        for peer in self.peers:
            sx, sy = self.cam(peer.pos)
            d = math.hypot(sx - screen_pos[0], sy - screen_pos[1])
            if d <= best:
                nearest, best = peer, d
        return nearest

    def _nearby_players(self):
        """[(name, dist, pid), ...] sorted nearest-first, within NEARBY_PLAYER_RADIUS -
        peers are already sent unfiltered-by-distance for your zone, so this is a
        pure client-side filter/sort, no new network traffic."""
        if self.you is None:
            return []
        out = []
        for peer in self.peers:
            d = peer.pos.distance_to(self.you.pos)
            if d <= NEARBY_PLAYER_RADIUS:
                out.append((peer.name, d, peer.pid))
        out.sort(key=lambda e: e[1])
        return out

    def _friends_status(self):
        """[(name, online_bool, pid_or_None), ...] - online means "currently a
        peer I can see" (same zone, within server-sent range), not literally
        "connected to the server" (co-op has no separate presence system)."""
        peer_by_name = {pe.name: pe for pe in self.peers}
        out = []
        for fname in self.friends:
            peer = peer_by_name.get(fname)
            out.append((fname, peer is not None, peer.pid if peer else None))
        return out

    def _open_context_menu_for(self, peer, screen_pos):
        self.context_menu = {"pid": peer.pid, "name": peer.name, "pos": screen_pos}

    def _chat_name_right_click(self, pos):
        """Right-click a player's name in the chat log -> the same player menu as
        right-clicking them in the world (RotMG-style). True if a name was hit."""
        hit = ui.chat_log_line_at(self.chat_log, self.chat_scroll, pos)
        if hit is None or hit[2] is None or not hit[2].collidepoint(pos):
            return False
        entry = self.chat_log[hit[1]]
        name = entry.get("sender")
        if not name:
            return False
        peer = next((pe for pe in self.peers if pe.name == name), None)
        self.context_menu = {"pid": peer.pid if peer else entry.get("pid"), "name": name, "pos": pos,
                             "here": peer is not None}
        return True

    def _context_menu_disabled(self):
        """Menu rows that need the player to be right here (same zone, on screen)."""
        if self.context_menu is None or self.context_menu.get("here", True):
            return ()
        return ("Trade", "Inspect", "Teleport", "Invite to Crew")

    def _context_menu_labels(self):
        name = self.context_menu["name"]
        labels = ["Chat", "Trade", "Inspect", "Teleport", "Remove Friend" if name in self.friends else "Add Friend"]
        if self.crew_name:
            labels.append("Invite to Crew")
        return labels

    def _context_menu_click(self, pos):
        menu = self.context_menu
        labels = self._context_menu_labels()
        disabled = self._context_menu_disabled()
        self.context_menu = None
        labels = [lb if lb not in disabled else None for lb in labels]
        rects = ui.context_menu_rects(menu["pos"], labels)
        for rect, label in zip(rects, labels):
            if not rect.collidepoint(pos):
                continue
            if label == "Chat":
                self.chat_open = True
                self.chat_buffer = f"/w {menu['name']} "
            elif label == "Trade":
                self.link.send({"type": "action", "action": "trade_request", "pid": menu["pid"]})
            elif label == "Teleport":
                self.link.send({"type": "action", "action": "tp_to_player", "pid": menu["pid"]})
            elif label == "Inspect":
                self.inspect_pid = menu["pid"]
            elif label == "Invite to Crew":
                # crews are joined by name (see _handle_crew_command) - an invite is just a
                # whisper telling them the exact command, no separate server-side crew state
                self.link.send({"type": "action", "action": "whisper", "pid": menu["pid"],
                                "text": f"[Crew invite] Join my crew with: /crew join {self.crew_name}"})
            elif label == "Add Friend":
                self.friends = friends.add_friend(self.name, menu["name"])
            elif label == "Remove Friend":
                self.friends = friends.remove_friend(self.name, menu["name"])
            return

    def _nearby_players_click(self, pos, rows):
        for row_rect, tp_rect, pid in rows:
            if tp_rect.collidepoint(pos):
                self.link.send({"type": "action", "action": "tp_to_player", "pid": pid})
                return True
            if row_rect.collidepoint(pos):
                return True  # consume the click even off the TP button, so it doesn't fall through
        return False

    def _friends_panel_click(self, pos):
        if ui.friends_close_button_rect().collidepoint(pos):
            self.friends_panel_open = False
            return
        # draw_friends_panel's own layout is recomputed here purely for hit-testing -
        # it's only actually easy to get the rects back from a real draw call, and
        # this fires on click (not every frame), so recomputing is cheap
        status = self._friends_status()
        y0 = ui.friends_panel_rect().y + 46
        row_h = 34
        for i, (fname, online, pid) in enumerate(status):
            ry = y0 + i * row_h
            row_rect = pygame.Rect(ui.friends_panel_rect().x + 8, ry, ui.FRIENDS_PANEL_W - 16, row_h - 4)
            bw = 48
            tp_rect = pygame.Rect(row_rect.right - bw * 3 - 12, row_rect.y + 2, bw, row_rect.h - 4)
            trade_rect = pygame.Rect(row_rect.right - bw * 2 - 8, row_rect.y + 2, bw, row_rect.h - 4)
            remove_rect = pygame.Rect(row_rect.right - bw - 4, row_rect.y + 2, bw, row_rect.h - 4)
            if online and tp_rect.collidepoint(pos):
                self.link.send({"type": "action", "action": "tp_to_player", "pid": pid})
                return
            if online and trade_rect.collidepoint(pos):
                self.link.send({"type": "action", "action": "trade_request", "pid": pid})
                return
            if remove_rect.collidepoint(pos):
                self.friends = friends.remove_friend(self.name, fname)
                return

    def _dock_mode(self):
        """The right dock's effective Tab mode - falls back to inventory with no pet."""
        if self.right_panel_mode == "pet" and getattr(self.you, "pet", None) is not None:
            return "pet"
        return "inventory"

    def _slot_at(self, pos):
        if self.vault_chest_open is not None and self.zone == "vault_room":
            lo = self.vault_chest_open * VAULT_CHEST_SIZE
            for i, rect in enumerate(ui.vault_chest_slot_rects(self._vault_chest_screen_pos())):
                if rect.collidepoint(pos):
                    return ("vault", lo + i)
        bag = self._current_bag()
        if bag is not None:
            for i, rect in enumerate(ui.bag_slot_rects(self.cam(bag.pos))):
                if rect.collidepoint(pos):
                    return ("bag", i)
        pet_rect = ui.pet_feed_target_rect(self.you, self._dock_mode()) if self.you else None
        if pet_rect is not None and pet_rect.collidepoint(pos):
            return ("pet", None)
        for rect, slot_type in ui.equip_slot_rects():
            if rect.collidepoint(pos):
                return ("equip", slot_type)
        for i, rect in enumerate(ui.backpack_slot_rects(self.you)):
            if rect.collidepoint(pos):
                return ("backpack", i)
        return None

    def _dragged_item(self):
        if self.drag_from is None or self.you is None:
            return None
        kind, key = self.drag_from
        if kind == "backpack":
            return self.you.backpack[key] if key < len(self.you.backpack) else None
        if kind == "bag":
            return self.bag_items[key] if key < len(self.bag_items) else None
        if kind == "vault":
            return self.vault_items[key] if key < len(self.vault_items) else None
        return getattr(self.you, key)

    def _inventory_mouse_down(self, pos):
        """Picks up whatever's in the clicked slot so it can be dragged. The server stays
        authoritative - this only decides what to send on mouse-up, nothing is mutated
        locally, so the dragged icon simply reflects state until the next snapshot lands."""
        slot = self._slot_at(pos)
        if slot is None:
            return
        kind, key = slot
        if (kind == "backpack" and key < len(self.you.backpack)
                and pygame.key.get_mods() & pygame.KMOD_SHIFT and self._shift_click(key)):
            return
        if kind == "backpack":
            has_item = key < len(self.you.backpack)
        elif kind == "bag":
            has_item = key < len(self.bag_items)
        elif kind == "vault":
            has_item = key < len(self.vault_items) and self.vault_items[key] is not None
        elif kind == "pet":
            has_item = False  # the pet panel is a drop TARGET only (feed an item onto it) -
            # there's nothing to pick UP and drag out of it
        else:
            has_item = getattr(self.you, key) is not None
        if has_item:
            self.drag_from = slot
            self.drag_start_pos = pos
            self._ui_click_active = True
            self.pending_socket = None  # a fresh drag cancels an unconfirmed socket request

    def _shift_click(self, idx):
        """Shift+click a backpack item: deposit into the open Vault / Bazaar chest, or
        offer it in the open trade. Returns True if it did something."""
        if self.vault_chest_open is not None:
            self.link.send({"type": "action", "action": "vault_deposit", "idx": idx})
        elif self.trade is not None:
            self.link.send({"type": "action", "action": "trade_offer", "idx": idx})
        elif isinstance(self._current_bag(), GhostChest):
            self.link.send({"type": "action", "action": "chest_deposit", "bag_id": self.open_bag_id, "idx": idx})
        else:
            return False
        self._ui_click_active = True
        return True

    def _trade_invite_click(self, pos):
        accept_rect, decline_rect = ui.trade_invite_button_rects()
        if accept_rect.collidepoint(pos):
            self.link.send({"type": "action", "action": "trade_invite_accept"})
        elif decline_rect.collidepoint(pos):
            self.link.send({"type": "action", "action": "trade_invite_decline"})
        else:
            return False
        self.trade_invite = None  # hide at once; the next snapshot confirms
        return True

    def _apply_pending_socket(self):
        if self.pending_socket is None:
            return
        i, j = self.pending_socket
        self.pending_socket = None
        self.link.send({"type": "action", "action": "socket_proc", "idx": i, "target_idx": j})

    def _try_open_vault_chest(self):
        """F / Enter next to a vault-room chest asks the server to open it."""
        if not self.you or self.zone != "vault_room":
            return False
        near = vault.nearest_chest(self.vault_room_map, self.you.pos)
        if near is None:
            return False
        self.link.send({"type": "action", "action": "open_vault"})
        return True

    def _close_vault_chest(self):
        self.vault_chest_open = None
        self._cancel_drag()

    def _vault_chest_screen_pos(self):
        wpos = vault.chest_world_pos(self.vault_room_map, self.vault_chest_open or 0)
        return ui.vault_chest_window_anchor(self.cam(wpos) if wpos is not None
                                            else (C.SCREEN_W // 2, C.SCREEN_H // 2))

    def _vault_mouse_up(self, pos):
        """Vault <-> backpack drag-and-drop (or a plain click) - server stays
        authoritative, this only decides which action to send."""
        origin = self.drag_from
        self.drag_from = None
        if origin is None or not self.you or self.drag_start_pos is None:
            return
        dest = self._slot_at(pos)
        dropped_far = math.hypot(pos[0] - self.drag_start_pos[0], pos[1] - self.drag_start_pos[1]) > 6
        if origin[0] != "vault" and dropped_far and (dest is None or dest[0] != "vault"):
            self.drag_from = origin  # an ordinary inventory move while a chest happens to be open
            self._inventory_mouse_up(pos)
            return
        if origin[0] == "backpack":
            idx = origin[1]
            if idx < len(self.you.backpack) and (not dropped_far or (dest is not None and dest[0] == "vault")):
                msg = {"type": "action", "action": "vault_deposit", "idx": idx}
                if dropped_far and dest is not None and dest[0] == "vault":
                    msg["target_idx"] = dest[1]  # a specific slot - server swaps if it's occupied
                self.link.send(msg)
        elif origin[0] == "vault":
            idx = origin[1]
            if (idx < len(self.vault_items) and self.vault_items[idx] is not None
                    and (not dropped_far or (dest is not None and dest[0] == "backpack"))):
                msg = {"type": "action", "action": "vault_withdraw", "idx": idx}
                if dropped_far and dest is not None and dest[0] == "backpack":
                    msg["target_idx"] = dest[1]
                self.link.send(msg)

    def _inventory_mouse_up(self, pos):
        origin = self.drag_from
        self.drag_from = None
        if origin is None or self.you is None or self.drag_start_pos is None:
            return
        dest = self._slot_at(pos)
        dropped_far = math.hypot(pos[0] - self.drag_start_pos[0], pos[1] - self.drag_start_pos[1]) > 6
        if self.trade is not None and origin[0] == "backpack":
            # trade open: a plain click or a drop onto "my offer" offers the item (it stays in
            # the backpack, highlighted, until the swap); anywhere else off the dock does nothing -
            # never a ground drop while the trade window covers the screen
            if not dropped_far or ui.trade_my_offer_area_rect().collidepoint(pos):
                if origin[1] < len(self.you.backpack):
                    self.link.send({"type": "action", "action": "trade_offer", "idx": origin[1]})
                return
            if dest is None:
                return
        if origin[0] == "bag":
            # bag -> backpack/equip only (never back into a ground bag) - a plain
            # click on a bag slot is also a quick withdraw
            if not dropped_far or (dest is not None and dest[0] in ("backpack", "equip")):
                if origin[1] < len(self.bag_items):
                    msg = {"type": "action", "action": "bag_withdraw",
                           "bag_id": self.open_bag_id, "idx": origin[1]}
                    if dest is not None and dest[0] == "backpack" and dropped_far:
                        msg["target_idx"] = dest[1]  # server swaps with whatever's already there
                    self.link.send(msg)
            return
        if not dropped_far or dest == origin:
            # a plain click (no real drag) no longer equips/uses by itself - that's now a
            # DOUBLE click; single click is reserved for picking the item up to drag and
            # (via _trade_click, a separate handler entirely) trade-offering
            if not dropped_far and origin[0] == "backpack" and origin[1] < len(self.you.backpack):
                self._ui_click_active = True
                now = pygame.time.get_ticks()
                if self._dblclick_slot == origin and now - self._dblclick_time <= self.DBLCLICK_MS:
                    self.link.send({"type": "action", "action": "equip", "idx": origin[1]})
                    self._dblclick_slot = None
                else:
                    self._dblclick_slot = origin
                    self._dblclick_time = now
            return
        if dest is None:
            # dragged clean off the inventory bar, into the play area - drop it on the ground
            # (server is authoritative - it decides whether this zone allows dropping)
            kind, key = origin
            if kind == "backpack":
                self.link.send({"type": "action", "action": "drop_item", "idx": key})
            else:
                self.link.send({"type": "action", "action": "drop_item", "slot": key})
            if self.zone in ("realm", "bonus", "bazaar"):
                audio.play_drop()  # optimistic like the shoot-sound estimate - server is authoritative
            return
        if origin[0] == "backpack" and dest[0] == "backpack":
            i, j = origin[1], dest[1]
            bp = self.you.backpack if self.you else []
            if i < len(bp) and j < len(bp) and i != j:
                src, tgt = bp[i], bp[j]
                if tgt.slot == SLOT_WEAPON and identify_proc_kind(src) is not None:
                    # destructive (consumes src) - requires an explicit ENTER confirm,
                    # matching main.py's single-player flow, see _apply_pending_socket
                    self.pending_socket = (i, j)
                    self.feed.insert(0, [f"Press ENTER to socket {src.name}'s proc onto {tgt.display_name} "
                                          f"(consumes {src.name})", (200, 180, 255), 6.0])
                    self.feed = self.feed[:4]
                    return
            self.link.send({"type": "action", "action": "swap_backpack", "i": i, "j": j})
        elif origin[0] == "backpack" and dest[0] == "equip":
            self.link.send({"type": "action", "action": "equip", "idx": origin[1], "slot": dest[1]})
        elif origin[0] == "equip" and dest[0] == "backpack":
            self.link.send({"type": "action", "action": "unequip", "slot": origin[1]})
        elif origin[0] == "backpack" and dest[0] == "pet":
            self.link.send({"type": "action", "action": "feed_pet", "idx": origin[1]})
        elif origin[0] == "backpack" and dest[0] == "bag":
            # deposit INTO the open container - server rejects this unless it's
            # actually a BazaarChest (see server.py's "chest_deposit" handler)
            if origin[1] < len(self.you.backpack):
                self.link.send({"type": "action", "action": "chest_deposit",
                                 "bag_id": self.open_bag_id, "idx": origin[1]})

    def _class_select_key(self, key):
        cols, n = ui._CLASS_COLS, len(ui.CLASS_ORDER)
        if key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.select_idx = (self.select_idx + (1 if key == pygame.K_RIGHT else -1)) % n
        elif key in (pygame.K_UP, pygame.K_DOWN):
            new_idx = self.select_idx + (cols if key == pygame.K_DOWN else -cols)
            if 0 <= new_idx < n:
                self.select_idx = new_idx
        elif key == pygame.K_RETURN:
            self._connect(ui.CLASS_ORDER[self.select_idx])

    def _send_respawn(self):
        self.link.send({"type": "action", "action": "respawn", "cls": ui.CLASS_ORDER[self.select_idx]})
        self._last_level = 1
        self._prev_backpack_len = 0
        self._prev_boss_active = False

    def _play_key(self, key):
        if self.zone == "dead":
            if key == pygame.K_RETURN:
                self._send_respawn()
            return
        if key == pygame.K_r and self.zone in ("realm", "bazaar", "vault_room", "bonus"):
            action = "leave_bonus" if self.zone == "bonus" else "goto_nexus"
            self.link.send({"type": "action", "action": action})
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.portal_prompt and self.zone in ("realm", "bonus"):
            self.link.send({"type": "action", "action": "enter_portal"})
        elif key == pygame.K_f and self.zone in ("nexus", "realm", "bonus"):
            self._context_action()
        elif key == pygame.K_j:
            self.quest_log_expanded = not self.quest_log_expanded
        elif key == pygame.K_i and self.zone in ("realm", "bonus"):
            self._set_auto_fire(not self.auto_fire_enabled)
            self.feed.insert(0, [f"Auto-fire {'ON' if self.auto_fire_enabled else 'OFF'}",
                                  (150, 220, 255) if self.auto_fire_enabled else (170, 170, 180), 4.0])
            self.feed = self.feed[:4]
        elif key == pygame.K_TAB and self.zone in ("nexus", "bazaar", "realm", "bonus"):
            self.right_panel_mode = "pet" if self.right_panel_mode == "inventory" else "inventory"
        elif pygame.K_1 <= key <= pygame.K_8:
            self.link.send({"type": "action", "action": "equip", "idx": key - pygame.K_1})
        elif key == pygame.K_l:
            self.friends_panel_open = not self.friends_panel_open
            self.context_menu = None

    def _trade_click(self, pos):
        if not self.you or self.trade is None:
            return
        if ui.trade_accept_button_rect().collidepoint(pos):
            self.link.send({"type": "action", "action": "trade_accept"})
            return
        if ui.trade_cancel_button_rect().collidepoint(pos):
            self.link.send({"type": "action", "action": "trade_cancel"})
            return
        for i, rect in enumerate(ui.trade_offer_slot_rects(mine=True)):
            if rect.collidepoint(pos) and i < len(self.trade["my_offer"]):
                self.link.send({"type": "action", "action": "trade_withdraw", "idx": i})
                return
        self._inventory_mouse_down(pos)  # backpack: click or drag onto "my offer" (see _inventory_mouse_up)

    def _connect(self, cls_name):
        self.state = STATE_CONNECTING
        self.draw()
        self._present()
        try:
            sock = socket.create_connection((self.host, self.port), timeout=5)
        except OSError as e:
            self.error_msg = f"Could not connect to {self.host}:{self.port} - {e}"
            self.state = STATE_ERROR
            return
        self.link = NetLink(sock)
        self.link.send({"type": "join", "name": self.name, "cls": cls_name})
        waited = 0.0
        while self.link.welcome_pid is None and self.link.error is None and waited < 5.0:
            pygame.time.wait(50)
            waited += 0.05
        if self.link.welcome_pid is None:
            self.error_msg = self.link.error or "server did not respond"
            self.state = STATE_ERROR
            return
        self.state = STATE_PLAY

    # ------------------------------------------------------------- update --
    ROTATE_SPEED_DEG = 120  # RotMG has a real Q/E camera-rotate feature; this matches its feel

    _THEME_ZONE_FOR_ZONE = {"nexus": "nexus", "bazaar": "bazaar", "vault_room": "nexus",
                             "realm": "realm", "bonus": "dungeon"}

    def update(self, dt):
        if self.state == STATE_INTRO:
            self.intro_timer += dt
            if self.intro_timer >= ui.INTRO_DURATION:
                self.state = STATE_CLASS_SELECT
            return
        if self.state != STATE_PLAY:
            return
        if self.link.error:
            self.error_msg = f"Disconnected: {self.link.error}"
            self.state = STATE_ERROR
            return

        # title card on entering a new place + that place's own ~60s track (the realm
        # follows the biome/area/island under you, with dwell hysteresis) - see game/zone_banner.py
        place = self._current_place()
        if place is not None:
            track = self.zone_tracker.observe(dt, *place)
            if track:
                audio.play_theme(track)
        audio.update_music()

        if not self.chat_open and not self.help_open and not self.quit_confirm_open and not self.journal.is_open():
            keys = pygame.key.get_pressed()
            if keys[pygame.K_q]:
                self.cam.rotate(-self.ROTATE_SPEED_DEG * dt)
            if keys[pygame.K_e]:
                self.cam.rotate(self.ROTATE_SPEED_DEG * dt)

        snap = self.link.get_snapshot()
        if snap:
            self._apply_snapshot(snap)
            self._send_input(dt)

        for w in self.link.pop_whispers():
            if w.get("error"):
                self._chat_notice(w["error"])
            elif w.get("echo"):
                self.chat_log.append({"name": f"You -> {w['to']}", "text": w["text"], "age": 0.0,
                                      "sender": w["to"]})
            else:
                self.chat_log.append({"name": f"{w['from']} (whisper)", "text": w["text"], "age": 0.0,
                                      "sender": w["from"]})
            self.chat_log = self.chat_log[-ui.CHAT_LOG_STORE_CAP:]

        vfx.update(dt)
        dx, dy = vfx.shake_offset(dt)
        self.cam.pos.x += dx
        self.cam.pos.y += dy
        if self.zone == "nexus":
            self.nexus_ambience.update(dt, self.nexus_map.bounds())

        if self.zone in ("realm", "bonus") and self.tilemap and self.you:
            tile_here = self.tilemap.tile_at(self.you.pos.x, self.you.pos.y)
            self.weather_fx.update(dt, world.weather_for_tile(tile_here))
            self._dust_cd = max(0.0, self._dust_cd - dt)
            if (self._dust_cd <= 0 and self._prev_you_pos is not None
                    and self.you.pos.distance_to(self._prev_you_pos) > 2):
                self._dust_cd = 0.15
                ground_color = world.TILE_COLORS.get(tile_here, (150, 140, 120))
                vfx.spawn_dust((self.you.pos.x, self.you.pos.y + 14), ground_color)
            self._prev_you_pos = pygame.Vector2(self.you.pos)
            if self.zone == "realm":
                # bonus dungeons get their ambient from the server's RealmSim (via
                # sim.vfx_events, already dispatched below) - the open Realm's is
                # purely client-side/cosmetic, keyed off the LOCAL player's biome
                biome_name = world.TILE_TO_BIOME_NAME.get(tile_here)
                bounds = (self.you.pos.x - 300, self.you.pos.y - 300,
                          self.you.pos.x + 300, self.you.pos.y + 300)
                self.realm_ambience.update(dt, bounds, kinds=vfx.REALM_AMBIENT_KINDS.get(biome_name))
        else:
            self.weather_fx.update(dt, None)

        if self.nexus_bot is not None:
            self.nexus_bot.speech_age += dt

        wr = self.link.pop_wish_result()
        if wr is not None:
            if wr.get("error"):
                self.feed.insert(0, [wr["error"], (220, 150, 90), 4.0])
            else:
                verdict = ("JACKPOT!" if wr["is_ut"] else
                           "Upgrade!" if wr["upgrade"] else "Sidegrade" if wr["same_tier"] else "Downgrade...")
                color = tuple(wr["new_color"])
                label = f"{wr['old_name']} -> {wr['new_name']} ({verdict})"
                self.feed.insert(0, [label, color, 4.0])
                audio.play_wish(wr["is_ut"])
            self.feed = self.feed[:4]

        for notice in self.link.pop_trade_notices():
            self.feed.insert(0, [notice, (230, 210, 150), 4.0])
            self.feed = self.feed[:4]

        for st in self.link.pop_echo_shop_states():
            self.echo_shop_data = st
            if st.get("message"):
                self.feed.insert(0, [st["message"], (150, 230, 210) if st.get("ok") else (220, 150, 90), 4.0])
                self.feed = self.feed[:4]

        for pr in self.link.pop_pet_results():
            self.feed.insert(0, [pr.get("message", ""), tuple(pr.get("color", (170, 220, 255))), 4.0])
            self.feed = self.feed[:4]
            if pr.get("fused") and self.you is not None:
                pos = self.you.pos
                vfx.spawn_burst(pos, (255, 120, 220), count=40, speed=(60, 230), life=(0.5, 1.0), radius=(2, 5))
                vfx.spawn_ring(pos, (255, 200, 255), max_radius=90, life=0.6)
                vfx.trigger_shake(0.25, 4)
                audio.play_levelup()

        sr = self.link.pop_socket_result()
        if sr is not None:
            color = (150, 220, 150) if sr.get("ok") else (220, 150, 90)
            self.feed.insert(0, [sr.get("message", ""), color, 4.0])
            self.feed = self.feed[:4]

        if self.story_banner is not None:
            self.story_banner[1] -= dt
            if self.story_banner[1] <= 0:
                self.story_banner = None
        if self.credits_t is not None:
            self.credits_t += dt
            if ui.credits_finished(self.credits_t):
                self.credits_t = None
        for m in self.feed:
            m[2] -= dt
        self.feed = [m for m in self.feed if m[2] > 0]
        for pt in self.portals:
            pt.t += dt
        for pop in self.popups:
            pop["age"] += dt
        self.popups = [pop for pop in self.popups if pop["age"] < ui.DAMAGE_POPUP_LIFETIME]
        for b in self._speech_bubbles:
            b["age"] += dt
        self._speech_bubbles = [b for b in self._speech_bubbles if b["age"] < SPEECH_BUBBLE_LIFETIME]
        for m in self.chat_log:
            m["age"] += dt
        self.chat_log = [m for m in self.chat_log if m["age"] < CHAT_LOG_LIFETIME]

    def _apply_snapshot(self, snap):
        ev = snap.get("live_event")
        if ev != getattr(self, "live_event", ev):
            label = live_events.label_for(ev)
            self.feed.insert(0, [f"Live event started: {label}" if label else "The live event has ended",
                                 (255, 220, 120), 5.0])
            self.feed = self.feed[:4]
        self.live_event = ev
        if snap["zone"] != self.zone:
            self.echo_shop_open = False
            self._cancel_drag()  # a drag must never survive a zone change (portal/death/nexus)
            self.inspect_pid = None
        self.zone = snap["zone"]
        if self.zone == "dead":
            if self.death_info is None:  # just arrived in the dead zone this snapshot
                audio.play_death()
                if self.you is not None:
                    vfx.spawn_burst(self.you.pos, (255, 90, 90), count=24, speed=(60, 220), life=(0.3, 0.65))
            self.death_info = snap.get("death_info")
            return
        self.death_info = None
        new_trade = snap.get("trade")
        if (new_trade is None) != (self.trade is None):
            self._cancel_drag()  # trade window opened/closed under an in-progress drag
        self.trade = new_trade
        self.trade_invite = snap.get("trade_invite")
        self.quest_log = snap.get("quest_log")
        pop_story = getattr(self.link, "pop_story", None)
        story_feed, story_banners = pop_story() if pop_story else ([], [])
        for msg, color in story_feed:
            self.feed.insert(0, [msg, tuple(color), 5.0])
        for title in story_banners:
            self.story_banner = [f"{title} - COMPLETE", 5.0]
            audio.play_levelup()
            if title == story.ACTS[-1]["title"]:
                self.credits_t = 0.0
        you = Player.from_full_state(snap["you"])
        if you.level > self._last_level:
            audio.play_levelup()
            vfx.dispatch([("levelup", you.pos.x, you.pos.y, (255, 215, 90))])
        self._last_level = you.level
        self.you = you
        self.peers = [Player.from_net_state(d) for d in snap.get("players", [])]
        for pid, text in snap.get("chats", []):
            self._speech_bubbles.append({"pid": pid, "text": text, "age": 0.0})
            speaker = "You" if pid == you.pid else next((pe.name for pe in self.peers if pe.pid == pid), "???")
            self.feed.insert(0, [f"{speaker}: {text}", (190, 220, 255), 4.0])
            self.chat_log.append({"name": speaker, "text": text, "age": 0.0,
                                  "sender": None if pid == you.pid else speaker, "pid": pid})
        self.feed = self.feed[:4]
        self.chat_log = self.chat_log[-ui.CHAT_LOG_STORE_CAP:]
        vault, chest_hint = self.link.pop_vault_items()
        if vault is not None:
            from game.items import Item
            self.vault_items = [(Item.from_json(d) if d is not None else None) for d in vault]
            if chest_hint is not None:
                if self.vault_chest_open != chest_hint:
                    self._cancel_drag()
                self.vault_chest = self.vault_chest_open = chest_hint
        bag_state = self.link.pop_bag_state()
        if bag_state is not None:
            from game.items import Item
            self.open_bag_id = bag_state["id"]
            self.bag_items = [Item.from_json(d) for d in bag_state["items"]]
        dmsg = self.link.pop_dialogue()
        if dmsg is not None:
            self.dialogue_view = dmsg.get("view")
            if self.dialogue_view is not None:
                self._cancel_drag()
        self.sidequest_log = snap.get("sidequests") or []
        self.sidequests_done = snap.get("sidequests_done") or []
        self.npcs = [NPC.from_net_state(d) for d in snap.get("npcs", [])]
        self.island_chests = [(pygame.Vector2(d["x"], d["y"]), d.get("skin", 0), d.get("opened", False))
                              for d in snap.get("island_chests", [])]
        bot_data = snap.get("bot")
        self.nexus_bot = GhostBot(bot_data) if bot_data else None
        if self.nexus_bot is not None and self.nexus_bot.speech and self.nexus_bot.speech != self._last_bot_speech:
            self._last_bot_speech = self.nexus_bot.speech
            self.chat_log.append({"name": self.nexus_bot.name, "text": self.nexus_bot.speech, "age": 0.0})
            self.chat_log = self.chat_log[-ui.CHAT_LOG_STORE_CAP:]
        if self.zone in ("realm", "bonus"):
            # the server only sends the map once per zone-instance - see NetLink's
            # pending_map for why this reads that dedicated buffer instead of
            # snap.get("map") directly (a multi-MB map can arrive a tick or two
            # after the snapshot that announced the zone change)
            pending_map = self.link.pop_pending_map()
            if pending_map is not None:
                self.tilemap = world.TileMap(pending_map)
                if self.zone == "realm":
                    self.realm_minimap = minimap.MinimapState()
                    self.realm_grid = pending_map  # kept for the journal's maps
                    self.realm_areas = self.link.pop_pending_areas()
                else:
                    self.bonus_minimap = minimap.MinimapState()
            mm = self._current_minimap()
            if mm is not None:
                weather_kind = world.weather_for_tile(self.tilemap.tile_at(you.pos.x, you.pos.y))
                mm.reveal(you.pos, radius=weather.reveal_radius_for(weather_kind, minimap.REVEAL_RADIUS_TILES))
            self.enemies = [GhostEnemy(d) for d in snap["enemies"]]
            self.bullets = [GhostBullet(d) for d in snap["bullets"]]
            self.ground_items = [GhostBag(d) for d in snap["ground_items"]]
            self.portals = [GhostPortal(d) for d in snap["portals"]]
            self.obstacles = [GhostObstacle(d) for d in snap.get("obstacles", [])]
            self.portal_prompt = snap.get("portal_prompt", False)
            self.boss_active = snap["boss"]
            self.kill_count = snap["kill_count"]
            self.difficulty = snap.get("difficulty")
            self.theme_name = snap.get("theme_name")
            self.secret_quest = snap.get("secret_quest")
            self.secret_quest_progress = snap.get("secret_quest_progress", 0)
            self.secret_quest_timer = snap.get("secret_quest_timer", 0.0)
            self.secret_quest_target = snap.get("secret_quest_target", 0)
            self.phase2_quest = snap.get("phase2_quest")
            self.phase2_quest_progress = snap.get("phase2_quest_progress", 0)
            self.phase2_quest_target = snap.get("phase2_quest_target", 0)
            self.light_level = snap.get("light_level", 1.0)
            self.blood_moon = snap.get("blood_moon", False)
            if self.boss_active and not self._prev_boss_active:
                audio.play_boss_spawn()
            self._prev_boss_active = self.boss_active
            if len(you.backpack) > self._prev_backpack_len:
                audio.play_pickup()
            self._prev_backpack_len = len(you.backpack)
            for msg, color in snap.get("feed", []):
                self.feed.insert(0, [msg, color, 4.0])
            self.feed = self.feed[:4]
            vfx.dispatch(snap.get("vfx", []))
            for kind, family, sx, sy in snap.get("sound", []):
                # distance-cull, same fix/reasoning as main.py's single-player consumption -
                # otherwise every mob sound anywhere in the shared realm plays at full
                # volume for every player regardless of how far away it actually happened
                if (sx - you.pos.x) ** 2 + (sy - you.pos.y) ** 2 > SOUND_HEARING_RADIUS ** 2:
                    continue
                if kind == "mob_hit":
                    audio.play_mob_hit(family)
                elif kind == "mob_death":
                    audio.play_mob_death(family)
                elif kind == "mob_bark":
                    audio.play_mob_bark(family)
            for kind, text in snap.get("mob_speech", []):
                self.chat_log.append({"name": kind.replace("_", " ").title(), "text": text, "age": 0.0})
            self.chat_log = self.chat_log[-ui.CHAT_LOG_STORE_CAP:]
            hurt = False
            for x, y, amount, color in snap.get("popups", []):
                self.popups.append({"x": x, "y": y, "amount": amount, "color": color, "age": 0.0})
                if list(color) == [255, 90, 90]:
                    hurt = True
            if hurt:
                audio.play_hit()
            # (enemy-hit feedback now comes from the "sound" list above - family-tinted
            # play_mob_hit() instead of one generic play_enemy_hit() for every kind)
        elif self.zone == "bazaar":
            self.bazaar_ground_items = [GhostChest(d) if d.get("is_chest") else GhostBag(d)
                                        for d in snap.get("ground_items", [])]
            if len(you.backpack) > self._prev_backpack_len:
                audio.play_pickup()
            self._prev_backpack_len = len(you.backpack)
        self.cam.follow(self.you.pos)

    def _auto_tile_trigger(self):
        """Walking onto a portal/vault tile triggers it automatically (Enter is now
        chat) - this just sends the same actions the old Enter-key handler did; the
        server independently re-checks the tile before honoring them, so a stale or
        mistaken client-side guess can't actually move you anywhere invalid."""
        if not self.you:
            return
        if self.zone == "nexus":
            tile = self.nexus_map.tile_at(self.you.pos.x, self.you.pos.y)
            if tile == world.PORTAL:
                self.link.send({"type": "action", "action": "goto_realm"})
            elif tile == world.BAZAAR_PORTAL:
                self.link.send({"type": "action", "action": "goto_bazaar"})
            elif tile == world.VAULT_TILE:
                self.link.send({"type": "action", "action": "goto_vault_room"})
            if tile != world.ECHO_KEEPER_TILE:
                self._echo_keeper_armed = True
            elif getattr(self, "_echo_keeper_armed", True) and not self.echo_shop_open:
                # the Echo Keeper: open once per step onto the tile (not every frame after closing)
                self._echo_keeper_armed = False
                self.echo_shop_open, self.echo_shop_selected = True, 0
                self.link.send({"type": "action", "action": "echo_shop_open"})
        elif self.zone == "bazaar":
            if self.bazaar_map.tile_at(self.you.pos.x, self.you.pos.y) == world.PORTAL:
                self.link.send({"type": "action", "action": "goto_nexus"})
        elif self.zone == "vault_room":
            tile = self.vault_room_map.tile_at(self.you.pos.x, self.you.pos.y)
            if tile == world.PORTAL:
                self.vault_chest_open = None
                self.link.send({"type": "action", "action": "goto_nexus"})
            elif self.vault_chest_open is not None:
                wpos = vault.chest_world_pos(self.vault_room_map, self.vault_chest_open)
                if wpos is None or wpos.distance_to(self.you.pos) > C.TILE * 3.5:
                    self._close_vault_chest()  # walked away from it

    def _send_input(self, dt):
        if (self._map_open() or self.chat_open or self.help_open or self.quit_confirm_open or self.echo_shop_open
                or self.dialogue_view is not None or self.journal.is_open()):
            # checking the full map, typing in chat, or browsing the options menu is
            # a modal action - stop sending input while it's up (other players keep
            # moving normally; only yours freezes) so you don't drift/move by accident
            self.link.send({"type": "input", "move": [0.0, 0.0], "aim": [0.0, 0.0], "fire": False, "dash": False})
            self._dash_pending = False
            return
        self._auto_tile_trigger()
        keys = pygame.key.get_pressed()
        move = pygame.Vector2(0, 0)
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            move.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            move.y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move.x += 1
        if move.length_squared() > 0:
            move = move.normalize()
            # WASD is screen-relative ("W" = up on screen) - the server has no idea
            # this client's camera is rotated (Q/E is purely a local viewing
            # convenience), so rotate the intent into world space before it's sent,
            # same fix as the single-player Player.update()'s cam_angle parameter
            if self.cam.angle:
                move = move.rotate(self.cam.angle)

        aim = pygame.Vector2(0, 1)
        if self.you:
            target = self.cam.inverse(pygame.mouse.get_pos())
            direction = target - self.you.pos
            if direction.length_squared() >= 1:
                aim = direction.normalize()
            if self.zone in ("realm", "bonus"):
                weather_kind = None
                if self.tilemap is not None:
                    weather_kind = world.weather_for_tile(self.tilemap.tile_at(self.you.pos.x, self.you.pos.y))
                cone_deg = weather.aim_cone_for(weather_kind, AUTO_AIM_CONE_DEG)
                aim = auto_aim_direction(self.you.pos, aim, self.enemies, cone_deg=cone_deg)
        fire = ((self.auto_fire_enabled or bool(pygame.mouse.get_pressed()[0])) and self.zone in ("realm", "bonus")
                and not self._ui_click_active)
        dash = self._dash_pending
        self._dash_pending = False  # one-shot per keypress, not held-key-repeat like move/fire
        self.link.send({"type": "input", "move": [move.x, move.y], "aim": [aim.x, aim.y], "fire": fire,
                         "dash": dash})

        # the server is authoritative for actual fire timing; this is just a client-side
        # estimate of the same cooldown so the shoot sound paces itself sensibly
        self._local_fire_cd = max(0.0, self._local_fire_cd - dt)
        if fire and self._local_fire_cd <= 0 and self.you:
            audio.play_shoot(self.you.cls_name)
            self._local_fire_cd = self.you.atk_interval()

    # --------------------------------------------------------------- draw --
    def draw(self):
        s = self.screen
        s.fill(C.COL_BG)
        if self.state == STATE_INTRO:
            ui.draw_intro_screen(s, self.intro_timer, self.intro_joke)
        elif self.state == STATE_CLASS_SELECT:
            ui.draw_class_select(s, self.select_idx, mouse_pos=pygame.mouse.get_pos())
            hint = ui._FONT_S.render(f"Will connect to {self.host}:{self.port} as '{self.name}'",
                                      True, (150, 150, 165))
            s.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, C.SCREEN_H - 30))
        elif self.state == STATE_CONNECTING:
            ui.draw_center_text(s, "CONNECTING...", f"{self.host}:{self.port}")
        elif self.state == STATE_ERROR:
            ui.draw_center_text(s, "CONNECTION ERROR", self.error_msg + "  (Enter to go back)", (220, 80, 80))
        elif self.state == STATE_PLAY:
            self._draw_play(s)
        if self.help_open:
            items = self._menu_items()
            self.menu_selected %= len(items)
            ui.draw_help_overlay(s, menu_items=items, selected_idx=self.menu_selected, mouse_pos=pygame.mouse.get_pos())
        if self.echo_shop_open and self.state == STATE_PLAY:
            items = self._echo_shop_items()
            self.echo_shop_selected %= len(items)
            ui.draw_echo_shop_overlay(s, self.echo_shop_data.get("echoes", 0), menu_items=items,
                                       selected_idx=self.echo_shop_selected, mouse_pos=pygame.mouse.get_pos())
        if self.state == STATE_PLAY and self.zone != "dead" and self.dialogue_view is not None:
            ui.draw_dialogue(s, self.dialogue_view, pygame.mouse.get_pos())
        if self.state == STATE_PLAY and self.journal.is_open():
            self.journal.draw(s, self._journal_ctx(), pygame.mouse.get_pos(), 1 / max(1, self.clock.get_fps() or 60))
        if self.state == STATE_PLAY and self.zone != "dead":
            ui.draw_zone_banners(s, self.zone_tracker.visible())
            if self.story_banner is not None:
                ui.draw_story_banner(s, self.story_banner[0], self.story_banner[1])
            if self.credits_t is not None:
                ui.draw_credits(s, self.credits_t)
        if self.quit_confirm_open:
            ui.draw_quit_confirm(s, pygame.mouse.get_pos())

    def _draw_play(self, s):
        if self.zone == "dead":
            d = self.death_info or {}
            ui.draw_center_text(s, "YOU DIED",
                                 f"{d.get('cls','?').title()} reached level {d.get('level','?')} with "
                                 f"{d.get('kills','?')} kills. Permadeath - press Enter or click below to respawn.",
                                 (220, 60, 60))
            ui.draw_death_screen_button(s, pygame.mouse.get_pos())
            return
        if self.you is None:
            ui.draw_center_text(s, "SYNCING...")
            return

        if self.zone == "nexus":
            self._draw_hub(self.nexus_map, self.nexus_minimap, "Nexus (co-op)",
                            "Walk onto a portal: Realm | Vault | Bazaar")
        elif self.zone == "bazaar":
            self._draw_hub(self.bazaar_map, self.bazaar_minimap, "Bazaar (co-op)",
                            "Drop items for others - walk onto the portal to return")
        elif self.zone == "vault_room":
            self._draw_hub(self.vault_room_map, self.vault_room_minimap, "Vault (co-op)",
                            "Walk up to a chest and press F to open it - the portal returns to the Nexus")
        elif self.zone in ("realm", "bonus") and self.tilemap:
            zone_label = ("The Godlands (co-op)" if self.zone == "realm"
                          else f"{self.theme_name or 'Bonus Room'} [{self.difficulty}] (co-op)")
            self._draw_sim(zone_label)


        mp = pygame.mouse.get_pos()
        self._last_nearby_rows = ui.draw_nearby_players_panel(s, self._nearby_players(), mp)
        if self.friends_panel_open:
            ui.draw_friends_panel(s, self._friends_status(), mp)
        inspected = next((pe for pe in self.peers if pe.pid == self.inspect_pid), None)
        if inspected is not None:
            ui.draw_inspect_panel(s, inspected, mp)
        elif self.inspect_pid is not None:
            self.inspect_pid = None  # they left the zone
        if self.trade_invite is not None:
            ui.draw_trade_invite(s, self.trade_invite, mp)
        if self.trade is not None and self._dragged_item() is not None:
            ui.draw_dragged_item(s, self._dragged_item(), mp)  # above the trade window
        if self.context_menu is not None:
            ui.draw_context_menu(s, self.context_menu["pos"], self.context_menu["name"],
                                  self._context_menu_labels(), mp, disabled=self._context_menu_disabled())

    def _draw_right_switch_panel(self, s, mp):
        """Tab key switches this dock slot between the inventory grid and pet
        stats - only one is ever drawn per frame, with a small tab-label strip
        above it so the key is discoverable. Falls back to inventory if
        there's no pet to show, so Tab can never leave a blank panel."""
        mode = self._dock_mode()
        dragging = self.drag_from is not None
        ui.draw_panel_tabs(s, mode, feed_drop_hint=dragging and getattr(self.you, "pet", None) is not None)
        if mode == "pet":
            ui.draw_pet_panel(s, self.you, dragging=dragging, mouse_pos=mp)
        else:
            ui.draw_inventory(s, self.you, mp, dragging_from=self.drag_from,
                              highlighted=set(self.trade.get("my_offer_idx", [])) if self.trade else (),
                              socket_pair=self.pending_socket)

    def _current_place(self):
        """(zone_kind, key, title, subtitle, music_zone) for game.zone_banner, or None."""
        if self.you is None or self.zone == "dead":
            return None
        if self.zone in ("nexus", "bazaar", "vault_room"):
            return zone_banner.hub_place({"vault_room": "vault"}.get(self.zone, self.zone))
        if self.zone == "bonus":
            return zone_banner.dungeon_place(self.theme_name, self.difficulty,
                                             audio.dungeon_zone_for_label(self.theme_name))
        if self.zone == "realm" and self.tilemap is not None:
            tx, ty = self.you.pos.x / C.TILE, self.you.pos.y / C.TILE
            biome = zone_banner.biome_near(self.tilemap, self.you.pos.x, self.you.pos.y)
            got = zone_banner.realm_place(self.realm_areas, tx, ty, biome)
            if got is None and (self.zone_tracker.place or "").startswith(("biome:", "area:", "island:")):
                return None   # open water / walkway far from any biome - keep the current place
            return got or ("realm", "biome:realm", "The Realm", "Realm", "forest")
        return None

    def _draw_hub(self, tmap, mm, name, hint_text):
        s = self.screen
        if mm.full_map_open:
            minimap.draw_full_map(s, tmap, mm, self.you.pos, peers=self.peers, zone_name=name)
            return
        if tmap is self.nexus_map:
            tmap.draw_backdrop(s, self.cam)
        # RotMG itself works this way: Q/E turns the MAP, characters stay upright.
        tmap.canopy_overlay = True  # trunks in the floor pass, canopies drawn over entities below
        world.render_rotated_world(s, self.cam, lambda surf, cam: tmap.draw(surf, cam, surf.get_size()))
        if tmap is self.bazaar_map:
            for g in self.bazaar_ground_items:
                g.draw(s, self.cam)
        if tmap is self.nexus_map:
            for n in self.npcs:
                n.draw(s, self.cam)
        if tmap is self.nexus_map and self.nexus_bot is not None:
            self.nexus_bot.draw(s, self.cam)
            if self.nexus_bot.speech and self.nexus_bot.speech_age < self.nexus_bot.SPEECH_LIFETIME:
                ui.draw_speech_bubble(s, self.cam, self.nexus_bot.pos, self.nexus_bot.speech, self.nexus_bot.speech_age)
        for peer in self.peers:
            peer.draw(s, self.cam)
        self._draw_peer_labels(s, self.cam, self.peers)
        if tmap is self.vault_room_map:
            near = vault.nearest_chest(tmap, self.you.pos)
            ui.draw_vault_room_chests(s, self.cam, [vault.chest_world_pos(tmap, i)
                                                     for i in range(len(vault.chest_tiles(tmap)))],
                                      self.vault_items, near[0] if near else None, self.vault_chest_open)
        self.you.draw(s, self.cam)
        tmap.draw_canopies(s, self.cam, (self.you.pos if self.you else None))
        ui.draw_npc_labels(s, self.cam, self.npcs, self.you.pos if self.you else None)
        self._draw_speech_bubbles(s)
        vfx.draw(s, self.cam)
        self._draw_hover_tooltip()
        hint = ui._FONT_M.render(hint_text, True, (220, 210, 230))
        s.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, 82))
        if tmap is self.nexus_map:
            event_label = live_events.label_for(getattr(self, "live_event", None))  # the server's event
            if event_label:
                banner = ui._FONT_S.render(f"Live event: {event_label}", True, (255, 220, 120))
                s.blit(banner, (C.SCREEN_W // 2 - banner.get_width() // 2, 104))
        ui.draw_dock_frame(s, self.you)
        ui.draw_hud(s, name, None, False)  # hubs: no kill counter
        if not (self.echo_shop_open or self.help_open or self.vault_chest_open is not None):  # a modal overlay owns that space
            ui.draw_story_log(s, self.quest_log, self.quest_log_expanded, side=self.sidequest_log)
        if settings.get("show_fps"):
            ui.draw_fps_counter(s, self.clock.get_fps())
        mp = pygame.mouse.get_pos()
        ui.draw_player_panel(s, self.you, auto_fire=False)
        self._draw_right_switch_panel(s, mp)
        dragged = self._dragged_item()
        if dragged:
            ui.draw_dragged_item(s, dragged, mp)
        elif not self.drag_from and tmap is self.bazaar_map:
            ui.draw_ground_item_tooltip(s, self.cam, mp, self.bazaar_ground_items)
            ui.draw_nearby_loot_panel(s, [g for g in self.bazaar_ground_items
                                           if g.pos.distance_to(self.you.pos) <= 160])
        open_bag = self._current_bag()
        if open_bag is not None:
            ui.draw_bag_window(s, self.cam(open_bag.pos), self.bag_items, mp, dragging_from=self.drag_from)
        ui.draw_item_feed(s, self.feed, y=128)  # below the hub's portal hint + live-event banner
        if tmap is self.vault_room_map and self.vault_chest_open is not None:
            ui.draw_vault_chest_window(s, self._vault_chest_screen_pos(), self.vault_chest_open, self.vault_items,
                                       mp, dragging_from=self.drag_from)
            if dragged:
                ui.draw_dragged_item(s, dragged, mp)
        minimap.draw_corner(s, tmap, mm, self.you.pos, peers=self.peers)
        ui.draw_chat_log(s, self.chat_log, scroll=self.chat_scroll, selection=self.chat_log_sel.span())
        if self.chat_open:
            ui.draw_chat_box(s, self.chat_buffer, chat_input=self.chat_in, recent=self.chat_log)
        if self.trade is not None:
            ui.draw_trade_panel(s, self.trade, self.you.name, mouse_pos=mp)

    def _draw_sim(self, name):
        s = self.screen
        mm = self._current_minimap()
        if mm is not None and mm.full_map_open:
            minimap.draw_full_map(s, self.tilemap, mm, self.you.pos,
                                   peers=self.peers, portals=self.portals, zone_name=name, enemies=self.enemies)
            return
        fog = mm.explored if (self.zone == "bonus" and mm is not None) else None
        self.tilemap.canopy_overlay = True  # trunks in the floor pass, canopies drawn over entities below
        world.render_rotated_world(s, self.cam, lambda surf, cam: self.tilemap.draw(surf, cam, surf.get_size(), fog=fog))
        for g in self.ground_items:
            g.draw(s, self.cam)
        for pt in self.portals:
            pt.draw(s, self.cam)
        ui.draw_portal_labels(s, self.cam, self.portals)
        ui.draw_island_chests(s, self.cam, self.island_chests)
        for n in self.npcs:
            n.draw(s, self.cam)
        for ob in self.obstacles:
            ob.draw(s, self.cam)
        for e in self.enemies:
            # `visible` is server-computed real line-of-sight (see server.py's
            # _snapshot_for) - the boss can still be IN this list (for the
            # minimap blip below) while not currently in LOS, so this check is
            # required here even though the server already filtered by distance
            if not e.visible:
                continue
            e.draw(s, self.cam)
            if e.speech and e.speech_age < ui.SPEECH_BUBBLE_LIFETIME:
                ui.draw_speech_bubble(s, self.cam, e.pos, e.speech, e.speech_age, text_color=ui.MOB_SPEECH_COLOR)
        for peer in self.peers:
            peer.draw(s, self.cam)
            if peer.fishing_state is not None:
                vfx.draw_fishing_bobber(s, self.cam, peer.pos, peer.fishing_state)
        self._draw_peer_labels(s, self.cam, self.peers)
        for b in self.bullets:
            b.draw(s, self.cam)
        self.you.draw(s, self.cam)
        self.tilemap.draw_canopies(s, self.cam, (self.you.pos if self.you else None))
        ui.draw_npc_labels(s, self.cam, self.npcs, self.you.pos if self.you else None)
        if self.you.fishing_state is not None:
            vfx.draw_fishing_bobber(s, self.cam, self.you.pos, self.you.fishing_state)
        vfx.draw(s, self.cam)
        ui.draw_damage_popups(s, self.cam, self.popups)
        torch_positions = [self.cam(pos) for pos in
                           world.nearby_torch_world_positions(self.tilemap, self.you.pos.x, self.you.pos.y)]
        ui.draw_day_night_overlay(s, self.light_level, self.blood_moon, torch_positions)
        self.weather_fx.draw(s)
        ui.draw_dock_frame(s, self.you)
        if self.zone != "bonus":
            ui.draw_day_night_clock(s, self.light_level, self.blood_moon)
        else:
            ui.draw_dungeon_header(s)
        self._draw_speech_bubbles(s)
        self._draw_hover_tooltip()
        ui.draw_hud(s, name, self.kill_count, self.boss_active)
        if settings.get("show_fps"):
            ui.draw_fps_counter(s, self.clock.get_fps())
        if self.portal_prompt:
            ui.draw_portal_prompt(s)
        if (self.zone != "bonus" or self.theme_name == DUNGEON_THEMES["forge"]["label"]) and not self.help_open:
            ui.draw_story_log(s, self.quest_log, self.quest_log_expanded, side=self.sidequest_log)
        else:
            ui.draw_quest_panel(s, self.secret_quest, self.secret_quest_progress, self.secret_quest_timer,
                                 secret_quest_target=self.secret_quest_target,
                                 phase2_quest=self.phase2_quest, phase2_progress=self.phase2_quest_progress,
                                 phase2_quest_target=self.phase2_quest_target)
        mp = pygame.mouse.get_pos()
        ui.draw_player_panel(s, self.you, auto_fire=self.auto_fire_enabled)
        self._draw_right_switch_panel(s, mp)
        dragged = self._dragged_item()
        if dragged:
            ui.draw_dragged_item(s, dragged, mp)
        elif not self.drag_from:
            ui.draw_ground_item_tooltip(s, self.cam, mp, self.ground_items)
            ui.draw_nearby_loot_panel(s, sorted(
                [g for g in self.ground_items if g.pos.distance_to(self.you.pos) <= 160],
                key=lambda g: g.pos.distance_to(self.you.pos)))
        open_bag = self._current_bag()
        if open_bag is not None:
            ui.draw_bag_window(s, self.cam(open_bag.pos), self.bag_items, mp, dragging_from=self.drag_from)
        ui.draw_item_feed(s, self.feed)
        if mm is not None:
            minimap.draw_corner(s, self.tilemap, mm, self.you.pos, peers=self.peers, portals=self.portals,
                                 enemies=self.enemies)
        ui.draw_chat_log(s, self.chat_log, scroll=self.chat_scroll, selection=self.chat_log_sel.span())
        if self.chat_open:
            ui.draw_chat_box(s, self.chat_buffer, chat_input=self.chat_in, recent=self.chat_log)
        if self.trade is not None:
            ui.draw_trade_panel(s, self.trade, self.you.name, mouse_pos=mp)

    def _draw_speech_bubbles(self, s):
        for b in self._speech_bubbles:
            pos = name = None
            if self.you and b["pid"] == self.you.pid:
                pos, name = self.you.pos, self.you.name
            else:
                peer = next((pe for pe in self.peers if pe.pid == b["pid"]), None)
                if peer:
                    pos, name = peer.pos, peer.name
            if pos is not None:
                ui.draw_speech_bubble(s, self.cam, pos, b["text"], b["age"], name=name)

    def _draw_peer_labels(self, surf, cam, peers):
        """Draws every nearby peer's name tag with the same greedy vertical-
        stagger collision avoidance as ui.draw_portal_labels - several
        players standing close together (very common right after a dungeon
        spawn, or crowded around a boss) previously had their name tags
        drawn independently at a fixed -34px offset with no awareness of
        each other, which visibly overlaps at typical co-op crowd spacing."""
        if not peers:
            return
        entries = []
        for peer in sorted(peers, key=lambda pr: cam(pr.pos)[0]):
            name = f"{peer.name} {peer.title}" if peer.title else f"{peer.name} Lv{peer.level}"
            color = (210, 210, 230) if not peer.title else (230, 210, 150)
            entries.append((cam(peer.pos), ui._FONT_S.render(name, True, color)))
        placed_rects = []
        for (px, py), label in entries:
            w, h = label.get_size()
            base_y = py - 34
            rect = pygame.Rect(px - w // 2, base_y, w, h)
            step = 0
            while any(rect.colliderect(r) for r in placed_rects):
                step += 1
                rect.y = base_y - step * (h + 2)
            placed_rects.append(rect)
            surf.blit(label, (rect.x, rect.y))

    def _draw_hover_tooltip(self):
        # done in world-space (via the rotation-aware inverse()) rather than comparing
        # raw screen pixels, so hovering still works correctly while the camera is rotated
        mouse_pos = pygame.mouse.get_pos()
        mouse_world = self.cam.inverse(mouse_pos)
        for peer in self.peers:
            if mouse_world.distance_to(peer.pos) < 40:
                ui.draw_peer_tooltip(self.screen, mouse_pos, peer, crews.get_crew_for_player(peer.name))
                break


def main():
    parser = argparse.ArgumentParser(description="Realm Reforged co-op client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=C.NET_PORT)
    parser.add_argument("--name", default="Player")
    args = parser.parse_args()
    CoopClient(args.host, args.port, args.name).run()


if __name__ == "__main__":
    main()

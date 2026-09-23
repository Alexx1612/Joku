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
from game import weather
from game import vfx
from game import clipboard
from game import friends
from game.entities import Player, Enemy, Bullet, Bag, Portal, Obstacle, NexusBot
from game.netmsg import send_msg, MessageReader
from game.items import VAULT_SLOTS, VAULT_CHEST_SIZE
from game.realm_sim import auto_aim_direction

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
        self.frozen_time = 1.0 if d.get("frozen") else 0.0
        self.moonlit = d.get("moonlit", False)
        self.invulnerable = d.get("invulnerable", False)
        self.speech = d.get("speech", "")
        self.speech_age = d.get("speech_age", 999.0)
        self.neutral = d.get("neutral", False)
        self.visible = d.get("visible", True)  # server-computed real LOS - see server.py::_snapshot_for


class GhostBullet:
    draw = Bullet.draw

    def __init__(self, d):
        self.pos = pygame.Vector2(d["x"], d["y"])
        self.color, self.radius = tuple(d["color"]), d["radius"]
        self.shape = d.get("shape", "bolt")
        self.vel = pygame.Vector2(d.get("vel", (0, 0)))


class GhostBag:
    draw = Bag.draw

    def __init__(self, d):
        self.id = d["id"]
        self.pos = pygame.Vector2(d["x"], d["y"])
        self.bag_color = tuple(d["bag_color"])
        self.name = d.get("name")
        self.count = d.get("count", 1)
        self.tier_color = tuple(d["tier_color"]) if d.get("tier_color") else (200, 200, 200)


class GhostBot:
    draw = NexusBot.draw

    def __init__(self, d):
        self.pos = pygame.Vector2(d["x"], d["y"])
        self.name = d.get("name", "Father Given")
        self.speech = d.get("speech", "")
        self.speech_age = d.get("speech_age", 0.0)
        self.SPEECH_LIFETIME = NexusBot.SPEECH_LIFETIME


class GhostPortal:
    draw = Portal.draw

    def __init__(self, d, t=0.0):
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


class NetLink:
    """Background thread that keeps the latest server messages ready for the render loop."""

    def __init__(self, sock):
        self.sock = sock
        self.reader = MessageReader(sock)
        self.lock = threading.Lock()
        self.latest_snapshot = None
        self.pending_map = None
        self.vault_items = None
        self.vault_chest_hint = None
        self.bag_state = None  # {"id": bag_id, "items": [json, ...]} - the last opened/withdrawn-from bag
        self.whispers = []  # queued incoming/echoed whisper messages, drained each frame
        self.wish_result = None
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
        audio.play_theme()
        self.fullscreen = False
        self.help_open = False
        self.menu_selected = 0
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

        self.vault_open = False
        self.vault_chest = 0  # which of the VAULT_CHEST_COUNT chests is currently paged in
        self._suppress_vault_trigger = False  # see _vault_click's close-button branch
        self.vault_items = []
        self.open_bag_id = None  # id of the ground Bag currently shown in the drag-and-drop window
        self.bag_items = []
        self.context_menu = None  # {"pid","name","pos"} - the right-click-a-player popup
        self.friends_panel_open = False
        self.friends = friends.load_friends(name)
        self._last_nearby_rows = []  # [(row_rect, tp_rect, pid), ...] from the last draw, for click hit-testing
        self.bazaar_ground_items = []
        self.nexus_bot = None
        self._last_bot_speech = ""  # dedupe so the same line isn't re-pushed to chat_log every snapshot
        self.realm_minimap = None
        self.bonus_minimap = None
        self.auto_fire_enabled = False
        self.popups = []
        self._ui_click_active = False  # suppresses firing while a UI click (e.g. inventory) is held
        self._last_level = 1
        self.drag_from = None       # ("backpack", idx) or ("equip", slot_type) while a drag is in progress
        self.drag_start_pos = None
        self._dblclick_slot = None  # ("backpack", idx) of the last plain click, for double-click-to-use
        self._dblclick_time = 0     # detection - equip/use now fires on a DOUBLE click, not a single one
        self.DBLCLICK_MS = 350
        self._prev_backpack_len = 0
        self._prev_boss_active = False
        self._local_fire_cd = 0.0  # client-side estimate only, purely to pace the shoot sound
        self.chat_open = False
        self.chat_buffer = ""
        self._chat_select_all = False
        self._speech_bubbles = []  # [{pid, text, age}]
        self.chat_log = []  # [{name, text, age}] persistent left-side log, cap ui.CHAT_LOG_STORE_CAP, scrollable via self.chat_scroll
        self.chat_scroll = 0  # wrapped-line offset from the newest line, 0 = pinned to the bottom
        self.trade = None  # the server's per-viewer trade dict, or None (see server._trade_info_for)
        self.nexus_minimap = minimap.MinimapState()
        self.nexus_minimap.reveal_all(self.nexus_map)
        self.bazaar_minimap = minimap.MinimapState()
        self.bazaar_minimap.reveal_all(self.bazaar_map)
        self.vault_room_minimap = minimap.MinimapState()
        self.vault_room_minimap.reveal_all(self.vault_room_map)
        self.nexus_ambience = vfx.NexusAmbience()

    # ---------------------------------------------------------------- run --
    def run(self):
        while True:
            dt = min(self.clock.tick(C.FPS) / 1000.0, 0.05)
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

    MAX_CANVAS_DIM = 2560

    def _resize_canvas(self, w, h):
        w = max(320, min(self.MAX_CANVAS_DIM, w))
        h = max(240, min(self.MAX_CANVAS_DIM, h))
        C.SCREEN_W, C.SCREEN_H = w, h
        self.screen = pygame.Surface((w, h))
        self.cam.screen_w, self.cam.screen_h = w, h

    def _menu_items(self):
        """The O-key menu: an actual interactive list (Up/Down to move, Enter to
        activate), not just a read-only controls reference."""
        items = [
            (f"Auto-fire: {'ON' if self.auto_fire_enabled else 'OFF'}", self._menu_toggle_autofire),
            (f"Fullscreen: {'ON' if self.fullscreen else 'OFF'}", self._toggle_fullscreen),
            ("Reset camera rotation", self.cam.reset_rotation),
        ]
        mm = self._current_minimap()
        if mm is not None:
            items.append((f"Full map: {'OPEN' if mm.full_map_open else 'closed'}", self._menu_toggle_full_map))
        if self.state == STATE_PLAY:
            items.append(("Disconnect (return to Class Select)", self._menu_disconnect))
        items.append(("Close menu", self._menu_close))
        return items

    def _menu_toggle_autofire(self):
        self.auto_fire_enabled = not self.auto_fire_enabled

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

    def _menu_close(self):
        self.help_open = False

    # ------------------------------------------------------------- events --
    CHAT_ZONES = ("nexus", "bazaar", "vault_room", "realm", "bonus")

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
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
            if event.type == pygame.KEYDOWN:
                if self.chat_open:
                    self._handle_chat_key(event)
                elif (event.key == pygame.K_RETURN and self.state == STATE_PLAY and not self.vault_open
                      and self.zone in self.CHAT_ZONES and not self.help_open and not self.portal_prompt):
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
                elif self.help_open and event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_w, pygame.K_s):
                    items = self._menu_items()
                    step = -1 if event.key in (pygame.K_UP, pygame.K_w) else 1
                    self.menu_selected = (self.menu_selected + step) % len(items)
                elif self.help_open and event.key == pygame.K_RETURN:
                    _, action = self._menu_items()[self.menu_selected]
                    action()
                elif event.key == pygame.K_SPACE and self.zone in ("realm", "bonus"):
                    self._use_ability()
                elif event.key == pygame.K_m and self._current_minimap() is not None:
                    self._current_minimap().full_map_open = not self._current_minimap().full_map_open
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    self._zoom_minimap(minimap.ZOOM_STEP)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    self._zoom_minimap(-minimap.ZOOM_STEP)
                elif event.key == pygame.K_ESCAPE:
                    if self._map_open():
                        self._current_minimap().full_map_open = False
                    elif self.context_menu is not None:
                        self.context_menu = None
                    elif self.friends_panel_open:
                        self.friends_panel_open = False
                    elif self.help_open:
                        self.help_open = False
                    elif self.vault_open:
                        pass  # closing the Vault is click-only now (see vault_close_button_rect)
                    else:
                        return False
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
                    items = self._menu_items()
                    for i, rect in enumerate(ui.help_menu_item_rects(items)):
                        if rect.collidepoint(event.pos):
                            self.menu_selected = i
                            _, action = items[i]
                            action()
                            break
                elif self.context_menu is not None:
                    self._context_menu_click(event.pos)
                elif self.friends_panel_open:
                    self._friends_panel_click(event.pos)
                elif self.vault_open:
                    if not self._vault_click_extras(event.pos):
                        self._inventory_mouse_down(event.pos)
                elif self.trade is not None:
                    self._trade_click(event.pos)
                elif self._current_minimap() is not None and self._minimap_button_click(event.pos):
                    pass
                elif (self._current_bag() is not None
                      and ui.bag_window_close_button_rect(self.cam(self._current_bag().pos)).collidepoint(event.pos)):
                    self.open_bag_id = None
                    self.bag_items = []
                elif (not self.chat_open and self.zone in self.CHAT_ZONES
                      and ui.chat_log_rect(self.chat_log).collidepoint(event.pos)):
                    self.chat_open = True
                    self.chat_buffer = ""
                elif self._nearby_players_click(event.pos, self._last_nearby_rows):
                    pass
                elif self.you and self.zone in ("nexus", "bazaar", "vault_room", "realm", "bonus"):
                    self._inventory_mouse_down(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.drag_from is not None:
                    if self.vault_open:
                        self._vault_mouse_up(event.pos)
                    else:
                        self._inventory_mouse_up(event.pos)
                self._ui_click_active = False
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
        ctrl = event.mod & pygame.KMOD_CTRL
        if ctrl and event.key == pygame.K_a:
            self._chat_select_all = True
            return
        if ctrl and event.key == pygame.K_c:
            clipboard.set_text(self.chat_buffer)
            return
        if ctrl and event.key == pygame.K_x:
            clipboard.set_text(self.chat_buffer)
            self.chat_buffer = ""
            self._chat_select_all = False
            return
        if ctrl and event.key == pygame.K_v:
            if self._chat_select_all:
                self.chat_buffer = ""
                self._chat_select_all = False
            self.chat_buffer = (self.chat_buffer + clipboard.get_text().replace("\n", " "))[:CHAT_MAX_LEN]
            return
        if event.key == pygame.K_RETURN:
            self._submit_chat()
        elif event.key == pygame.K_ESCAPE:
            self.chat_open = False
            self.chat_buffer = ""
            self._chat_select_all = False
        elif event.key == pygame.K_BACKSPACE:
            if self._chat_select_all:
                self.chat_buffer = ""
                self._chat_select_all = False
            else:
                self.chat_buffer = self.chat_buffer[:-1]
        elif event.unicode and event.unicode.isprintable() and len(self.chat_buffer) < CHAT_MAX_LEN:
            if self._chat_select_all:
                self.chat_buffer = ""
                self._chat_select_all = False
            self.chat_buffer += event.unicode

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
        elif cmd == "w":
            rest = parts[1] if len(parts) > 1 else ""
            name_part, _, message = rest.partition(" ")
            target = next((pe for pe in self.peers if pe.name.lower() == name_part.lower()), None)
            if target is None or not message.strip():
                self.feed.insert(0, ["Usage: /w <name> <message> (they must be nearby you)", (220, 150, 90), 4.0])
                self.feed = self.feed[:4]
            else:
                self.link.send({"type": "action", "action": "whisper", "pid": target.pid, "text": message.strip()})
        elif cmd == "help":
            self.feed.insert(0, ["Commands: /nexus /realm /vault /bazaar /trade /w <name> <msg>",
                                  (200, 200, 215), 4.0])
            self.feed = self.feed[:4]
        else:
            self.feed.insert(0, [f"Unknown command: /{cmd}", (220, 120, 120), 4.0])
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

    def _context_menu_labels(self):
        name = self.context_menu["name"]
        return ["Chat", "Trade", "Teleport", "Remove Friend" if name in self.friends else "Add Friend"]

    def _context_menu_click(self, pos):
        menu = self.context_menu
        labels = self._context_menu_labels()
        self.context_menu = None
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

    def _slot_at(self, pos):
        if self.vault_open:
            for i, rect in enumerate(ui._vault_backpack_slot_rects(self.you)):
                if rect.collidepoint(pos):
                    return ("backpack", i)
            lo = self.vault_chest * VAULT_CHEST_SIZE
            for i, rect in enumerate(ui.vault_slot_rects()):
                if rect.collidepoint(pos):
                    return ("vault", lo + i)
            return None
        bag = self._current_bag()
        if bag is not None:
            for i, rect in enumerate(ui.bag_slot_rects(self.cam(bag.pos))):
                if rect.collidepoint(pos):
                    return ("bag", i)
        pet_rect = ui.pet_feed_target_rect(self.you) if self.you else None
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

    def _vault_click_extras(self, pos):
        """Close button and chest tabs stay click-only. Returns True if handled."""
        if ui.vault_close_button_rect().collidepoint(pos):
            self.vault_open = False
            self._suppress_vault_trigger = True
            return True
        for i, rect in enumerate(ui.vault_chest_tab_rects()):
            if rect.collidepoint(pos):
                self.vault_chest = i
                self.link.send({"type": "action", "action": "vault_select_chest", "chest": i})
                return True
        return False

    def _vault_mouse_up(self, pos):
        """Vault <-> backpack drag-and-drop (or a plain click) - server stays
        authoritative, this only decides which action to send."""
        origin = self.drag_from
        self.drag_from = None
        if origin is None or not self.you:
            return
        dest = self._slot_at(pos)
        dropped_far = math.hypot(pos[0] - self.drag_start_pos[0], pos[1] - self.drag_start_pos[1]) > 6
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
        dest = self._slot_at(pos)
        dropped_far = math.hypot(pos[0] - self.drag_start_pos[0], pos[1] - self.drag_start_pos[1]) > 6
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
            self.link.send({"type": "action", "action": "swap_backpack", "i": origin[1], "j": dest[1]})
        elif origin[0] == "backpack" and dest[0] == "equip":
            self.link.send({"type": "action", "action": "equip", "idx": origin[1], "slot": dest[1]})
        elif origin[0] == "equip" and dest[0] == "backpack":
            self.link.send({"type": "action", "action": "unequip", "slot": origin[1]})
        elif origin[0] == "backpack" and dest[0] == "pet":
            self.link.send({"type": "action", "action": "feed_pet", "idx": origin[1]})

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
        if self.vault_open:
            return  # closing the Vault is click-only now (see vault_close_button_rect)
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
        elif key == pygame.K_i and self.zone in ("realm", "bonus"):
            self.auto_fire_enabled = not self.auto_fire_enabled
            self.feed.insert(0, [f"Auto-fire {'ON' if self.auto_fire_enabled else 'OFF'}",
                                  (150, 220, 255) if self.auto_fire_enabled else (170, 170, 180), 4.0])
            self.feed = self.feed[:4]
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
        for i, rect in enumerate(ui.backpack_slot_rects(self.you)):
            if rect.collidepoint(pos) and i < len(self.you.backpack):
                self.link.send({"type": "action", "action": "trade_offer", "idx": i})
                return

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

        theme_zone = self._THEME_ZONE_FOR_ZONE.get(self.zone)
        if theme_zone is not None:
            audio.play_theme(theme_zone)

        if not self.chat_open and not self.help_open:
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
            if w.get("echo"):
                self.chat_log.append({"name": f"You -> {w['to']}", "text": w["text"], "age": 0.0})
            else:
                self.chat_log.append({"name": f"{w['from']} (whisper)", "text": w["text"], "age": 0.0})
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
                biome_name = world.GROUND_TO_BIOME_NAME.get(tile_here)
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
                prefix = "The Guide trades your" if wr.get("via_bot") else ""
                label = f"{prefix} {wr['old_name']} -> {wr['new_name']} ({verdict})".strip()
                self.feed.insert(0, [label, color, 4.0])
                audio.play_wish(wr["is_ut"])
            self.feed = self.feed[:4]

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
        self.zone = snap["zone"]
        if self.zone == "dead":
            if self.death_info is None:  # just arrived in the dead zone this snapshot
                audio.play_death()
                if self.you is not None:
                    vfx.spawn_burst(self.you.pos, (255, 90, 90), count=24, speed=(60, 220), life=(0.3, 0.65))
            self.death_info = snap.get("death_info")
            return
        self.death_info = None
        self.trade = snap.get("trade")
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
            self.chat_log.append({"name": speaker, "text": text, "age": 0.0})
        self.feed = self.feed[:4]
        self.chat_log = self.chat_log[-ui.CHAT_LOG_STORE_CAP:]
        vault, chest_hint = self.link.pop_vault_items()
        if vault is not None:
            from game.items import Item
            self.vault_items = [(Item.from_json(d) if d is not None else None) for d in vault]
            self.vault_chest = chest_hint if chest_hint is not None else 0
            self.vault_open = True
        bag_state = self.link.pop_bag_state()
        if bag_state is not None:
            from game.items import Item
            self.open_bag_id = bag_state["id"]
            self.bag_items = [Item.from_json(d) for d in bag_state["items"]]
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
                else:
                    self.bonus_minimap = minimap.MinimapState()
            mm = self._current_minimap()
            if mm is not None:
                mm.reveal(you.pos)
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
            self.bazaar_ground_items = [GhostBag(d) for d in snap.get("ground_items", [])]
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
        elif self.zone == "bazaar":
            if self.bazaar_map.tile_at(self.you.pos.x, self.you.pos.y) == world.PORTAL:
                self.link.send({"type": "action", "action": "goto_nexus"})
        elif self.zone == "vault_room":
            tile = self.vault_room_map.tile_at(self.you.pos.x, self.you.pos.y)
            if tile != world.CHEST:
                self._suppress_vault_trigger = False
            if tile == world.PORTAL:
                self.link.send({"type": "action", "action": "goto_nexus"})
            elif tile == world.CHEST and not self._suppress_vault_trigger:
                self.link.send({"type": "action", "action": "open_vault"})

    def _send_input(self, dt):
        if self._map_open() or self.chat_open or self.help_open:
            # checking the full map, typing in chat, or browsing the options menu is
            # a modal action - stop sending input while it's up (other players keep
            # moving normally; only yours freezes) so you don't drift/move by accident
            self.link.send({"type": "input", "move": [0.0, 0.0], "aim": [0.0, 0.0], "fire": False})
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
                aim = auto_aim_direction(self.you.pos, aim, self.enemies)
        fire = ((self.auto_fire_enabled or bool(pygame.mouse.get_pressed()[0])) and self.zone in ("realm", "bonus")
                and not self.vault_open and not self._ui_click_active)
        self.link.send({"type": "input", "move": [move.x, move.y], "aim": [aim.x, aim.y], "fire": fire})

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
                            "Walk onto a chest to open it - the portal returns to the Nexus")
        elif self.zone in ("realm", "bonus") and self.tilemap:
            zone_label = ("The Godlands (co-op)" if self.zone == "realm"
                          else f"{self.theme_name or 'Bonus Room'} [{self.difficulty}] (co-op)")
            self._draw_sim(zone_label)

        if self.vault_open:
            mp = pygame.mouse.get_pos()
            ui.draw_vault_screen(s, self.you, self.vault_items, VAULT_SLOTS, mp,
                                 selected_chest=self.vault_chest, dragging_from=self.drag_from)
            dragged = self._dragged_item()
            if dragged:
                ui.draw_dragged_item(s, dragged, mp)

        mp = pygame.mouse.get_pos()
        self._last_nearby_rows = ui.draw_nearby_players_panel(s, self._nearby_players(), mp)
        if self.friends_panel_open:
            ui.draw_friends_panel(s, self._friends_status(), mp)
        if self.context_menu is not None:
            ui.draw_context_menu(s, self.context_menu["pos"], self.context_menu["name"],
                                  self._context_menu_labels(), mp)

    def _draw_hub(self, tmap, mm, name, hint_text):
        s = self.screen
        if mm.full_map_open:
            minimap.draw_full_map(s, tmap, mm, self.you.pos, peers=self.peers, zone_name=name)
            return
        if tmap is self.nexus_map:
            tmap.draw_backdrop(s, self.cam)
        # RotMG itself works this way: Q/E turns the MAP, characters stay upright.
        world.render_rotated_world(s, self.cam, lambda surf, cam: tmap.draw(surf, cam, surf.get_size()))
        if tmap is self.bazaar_map:
            for g in self.bazaar_ground_items:
                g.draw(s, self.cam)
        elif tmap is self.nexus_map and self.nexus_bot is not None:
            self.nexus_bot.draw(s, self.cam)
            if self.nexus_bot.speech and self.nexus_bot.speech_age < self.nexus_bot.SPEECH_LIFETIME:
                ui.draw_speech_bubble(s, self.cam, self.nexus_bot.pos, self.nexus_bot.speech, self.nexus_bot.speech_age)
        for peer in self.peers:
            peer.draw(s, self.cam)
        self._draw_peer_labels(s, self.cam, self.peers)
        self.you.draw(s, self.cam)
        self._draw_speech_bubbles(s)
        vfx.draw(s, self.cam)
        self._draw_hover_tooltip()
        hint = ui._FONT_M.render(hint_text, True, (220, 210, 230))
        s.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, 82))
        ui.draw_hud(s, name, 0, False)
        mp = pygame.mouse.get_pos()
        ui.draw_player_panel(s, self.you, auto_fire=False)
        ui.draw_pet_panel(s, self.you, dragging=self.drag_from is not None)
        ui.draw_inventory(s, self.you, mp, dragging_from=self.drag_from)
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
        minimap.draw_corner(s, tmap, mm, self.you.pos, peers=self.peers)
        ui.draw_chat_log(s, self.chat_log, scroll=self.chat_scroll)
        if self.chat_open:
            ui.draw_chat_box(s, self.chat_buffer, selected=self._chat_select_all)
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
        world.render_rotated_world(s, self.cam, lambda surf, cam: self.tilemap.draw(surf, cam, surf.get_size(), fog=fog))
        for g in self.ground_items:
            g.draw(s, self.cam)
        for pt in self.portals:
            pt.draw(s, self.cam)
        ui.draw_portal_labels(s, self.cam, self.portals)
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
        self._draw_peer_labels(s, self.cam, self.peers)
        for b in self.bullets:
            b.draw(s, self.cam)
        self.you.draw(s, self.cam)
        vfx.draw(s, self.cam)
        ui.draw_damage_popups(s, self.cam, self.popups)
        ui.draw_day_night_overlay(s, self.light_level, self.blood_moon)
        if self.zone != "bonus":
            ui.draw_day_night_clock(s, self.light_level, self.blood_moon)
        self.weather_fx.draw(s)
        self._draw_speech_bubbles(s)
        self._draw_hover_tooltip()
        ui.draw_hud(s, name, self.kill_count, self.boss_active)
        if self.portal_prompt:
            ui.draw_portal_prompt(s)
        if self.zone == "bonus":
            ui.draw_quest_panel(s, self.secret_quest, self.secret_quest_progress, self.secret_quest_timer,
                                 secret_quest_target=self.secret_quest_target,
                                 phase2_quest=self.phase2_quest, phase2_progress=self.phase2_quest_progress,
                                 phase2_quest_target=self.phase2_quest_target)
        mp = pygame.mouse.get_pos()
        ui.draw_player_panel(s, self.you, auto_fire=self.auto_fire_enabled)
        ui.draw_pet_panel(s, self.you, dragging=self.drag_from is not None)
        ui.draw_inventory(s, self.you, mp, dragging_from=self.drag_from)
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
        ui.draw_chat_log(s, self.chat_log, scroll=self.chat_scroll)
        if self.chat_open:
            ui.draw_chat_box(s, self.chat_buffer, selected=self._chat_select_all)
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
                ui.draw_peer_tooltip(self.screen, mouse_pos, peer)
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

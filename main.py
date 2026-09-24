"""
Realm Reforged - v0 (single-player)
A from-scratch, RotMG-inspired bullet-hell top-down prototype: permadeath,
class stats driven by the real ATT/DEF/SPD/DEX/VIT/WIS formulas, tiered +
untiered (UT) loot, a Nexus hub with a Vault and a Bazaar, mob-death bonus
portals, and swarming enemies with bullet patterns.

For co-op with a friend, run server.py and have both players launch
coop_client.py instead of this file - see README.md.

Controls
  WASD / arrows  - move
  Mouse          - aim (soft assist near enemies)
  Left click     - fire (auto-repeats while held, rate = your DEX)
  I              - toggle auto-fire (fires continuously without holding click)
  1-8            - use/equip backpack slot
  Click+drag     - drag items between backpack/equip slots (or click to auto-equip/use)
  Enter          - confirm menus / interact with the tile you're standing on
  R              - Nexus (teleport to hub) while in the Realm
  Q / E          - rotate camera, X - reset it
  F11            - fullscreen (shows more of the world, not just a bigger view)
  M              - full map (scroll wheel or +/- to zoom); a minimap is always in the corner
  O              - toggle the controls overlay
  Esc            - quit / leave the Vault / close the controls overlay
"""
import math
import random
import sys

import pygame
from game import constants as C
from game import world
from game import ui
from game import audio
from game import minimap
from game import weather
from game import vfx
from game import accounts
from game import characters
from game import clipboard
from game import live_events
from game.entities import (Player, Bag, Portal, NexusBot, find_nearby_bag, bag_by_id,
                            withdraw_from_bag, BazaarChest, deposit_to_bag, spawn_bazaar_chests)
from game.realm_sim import RealmSim, auto_aim_direction, DUNGEON_THEMES, BONUS_DIFFICULTIES, AUTO_AIM_CONE_DEG
from game.items import (load_vault, save_vault, vault_exists, VAULT_SLOTS, VAULT_CHEST_SIZE,
                         PERMANENT_POTION_CAP, identify_proc_kind, apply_socket, SLOT_WEAPON)

(STATE_INTRO, STATE_NAME_ENTRY, STATE_CLASS_SELECT, STATE_NEXUS, STATE_REALM, STATE_BONUS,
 STATE_BAZAAR, STATE_VAULT_ROOM, STATE_VAULT, STATE_DEAD) = range(10)

_LEGACY_SINGLEPLAYER_VAULT_KEY = "singleplayer"  # pre-accounts fixed vault key; kept only for one-time migration
FIRE_BUFFER_WINDOW = 0.1  # seconds - an early fire click within this window of the weapon's
# cooldown clearing still fires, instead of being silently dropped (see _handle_firing)
SPEECH_BUBBLE_LIFETIME = 4.0
CHAT_MAX_LEN = 1000
CHAT_LOG_LIFETIME = 120.0  # chat log entries expire after 2 minutes
SOUND_HEARING_RADIUS = 900  # mob hit/death/bark sounds beyond this range aren't played -
# a bit past screen edge so combat you can almost see still has audio, without every
# idle bark on an 800-enemy continent being audible no matter where it happens
AUTOSAVE_INTERVAL = 60.0  # seconds between background character-progress saves,
# on top of the save-on-return-to-Nexus and save-on-quit checkpoints - covers long
# stretches spent in the Realm/Bazaar between Nexus visits so a crash there doesn't
# lose much progress

INTRO_DURATION = ui.INTRO_DURATION
INTRO_JOKES = ui.INTRO_JOKES


class Game:
    def __init__(self):
        pygame.init()
        audio.init()
        audio.play_theme()
        self.fullscreen = False
        self.help_open = False
        self.menu_selected = 0
        self.echo_shop_open = False  # the Echo Keeper's shop panel, see _open_echo_shop
        self.echo_shop_selected = 0
        self._base_size = (C.SCREEN_W, C.SCREEN_H)  # windowed-mode size, restored when leaving fullscreen
        # RESIZABLE gives the window a real title bar with a native maximize button
        # (next to minimize/close) - clicking it, or F11, or manually dragging an edge
        # all land in the VIDEORESIZE handler in handle_events().
        self.window = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H), pygame.RESIZABLE)
        self.screen = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
        pygame.display.set_caption(C.TITLE)
        self.clock = pygame.time.Clock()
        self.state = STATE_INTRO
        self.intro_timer = 0.0
        self.intro_joke = random.choice(INTRO_JOKES)
        self.name_entry_buffer = accounts.get_last_used()  # pre-filled, still editable
        self.name_entry_timer = 0.0
        self.player_name = ""
        self._autosave_cd = AUTOSAVE_INTERVAL
        self.select_idx = 0
        self.player = None
        self.feed = []  # [msg, color, remaining_time]
        self.popups = []  # [{x,y,amount,color,age}] floating combat text
        self._ui_click_active = False  # suppresses firing while a UI click (e.g. inventory) is held
        self._last_level = 1
        self.drag_from = None       # ("backpack", idx) or ("equip", slot_type) while a drag is in progress
        self.drag_start_pos = None
        self.pending_socket = None  # (source_backpack_idx, target_backpack_idx) awaiting an ENTER
        # confirmation - set by dragging a socketable UT onto a different weapon in the
        # backpack (see _transfer_item); requires an explicit confirm since it destroys
        # the source item, so a routine backpack-reorganizing drag can't trigger it by accident
        self._dblclick_slot = None  # ("backpack", idx) of the last plain click, for double-click-to-use
        self._dblclick_time = 0     # detection - use_backpack_slot() now fires on a DOUBLE click, not a
        # single one, so a single click is free for trade-offering/bag-withdraw without also equipping/
        # consuming the item by accident
        self.DBLCLICK_MS = 350
        self.auto_fire_enabled = False  # I key: fires continuously without holding the mouse button
        self.right_panel_mode = "inventory"  # Tab key: switches inventory vs. pet stats in the right dock
        self._fire_buffer = 0.0  # seconds left to auto-fire a click that landed just before
        # the weapon's cooldown cleared - see _handle_firing / FIRE_BUFFER_WINDOW
        self.chat_open = False
        self.chat_buffer = ""
        self._chat_select_all = False
        self._speech_bubbles = []  # [{pid, text, age}] - "local" pid is always the player
        self.chat_log = []  # [{name, text}] persistent left-side log, cap ui.CHAT_LOG_STORE_CAP, scrollable via self.chat_scroll
        self.chat_scroll = 0  # wrapped-line offset from the newest line, 0 = pinned to the bottom
        self._ability_cd = 0.0

        self.nexus_map = world.TileMap(world.make_nexus())
        self.bazaar_map = world.TileMap(world.make_bazaar())
        self.vault_room_map = world.TileMap(world.make_vault_room())
        self.nexus_bot = NexusBot(self.nexus_map.center_world_pos())
        self.cam = world.Camera(C.SCREEN_W, C.SCREEN_H)
        # small, static, always-safe maps - no exploration/fog gameplay needed, just
        # shown fully-revealed from the start so the right-docked HUD is consistent
        # (minimap always present) across every live-play screen
        self.nexus_minimap = minimap.MinimapState()
        self.nexus_minimap.reveal_all(self.nexus_map)
        self.bazaar_minimap = minimap.MinimapState()
        self.bazaar_minimap.reveal_all(self.bazaar_map)
        self.vault_room_minimap = minimap.MinimapState()
        self.vault_room_minimap.reveal_all(self.vault_room_map)
        self.nexus_ambience = vfx.NexusAmbience()
        self._vault_return_state = STATE_NEXUS

        self.realm_sim = None
        self.bonus_sim = None
        self.realm_minimap = None
        self.bonus_minimap = None
        self._pre_bonus_pos = None
        self._portal_prompt = None  # (on_portal_fn, theme, kind, difficulty) while standing on/near a
        # portal, or None - see _update_sim/_trigger_portal_prompt. Entering is now a deliberate ENTER
        # key press with an on-screen prompt, not an automatic walk-over trigger.

        self.vault_items = []
        self.vault_chest = 0  # which of the VAULT_CHEST_COUNT chests is currently paged in
        self.open_bag_id = None  # id of the ground Bag currently shown in the drag-and-drop window
        self.weather_fx = weather.WeatherFX()
        self.realm_ambience = vfx.AmbientEvents([])  # open-Realm ambient flavor - kinds swapped
        # per-call based on the player's current biome (see _update_sim); bonus dungeons get
        # their own theme-fixed AmbientEvents instance inside RealmSim itself
        self._dust_cd = 0.0  # footstep-dust cooldown, see _update_sim
        self.bazaar_ground_items = spawn_bazaar_chests()  # permanent chests + whatever players drop
        self.death_info = None

    # ---------------------------------------------------------- lifecycle --
    def _nexus_spawn_pos(self):
        # a couple tiles off the exact center, which is where the Realm portal tile
        # sits - spawning ON the portal would auto-trigger goto-Realm the instant you
        # arrive (the tile-trigger fires on any tick you're standing on it)
        c = self.nexus_map.center_world_pos()
        return pygame.Vector2(c.x, c.y + C.TILE * 2)

    def start_run(self, cls_name):
        self.player = Player(cls_name, name=self.player_name, pid="local")
        self.player.load_title()
        # a fresh character only - never on resume_run, whose backpack_size/xp
        # are already whatever was persisted (see accounts.apply_unlocks's docstring)
        accounts.apply_unlocks(self.player, self.player_name)
        self.player.pos = self._nexus_spawn_pos()
        self.state = STATE_NEXUS
        self.realm_sim = None
        self.bonus_sim = None
        self._last_level = 1
        self._autosave_cd = AUTOSAVE_INTERVAL

    def resume_run(self, saved_state):
        """Reconstructs a Player from a previously-saved characters.load_character()
        dict (via the same full_state()/from_full_state() round-trip already used for
        co-op network sync) instead of starting a fresh level-1 character - see
        _submit_name_entry, which calls this when a save exists for the entered name."""
        self.player = Player.from_full_state(dict(saved_state, pid="local", name=self.player_name))
        self.player.alive = True  # a dead character is never saved (see characters.delete_character)
        self.player.pos = self._nexus_spawn_pos()
        self.state = STATE_NEXUS
        self.realm_sim = None
        self.bonus_sim = None
        self._last_level = self.player.level
        self._autosave_cd = AUTOSAVE_INTERVAL

    def _save_character_progress(self):
        if self.player is not None and self.player.alive:
            characters.save_character(self.player_name, self.player)

    def enter_realm(self):
        self.realm_sim = RealmSim(bonus=False)
        self.realm_minimap = minimap.MinimapState()
        self.player.pos = self.realm_sim.spawn_point()
        self.state = STATE_REALM

    def enter_bazaar(self):
        self.player.pos = self.bazaar_map.center_world_pos()
        self.state = STATE_BAZAAR

    def enter_bonus_room(self, theme="generic", kind=None, difficulty=None):
        self.bonus_sim = RealmSim(bonus=True, theme=theme, difficulty_name=difficulty)
        self.bonus_minimap = minimap.MinimapState()
        self._pre_bonus_pos = pygame.Vector2(self.player.pos)
        self.player.pos = self.bonus_sim.spawn_point()
        self.state = STATE_BONUS

    def leave_bonus_room(self, theme=None, kind=None, difficulty=None):
        # phase-2 access is now a walked-through door (see world.open_phase2_door,
        # RealmSim._maybe_open_phase2_door) opened by its own quest, not a portal-
        # teleport kind - no special-case needed here anymore, every portal touch
        # in a bonus room really does mean "leave the dungeon."
        self.bonus_sim = None
        self.player.pos = self._pre_bonus_pos or self.realm_sim.spawn_point()
        self.state = STATE_REALM

    def go_nexus(self):
        self.player.pos = self._nexus_spawn_pos()
        self.state = STATE_NEXUS
        self._save_character_progress()  # a frequent, natural checkpoint

    def enter_vault_room(self):
        c = self.vault_room_map.center_world_pos()
        # spawn a couple tiles off the portal (bottom-center), same anti-instant-
        # retrigger reasoning as _nexus_spawn_pos - land facing the chests instead
        self.player.pos = pygame.Vector2(c.x, c.y + C.TILE * 4)
        self.state = STATE_VAULT_ROOM

    def _leave_vault_room(self):
        self.player.pos = self._nexus_spawn_pos()
        self.player.pos.x -= C.TILE * 3  # away from the Vault entry tile itself
        self.state = STATE_NEXUS

    def _migrate_legacy_vault(self):
        """One-time migration from the pre-accounts era, where the single-player vault
        was always saved under the fixed key "singleplayer" rather than the player's
        name. Runs cheaply on every open_vault() call (self-heals even for a player
        who upgrades and doesn't visit the Vault first thing). Copies rather than
        deletes the legacy file - a rare one-time event, tiny file, and leaving it in
        place means a bug here can't destroy anyone's saved items."""
        if self.player_name == _LEGACY_SINGLEPLAYER_VAULT_KEY or vault_exists(self.player_name):
            return
        legacy_items = load_vault(_LEGACY_SINGLEPLAYER_VAULT_KEY)
        if not legacy_items:
            return
        save_vault(self.player_name, legacy_items)

    def open_vault(self, chest_index=0):
        self._migrate_legacy_vault()
        self.vault_items = load_vault(self.player_name)
        self.vault_chest = chest_index
        self._vault_return_state = self.state  # STATE_VAULT_ROOM now; STATE_NEXUS is a
        # legacy fallback kept for safety, from the pre-room era where the Vault tile
        # opened the modal directly
        self.state = STATE_VAULT

    def close_vault(self):
        save_vault(self.player_name, self.vault_items)
        self.state = self._vault_return_state
        self.drag_from = None  # defensive - a drag in progress when the Vault closes shouldn't leak into play
        # closing while still standing on the trigger tile would otherwise auto-reopen
        # it the very next tick (_interact_nexus_tile/_interact_vault_room_tile fires
        # again) - same insta-retrigger bug class as spawning on a portal tile, same
        # fix: step off it
        if self.state == STATE_VAULT_ROOM:
            if self.vault_room_map.tile_at(self.player.pos.x, self.player.pos.y) == world.CHEST:
                self.player.pos.y += C.TILE * 1.5
        elif self.nexus_map.tile_at(self.player.pos.x, self.player.pos.y) == world.VAULT_TILE:
            self.player.pos.x += C.TILE * 1.5

    def die(self):
        earned = accounts.award_echoes_for_death(self.player_name, self.player._echoes_this_life)
        self.death_info = dict(level=self.player.level, kills=self.player.kills,
                                cls=self.player.cls_name, earned_echoes=earned)
        # permadeath means what it says - the saved character (if any) is gone for
        # good, not just marked dead, so the next login/respawn starts completely
        # fresh rather than resuming a corpse
        characters.delete_character(self.player_name)
        self.state = STATE_DEAD

    def push_feed(self, msg, color):
        self.feed.insert(0, [msg, color, 4.0])
        self.feed = self.feed[:4]

    def _toggle_fullscreen(self):
        # some display drivers/multi-monitor setups can raise pygame.error on a
        # FULLSCREEN mode switch (a real crash report came in for this) - never let a
        # display-mode change take the whole game down, just fall back to windowed.
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
            self.push_feed("Fullscreen unavailable on this display - staying windowed", (220, 140, 90))
        # always read back the ACTUAL size the driver gave us rather than trusting the
        # requested size - keeps canvas/window/camera consistent even if the OS/driver
        # clamps or ignores part of the request
        self._resize_canvas(*self.window.get_size())

    def _menu_items(self):
        """The O-key menu: an actual interactive list (Up/Down to move, Enter to
        activate), not just a read-only controls reference - RotMG's own options
        screen works the same way. The controls reference is still shown alongside it."""
        items = [
            (f"Auto-fire: {'ON' if self.auto_fire_enabled else 'OFF'}", self._menu_toggle_autofire),
            (f"Fullscreen: {'ON' if self.fullscreen else 'OFF'}", self._toggle_fullscreen),
            ("Reset camera rotation", self.cam.reset_rotation),
        ]
        if self.state in (STATE_REALM, STATE_BONUS):
            mm = self._current_minimap()
            if mm is not None:
                items.append((f"Full map: {'OPEN' if mm.full_map_open else 'closed'}",
                               self._menu_toggle_full_map))
        if self.state != STATE_CLASS_SELECT:
            items.append(("Abandon run (Class Select)", self._menu_quit_to_class_select))
        items.append(("Close menu", self._menu_close))
        return items

    def _menu_toggle_autofire(self):
        self.auto_fire_enabled = not self.auto_fire_enabled

    def _menu_toggle_full_map(self):
        mm = self._current_minimap()
        if mm is not None:
            mm.full_map_open = not mm.full_map_open

    def _menu_quit_to_class_select(self):
        self.state = STATE_CLASS_SELECT
        self.help_open = False

    def _menu_close(self):
        self.help_open = False

    MAX_CANVAS_DIM = 2560  # caps the rotation-buffer allocation on very large/4K displays

    def _resize_canvas(self, w, h):
        # the render canvas always matches the real window pixel-for-pixel - no scale
        # factor between them - which is also what fixes mouse-aim being off in
        # fullscreen/resized windows: pygame.mouse.get_pos() is in window space, and
        # self.cam.inverse() assumes that space matches C.SCREEN_W/H exactly.
        w = max(320, min(self.MAX_CANVAS_DIM, w))
        h = max(240, min(self.MAX_CANVAS_DIM, h))
        C.SCREEN_W, C.SCREEN_H = w, h
        self.screen = pygame.Surface((w, h))
        self.cam.screen_w, self.cam.screen_h = w, h

    # ---------------------------------------------------------------- run --
    def run(self):
        while True:
            dt = self.clock.tick(C.FPS) / 1000.0
            dt = min(dt, 0.05)
            dt = vfx.apply_hitstop(dt)
            if not self.handle_events():
                break
            self.update(dt)
            self.draw()
            # the game always renders onto a fixed-size canvas, then that canvas is
            # scaled to whatever the real window/fullscreen size is - this works on
            # any display backend, unlike pygame.SCALED which needs a render backend
            # that isn't always available (e.g. it failed outright under headless test)
            if self.window.get_size() == self.screen.get_size():
                self.window.blit(self.screen, (0, 0))
            else:
                pygame.transform.scale(self.screen, self.window.get_size(), self.window)
            pygame.display.flip()
        self._save_character_progress()
        pygame.quit()
        sys.exit()

    # ------------------------------------------------------------- events --
    CHAT_STATES = (STATE_NEXUS, STATE_BAZAAR, STATE_VAULT_ROOM, STATE_REALM, STATE_BONUS)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if self.state == STATE_INTRO:
                if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    self.state = STATE_NAME_ENTRY
                    self.name_entry_timer = 0.0
                continue
            if self.state == STATE_NAME_ENTRY:
                if event.type == pygame.KEYDOWN:
                    self._handle_name_entry_key(event)
                continue
            if event.type == pygame.KEYDOWN:
                if self.chat_open:
                    self._handle_chat_key(event)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.pending_socket is not None:
                    self._apply_pending_socket()
                elif (event.key == pygame.K_RETURN and self.state in self.CHAT_STATES and not self.help_open
                      and self._portal_prompt is None):
                    # standing near a portal takes priority over opening chat -
                    # see the STATE_REALM/STATE_BONUS branches below
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
                elif self.echo_shop_open and event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_w, pygame.K_s):
                    items = self._echo_shop_items()
                    step = -1 if event.key in (pygame.K_UP, pygame.K_w) else 1
                    self.echo_shop_selected = (self.echo_shop_selected + step) % len(items)
                elif self.echo_shop_open and event.key == pygame.K_RETURN:
                    _, action = self._echo_shop_items()[self.echo_shop_selected]
                    action()
                elif event.key == pygame.K_i and self.state in (STATE_REALM, STATE_BONUS):
                    self.auto_fire_enabled = not self.auto_fire_enabled
                    self.push_feed(f"Auto-fire {'ON' if self.auto_fire_enabled else 'OFF'}",
                                    (150, 220, 255) if self.auto_fire_enabled else (170, 170, 180))
                elif (event.key == pygame.K_TAB
                      and self.state in (STATE_NEXUS, STATE_BAZAAR, STATE_REALM, STATE_BONUS)):
                    self.right_panel_mode = "pet" if self.right_panel_mode == "inventory" else "inventory"
                elif event.key == pygame.K_SPACE and self.state in (STATE_REALM, STATE_BONUS):
                    self._use_ability()
                elif (event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT)
                      and self.state in (STATE_REALM, STATE_BONUS) and self.player is not None):
                    self.player.try_dash()
                elif event.key == pygame.K_m and self._current_minimap() is not None:
                    self._current_minimap().full_map_open = not self._current_minimap().full_map_open
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    self._zoom_minimap(minimap.ZOOM_STEP)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    self._zoom_minimap(-minimap.ZOOM_STEP)
                elif event.key == pygame.K_ESCAPE and self.pending_socket is not None:
                    self.pending_socket = None
                elif event.key == pygame.K_ESCAPE:
                    if self._map_open():
                        self._current_minimap().full_map_open = False
                    elif self.help_open:
                        self.help_open = False
                    elif self.echo_shop_open:
                        self.echo_shop_open = False
                    elif self.state == STATE_VAULT:
                        pass  # closing the Vault is click-only now (see vault_close_button_rect) - never Enter/Escape
                    else:
                        return False
                elif self.state == STATE_CLASS_SELECT:
                    self._class_select_key(event.key)
                elif self.state == STATE_REALM:
                    if event.key == pygame.K_r:
                        self.go_nexus()
                    elif event.key == pygame.K_f:
                        self._context_action()
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self._portal_prompt is not None:
                        self._trigger_portal_prompt()
                    elif pygame.K_1 <= event.key <= pygame.K_8:
                        self.use_backpack_slot(event.key - pygame.K_1)
                elif self.state == STATE_BONUS:
                    if event.key == pygame.K_r:
                        self.leave_bonus_room()
                    elif event.key == pygame.K_f:
                        self._context_action()
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self._portal_prompt is not None:
                        self._trigger_portal_prompt()
                    elif pygame.K_1 <= event.key <= pygame.K_8:
                        self.use_backpack_slot(event.key - pygame.K_1)
                elif self.state == STATE_NEXUS and event.key == pygame.K_f:
                    self._context_action()
                elif self.state == STATE_DEAD:
                    if event.key == pygame.K_RETURN:
                        self.state = STATE_CLASS_SELECT
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.help_open and ui.help_close_button_rect(self._menu_items()).collidepoint(event.pos):
                    self.help_open = False
                elif self.help_open:
                    items = self._menu_items()
                    for i, rect in enumerate(ui.help_menu_item_rects(items)):
                        if rect.collidepoint(event.pos):
                            self.menu_selected = i
                            _, action = items[i]
                            action()
                            break
                elif self.echo_shop_open and ui.echo_shop_close_button_rect(self._echo_shop_items()).collidepoint(event.pos):
                    self.echo_shop_open = False
                elif self.echo_shop_open:
                    items = self._echo_shop_items()
                    for i, rect in enumerate(ui.echo_shop_menu_item_rects(items)):
                        if rect.collidepoint(event.pos):
                            self.echo_shop_selected = i
                            _, action = items[i]
                            action()
                            break
                elif self.state == STATE_VAULT:
                    if not self._vault_click_extras(event.pos):
                        self._inventory_mouse_down(event.pos)
                elif self.state == STATE_CLASS_SELECT:
                    self._class_select_click(event.pos)
                elif self.state == STATE_DEAD:
                    self._death_screen_click(event.pos)
                elif self._current_minimap() is not None and self._minimap_button_click(event.pos):
                    pass
                elif (self._current_bag() is not None
                      and ui.bag_window_close_button_rect(self.cam(self._current_bag().pos)).collidepoint(event.pos)):
                    self.open_bag_id = None
                elif (not self.chat_open and self.state in self.CHAT_STATES
                      and ui.chat_log_rect(self.chat_log).collidepoint(event.pos)):
                    self.chat_open = True
                    self.chat_buffer = ""
                elif self.state in (STATE_NEXUS, STATE_BAZAAR, STATE_VAULT_ROOM, STATE_REALM, STATE_BONUS):
                    self._inventory_mouse_down(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.drag_from is not None:
                    if self.state == STATE_VAULT:
                        self._vault_mouse_up(event.pos)
                    else:
                        self._inventory_mouse_up(event.pos)
                self._ui_click_active = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                # right-click a backpack item = auto-drop it (only where there's
                # actual ground to drop it on); anywhere else, right-click keeps its
                # existing "open the nearest ground bag" meaning
                slot = self._slot_at(event.pos) if self.state in (STATE_REALM, STATE_BONUS, STATE_BAZAAR) else None
                if slot is not None and slot[0] == "backpack" and slot[1] < len(self.player.backpack):
                    self._right_click_drop_backpack_slot(slot[1])
                else:
                    self._try_loot()
            elif event.type == pygame.MOUSEWHEEL:
                if ui.chat_log_rect(self.chat_log).collidepoint(pygame.mouse.get_pos()):
                    max_scroll = ui.chat_log_max_scroll(self.chat_log)
                    self.chat_scroll = max(0, min(max_scroll, self.chat_scroll + event.y))
                else:
                    self._zoom_minimap(event.y * minimap.ZOOM_STEP)
            elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                # covers the native maximize button (next to minimize/close) and manual
                # edge-dragging, not just F11 - both keep the canvas pixel-matched to the window
                self.window = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                self._base_size = self.window.get_size()
                self._resize_canvas(*self._base_size)
        return True

    def _current_minimap(self):
        if self.state == STATE_REALM:
            return self.realm_minimap
        if self.state == STATE_BONUS:
            return self.bonus_minimap
        if self.state == STATE_NEXUS:
            return self.nexus_minimap
        if self.state == STATE_BAZAAR:
            return self.bazaar_minimap
        if self.state == STATE_VAULT_ROOM:
            return self.vault_room_minimap
        return None

    def _map_open(self):
        mm = self._current_minimap()
        return mm is not None and mm.full_map_open

    def _slot_at(self, pos):
        """Hit-tests an open bag window (if any) first, then the equip bar, then the
        backpack grid - returning ("bag", idx), ("equip", slot_type), ("backpack", idx),
        or None. The Vault is its own full-page state with its own layout entirely
        (its own backpack row + chest grid, not the normal HUD dock), so it's handled
        as a separate branch: ("backpack", idx) there refers to the same underlying
        player.backpack list, just via the Vault screen's own slot rects."""
        if self.state == STATE_VAULT:
            for i, rect in enumerate(ui._vault_backpack_slot_rects(self.player)):
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
        pet_rect = ui.pet_feed_target_rect(self.player)
        if pet_rect is not None and pet_rect.collidepoint(pos):
            return ("pet", None)
        for rect, slot_type in ui.equip_slot_rects():
            if rect.collidepoint(pos):
                return ("equip", slot_type)
        for i, rect in enumerate(ui.backpack_slot_rects(self.player)):
            if rect.collidepoint(pos):
                return ("backpack", i)
        return None

    def _dragged_item(self):
        if self.drag_from is None:
            return None
        kind, key = self.drag_from
        if kind == "backpack":
            return self.player.backpack[key] if key < len(self.player.backpack) else None
        if kind == "bag":
            bag = self._current_bag()
            return bag.items[key] if bag is not None and key < len(bag.items) else None
        if kind == "vault":
            return self.vault_items[key] if key < len(self.vault_items) else None
        return getattr(self.player, key)

    def _inventory_mouse_down(self, pos):
        """Picks up whatever's in the clicked slot so it can be dragged. Also suppresses
        firing for as long as the click/drag is held, so it doesn't waste a shot."""
        slot = self._slot_at(pos)
        if slot is None:
            return
        kind, key = slot
        if kind == "backpack":
            has_item = key < len(self.player.backpack)
        elif kind == "bag":
            bag = self._current_bag()
            has_item = bag is not None and key < len(bag.items)
        elif kind == "vault":
            has_item = key < len(self.vault_items) and self.vault_items[key] is not None
        elif kind == "pet":
            has_item = False  # the pet panel is a drop TARGET only (feed an item onto it) -
            # there's nothing to pick UP and drag out of it
        else:
            has_item = getattr(self.player, key) is not None
        if has_item:
            self.drag_from = slot
            self.drag_start_pos = pos
            self._ui_click_active = True
            self.pending_socket = None  # a fresh drag cancels an unconfirmed socket request

    def _apply_pending_socket(self):
        if self.pending_socket is None:
            return
        i, j = self.pending_socket
        self.pending_socket = None
        p = self.player
        if not (i < len(p.backpack) and j < len(p.backpack)) or i == j:
            return
        ok, msg = apply_socket(p.backpack[i], p.backpack[j])
        color = (150, 220, 150) if ok else (220, 150, 90)
        if ok:
            p.backpack.pop(i)
        self.push_feed(msg, color)

    def _inventory_mouse_up(self, pos):
        origin = self.drag_from
        self.drag_from = None
        dest = self._slot_at(pos)
        dropped_far = math.hypot(pos[0] - self.drag_start_pos[0], pos[1] - self.drag_start_pos[1]) > 6
        if origin[0] == "bag":
            # bag -> backpack/equip only (never back into a ground bag) - a plain
            # click on a bag slot is also a quick withdraw, matching the backpack's
            # own click-to-equip convenience. Dragging onto a SPECIFIC backpack slot
            # (dest[0]=="backpack") swaps with whatever's already there if the
            # backpack is full - see withdraw_from_bag's target_idx.
            if not dropped_far or (dest is not None and dest[0] in ("backpack", "equip")):
                target_idx = dest[1] if dest is not None and dest[0] == "backpack" and dropped_far else None
                self._bag_withdraw(origin[1], target_idx=target_idx)
            return
        if not dropped_far or dest == origin:
            # a plain click (no real drag) no longer equips/uses by itself - that's now
            # a DOUBLE click (see DBLCLICK_MS); single click is reserved for picking the
            # item up to drag and (elsewhere) trade-offering, matching RotMG's own
            # click semantics (right-click=drop, double-click=use, single-click=pick up)
            if not dropped_far and origin[0] == "backpack":
                now = pygame.time.get_ticks()
                if self._dblclick_slot == origin and now - self._dblclick_time <= self.DBLCLICK_MS:
                    self.use_backpack_slot(origin[1])
                    self._dblclick_slot = None
                else:
                    self._dblclick_slot = origin
                    self._dblclick_time = now
            return
        if dest is None:
            # dragged clean off the inventory bar, into the play area - drop it on the ground
            item = self._take_item_from_slot(origin)
            if item is None:
                return
            if self.state in (STATE_REALM, STATE_BONUS, STATE_BAZAAR):
                self._drop_item(item)
                self.push_feed(f"Dropped {item.display_name}", item.color)
            else:
                self._put_item_back(origin, item)
            return
        self._transfer_item(origin, dest)

    def _take_item_from_slot(self, origin):
        kind, key = origin
        p = self.player
        if kind == "backpack":
            return p.backpack.pop(key) if key < len(p.backpack) else None
        it = getattr(p, key)
        setattr(p, key, None)
        return it

    def _put_item_back(self, origin, item):
        kind, key = origin
        p = self.player
        if kind == "backpack":
            p.backpack.insert(key, item) if key <= len(p.backpack) else p.backpack.append(item)
        else:
            setattr(p, key, item)

    def _drop_item(self, item):
        rarity_key = "white" if item.is_ut else "purple" if (item.tier or 0) >= 7 else "brown"
        if self.state not in (STATE_REALM, STATE_BONUS, STATE_BAZAAR):
            return
        g = Bag([item], self.player.pos, dropped_by=self.player.pid, rarity_key=rarity_key)
        self._current_bag_list().append(g)
        audio.play_drop()

    def _right_click_drop_backpack_slot(self, idx):
        """Right-click auto-drop - RotMG's own inventory convention (right-click =
        drop instantly, no drag needed)."""
        p = self.player
        if idx >= len(p.backpack):
            return
        item = p.backpack.pop(idx)
        self._drop_item(item)
        self.push_feed(f"Dropped {item.display_name}", item.color)

    def _transfer_item(self, origin, dest):
        """Performs a drag-and-drop transfer between two inventory slots. Invalid drops
        (wrong item type for the target equip slot, etc.) are silently cancelled."""
        p = self.player
        if origin[0] == "backpack" and dest[0] == "backpack":
            i, j = origin[1], dest[1]
            if i < len(p.backpack) and j < len(p.backpack):
                src, tgt = p.backpack[i], p.backpack[j]
                if tgt.slot == SLOT_WEAPON and src is not tgt and identify_proc_kind(src) is not None:
                    # a destructive action (consumes src) - requires an explicit ENTER
                    # confirm rather than applying instantly on drop, see handle_events
                    self.pending_socket = (i, j)
                    self.push_feed(f"Press ENTER to socket {src.name}'s proc onto {tgt.display_name} "
                                    f"(consumes {src.name})", (200, 180, 255))
                    return
            p.swap_backpack(origin[1], dest[1])
        elif origin[0] == "backpack" and dest[0] == "equip":
            i, slot_type = origin[1], dest[1]
            if i < len(p.backpack) and p.backpack[i].slot == slot_type:
                it = p.backpack.pop(i)
                p.equip(it, backpack_idx=i)
                self.push_feed(f"Equipped {it.display_name}", it.color)
        elif origin[0] == "equip" and dest[0] == "backpack":
            slot_type, j = origin[1], dest[1]
            it = getattr(p, slot_type)
            if it is None:
                return
            if j < len(p.backpack):
                old_bp_item = p.backpack[j]
                if old_bp_item.slot != slot_type:
                    return
                p.backpack[j] = it
                setattr(p, slot_type, old_bp_item)
            elif p.unequip(slot_type):
                self.push_feed(f"Unequipped {it.display_name}", it.color)
        elif origin[0] == "backpack" and dest[0] == "pet":
            i = origin[1]
            if i < len(p.backpack):
                it = p.backpack[i]
                if p.feed_pet(i):
                    self.push_feed(f"Fed {it.display_name} to your pet", (170, 220, 255))
                else:
                    self.push_feed("Can't feed that to your pet", (220, 150, 90))
        elif origin[0] == "backpack" and dest[0] == "bag":
            # deposit INTO the currently-open container - only a BazaarChest accepts
            # this (a regular loot Bag stays take-only, see withdraw_from_bag's own
            # "bag -> backpack/equip only" docstring)
            bag = self._current_bag()
            if isinstance(bag, BazaarChest):
                i = origin[1]
                if i < len(p.backpack) and not bag.is_full():
                    it = p.backpack.pop(i)
                    bag.add_item(it)

    NAME_ENTRY_MAX_LEN = 16  # matches server.py's join-name cap, same identity system

    def _handle_name_entry_key(self, event):
        if event.key == pygame.K_RETURN:
            self._submit_name_entry()
        elif event.key == pygame.K_BACKSPACE:
            self.name_entry_buffer = self.name_entry_buffer[:-1]
        elif event.unicode and event.unicode.isprintable() and len(self.name_entry_buffer) < self.NAME_ENTRY_MAX_LEN:
            self.name_entry_buffer += event.unicode

    def _submit_name_entry(self):
        name = self.name_entry_buffer.strip()[:self.NAME_ENTRY_MAX_LEN] or "You"
        self.player_name = name
        accounts.touch_account(name)
        accounts.set_last_used(name)
        saved = characters.load_character(name)
        if saved is not None:
            self.resume_run(saved)
        else:
            self.state = STATE_CLASS_SELECT

    def _class_select_key(self, key):
        cols = ui._CLASS_COLS
        n = len(ui.CLASS_ORDER)
        if key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.select_idx = (self.select_idx + (1 if key == pygame.K_RIGHT else -1)) % n
        elif key in (pygame.K_UP, pygame.K_DOWN):
            step = cols if key == pygame.K_DOWN else -cols
            new_idx = self.select_idx + step
            if 0 <= new_idx < n:
                self.select_idx = new_idx
        elif key == pygame.K_RETURN:
            self.start_run(ui.CLASS_ORDER[self.select_idx])

    def _class_select_click(self, mouse_pos):
        """Mouse-driven class select, alongside the existing keyboard path
        (_class_select_key) - clicking a tile picks AND confirms in one click,
        matching how a real menu button behaves."""
        for rect, cls in ui.class_select_tile_rects():
            if rect.collidepoint(mouse_pos):
                self.select_idx = ui.CLASS_ORDER.index(cls)
                self.start_run(cls)
                return

    def _death_screen_click(self, mouse_pos):
        if ui.death_screen_button_rect().collidepoint(mouse_pos):
            self.state = STATE_CLASS_SELECT

    def _interact_nexus_tile(self):
        tile = self.nexus_map.tile_at(*self.player.pos)
        if tile == world.PORTAL:
            self.enter_realm()
        elif tile == world.BAZAAR_PORTAL:
            self.enter_bazaar()
        elif tile == world.VAULT_TILE:
            self.enter_vault_room()
        elif tile == world.ECHO_KEEPER_TILE and not self.echo_shop_open:
            self._open_echo_shop()

    # ------------------------------------------------------------ Echo Keeper --
    def _echo_shop_items(self):
        """(label, action) pairs, same shape as _menu_items()'s O-key menu -
        an already-owned/maxed row just gets a no-op action so Enter on it is safe."""
        unlocks = accounts.get_unlocks(self.player_name)
        slots = int(unlocks.get("backpack_slots", 0))
        items = []
        if slots < accounts.MAX_BACKPACK_BONUS_SLOTS:
            cost = accounts.BACKPACK_SLOT_COST + slots * accounts.BACKPACK_SLOT_COST_STEP
            items.append((f"+1 Backpack Slot - {cost} Echoes ({slots}/{accounts.MAX_BACKPACK_BONUS_SLOTS})",
                          self._buy_backpack_slot))
        else:
            items.append(("Backpack Slots: MAXED", lambda: None))
        if unlocks.get("starting_xp_boost"):
            items.append(("Starting XP Boost: OWNED", lambda: None))
        else:
            items.append((f"Starting XP Boost - {accounts.STARTING_XP_COST} Echoes (future characters)",
                          self._buy_starting_xp))
        items.append(("Close", self._close_echo_shop))
        return items

    def _open_echo_shop(self):
        self.echo_shop_open = True
        self.echo_shop_selected = 0

    def _close_echo_shop(self):
        self.echo_shop_open = False

    def _buy_backpack_slot(self):
        ok, msg = accounts.buy_backpack_slot(self.player_name)
        self.push_feed(msg, (150, 230, 210) if ok else (220, 150, 90))
        if ok and self.player is not None:
            self.player.backpack_size += 1

    def _buy_starting_xp(self):
        ok, msg = accounts.buy_starting_xp_boost(self.player_name)
        self.push_feed(msg, (150, 230, 210) if ok else (220, 150, 90))

    def _vault_room_chest_index(self, pos):
        """Chests are numbered in row-major grid order, matching the layout
        make_vault_room() lays them out in - stable regardless of draw order."""
        grid = self.vault_room_map.grid
        tx, ty = int(pos.x // C.TILE), int(pos.y // C.TILE)
        idx = 0
        for y in range(len(grid)):
            for x in range(len(grid[0])):
                if grid[y][x] == world.CHEST:
                    if (x, y) == (tx, ty):
                        return idx
                    idx += 1
        return 0

    def _interact_vault_room_tile(self):
        tile = self.vault_room_map.tile_at(*self.player.pos)
        if tile == world.PORTAL:
            self._leave_vault_room()
        elif tile == world.CHEST:
            self.open_vault(self._vault_room_chest_index(self.player.pos))

    def _vault_click_extras(self, mouse_pos):
        """Close button and chest tabs stay click-only (they're not items) - checked
        before falling through to the generic drag-and-drop dispatch. Returns True
        if the click was handled here."""
        if ui.vault_close_button_rect().collidepoint(mouse_pos):
            self.close_vault()
            return True
        for i, rect in enumerate(ui.vault_chest_tab_rects()):
            if rect.collidepoint(mouse_pos):
                self.vault_chest = i
                return True
        return False

    def _vault_mouse_up(self, pos):
        """Vault <-> backpack drag-and-drop (or a plain click, which does the same
        thing instantly) - mirrors _inventory_mouse_up's shape but the Vault is its
        own full-page state with its own slot rects, so it gets its own small
        dispatcher rather than overloading the normal play-screen one.

        Each chest is real, independent 8-slot storage now (see items.load_vault) -
        a plain-click deposit fills the first empty slot of the CURRENTLY VIEWED
        chest specifically (never a different one), and dragging onto a specific
        occupied vault/backpack slot SWAPS the two items instead of failing,
        matching RotMG's own "drag onto a full slot to swap" convention."""
        origin = self.drag_from
        self.drag_from = None
        if origin is None:
            return
        dest = self._slot_at(pos)
        dropped_far = math.hypot(pos[0] - self.drag_start_pos[0], pos[1] - self.drag_start_pos[1]) > 6
        p = self.player
        if origin[0] == "backpack":
            idx = origin[1]
            if idx >= len(p.backpack):
                return
            if dropped_far and dest is not None and dest[0] == "vault":
                slot = dest[1]
                if self.vault_items[slot] is None:
                    self.vault_items[slot] = p.backpack.pop(idx)
                else:
                    p.backpack[idx], self.vault_items[slot] = self.vault_items[slot], p.backpack[idx]
            elif not dropped_far:
                lo = self.vault_chest * VAULT_CHEST_SIZE
                slot = next((s for s in range(lo, lo + VAULT_CHEST_SIZE) if self.vault_items[s] is None), None)
                if slot is not None:
                    self.vault_items[slot] = p.backpack.pop(idx)
        elif origin[0] == "vault":
            slot = origin[1]
            if slot >= len(self.vault_items) or self.vault_items[slot] is None:
                return
            if dropped_far and dest is not None and dest[0] == "backpack":
                bidx = dest[1]
                if bidx < len(p.backpack):
                    p.backpack[bidx], self.vault_items[slot] = self.vault_items[slot], p.backpack[bidx]
                elif len(p.backpack) < p.backpack_size:
                    p.backpack.append(self.vault_items[slot])
                    self.vault_items[slot] = None
            elif not dropped_far:
                if len(p.backpack) < p.backpack_size:
                    p.backpack.append(self.vault_items[slot])
                    self.vault_items[slot] = None

    BAG_AUTO_CLOSE_RADIUS = 220  # walk this far from an open bag and its window auto-closes

    def _current_bag_list(self):
        if self.state == STATE_REALM:
            return self.realm_sim.ground_items
        if self.state == STATE_BONUS:
            return self.bonus_sim.ground_items
        if self.state == STATE_BAZAAR:
            return self.bazaar_ground_items
        return []

    def _current_bag(self):
        """The Bag backing the open drag-and-drop window, or None - also handles
        auto-close (walked away, or the bag emptied/expired from under us)."""
        if self.open_bag_id is None:
            return None
        bag = bag_by_id(self._current_bag_list(), self.open_bag_id)
        if bag is None or not bag.items or bag.pos.distance_to(self.player.pos) > self.BAG_AUTO_CLOSE_RADIUS:
            self.open_bag_id = None
            return None
        return bag

    def _try_loot(self):
        """Right-click: open the nearest bag in range as a drag-and-drop window
        (see game.entities.Bag / ui.draw_bag_window) instead of an instant grab -
        so you can see everything inside and choose what to take."""
        bag = find_nearby_bag(self._current_bag_list(), self.player.pos, self.player.pid)
        if bag is not None:
            self.open_bag_id = bag.id

    def _bag_withdraw(self, idx, target_idx=None):
        bag = self._current_bag()
        if bag is None:
            return None
        item = withdraw_from_bag(self._current_bag_list(), bag.id, idx, self.player, target_idx=target_idx)
        if item is not None:
            self.push_feed(f"Picked up {item.display_name}", item.color)
            audio.play_pickup()
        return item

    def _use_ability(self):
        """Success feed message comes from sim.events (see _try_loot's docstring) -
        only the failure case (no MP, no ability, still on cooldown) is pushed here,
        since use_ability() returns before ever touching sim.events for those."""
        sim = self.realm_sim if self.state == STATE_REALM else self.bonus_sim if self.state == STATE_BONUS else None
        if sim is None:
            return
        target = self.cam.inverse(pygame.mouse.get_pos())
        ok, msg = sim.use_ability(self.player, target, [self.player])
        if ok:
            audio.play_ability()
        elif msg:
            self.push_feed(msg, (220, 120, 120))

    BOT_TRADE_RADIUS = 55

    def _context_action(self):
        """F: one key, several meanings depending on where you're standing - fish
        near water in the Realm/Bonus room, make a wish at the Nexus fountain, or
        trade with the wandering Nexus Guide."""
        if self.state == STATE_NEXUS:
            on_fountain = self.nexus_map.tile_at(self.player.pos.x, self.player.pos.y) == world.NEXUS_FOUNTAIN
            near_bot = self.player.pos.distance_to(self.nexus_bot.pos) <= self.BOT_TRADE_RADIUS
            if not on_fountain and not near_bot:
                self.push_feed("Stand in the fountain to wish, or approach the Guide to trade", (170, 170, 185))
                return
            from game.items import wish_fountain
            old, new, err = wish_fountain(self.player)
            if err:
                self.push_feed(err, (220, 150, 90))
            else:
                audio.play_wish(new.is_ut)
                verdict = "JACKPOT!" if new.is_ut else ("Upgrade!" if new.tier > (old.tier or 0) else
                                                          "Sidegrade" if new.tier == (old.tier or 0) else "Downgrade...")
                if new.is_ut:
                    vfx.spawn_burst(self.player.pos, new.color, count=30, speed=(60, 200), life=(0.4, 0.85), radius=(2, 5))
                if near_bot and not on_fountain:
                    self.push_feed(f"The Guide trades your {old.name} for {new.display_name} ({verdict})", new.color)
                    self.nexus_bot.speech = f"Here, take this {new.display_name.split('] ')[-1]}."
                    self.nexus_bot.speech_age = 0.0
                else:
                    self.push_feed(f"{old.name} -> {new.display_name} ({verdict})", new.color)
            return
        sim = self.realm_sim if self.state == STATE_REALM else self.bonus_sim if self.state == STATE_BONUS else None
        if sim is None:
            return
        # the feed message comes from sim.events via _update_sim's generic consumption
        # loop, same as loot/ability - fish_action()'s return value is just for the sound
        item, _msg = sim.fish_action(self.player)
        if item:
            audio.play_pickup()

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
            self.push_feed(f"You: {text}", (190, 220, 255))
            self._speech_bubbles.append({"pid": "local", "text": text, "age": 0.0})
            self.chat_log.append({"name": self.player_name or "You", "text": text, "age": 0.0})
            self.chat_log = self.chat_log[-ui.CHAT_LOG_STORE_CAP:]

    def _handle_chat_command(self, cmd_text):
        parts = cmd_text.split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        if cmd == "nexus":
            if self.state == STATE_BONUS:
                self.leave_bonus_room()
            elif self.state in (STATE_REALM, STATE_BAZAAR):
                self.go_nexus()
            else:
                self.push_feed("Already in the Nexus", (170, 170, 185))
        elif cmd == "realm":
            if self.state == STATE_NEXUS:
                self.enter_realm()
            else:
                self.push_feed("/realm only works from the Nexus", (220, 150, 90))
        elif cmd == "vault":
            if self.state == STATE_NEXUS:
                self.open_vault()
            else:
                self.push_feed("/vault only works from the Nexus", (220, 150, 90))
        elif cmd == "bazaar":
            if self.state == STATE_NEXUS:
                self.enter_bazaar()
            else:
                self.push_feed("/bazaar only works from the Nexus", (220, 150, 90))
        elif cmd == "trade":
            self.push_feed("Trading needs another player - join a co-op server (coop_client.py)", (220, 150, 90))
        elif cmd == "help":
            self.push_feed("Commands: /nexus /realm /vault /bazaar (trading is co-op only)", (200, 200, 215))
        else:
            self.push_feed(f"Unknown command: /{cmd}", (220, 120, 120))

    def _minimap_button_click(self, pos):
        """Handles a click on the corner minimap's +/- zoom buttons. Returns True if
        the click landed on one (so the caller doesn't also treat it as something else)."""
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

    def _trigger_portal_prompt(self):
        """Called on an ENTER key press while self._portal_prompt is set (see
        _update_sim) - actually performs whatever standing near that portal
        offers (enter a dungeon / leave one / step into a phase-2 pocket)."""
        if self._portal_prompt is None:
            return
        on_portal_fn, theme, kind, difficulty, target_pos = self._portal_prompt
        self._portal_prompt = None
        if kind == "island_link":
            # a same-map teleport (see RealmSim._stamp_islands), not a dungeon-
            # instance swap - no on_portal_fn call, self.state/self.realm_sim untouched
            if target_pos is not None:
                self.player.pos = pygame.Vector2(target_pos)
            return
        on_portal_fn(theme, kind, difficulty)

    def use_backpack_slot(self, idx):
        p = self.player
        if idx >= len(p.backpack):
            return
        it = p.backpack[idx]
        if it.slot == "consumable":
            if p.use_potion(idx):
                self.push_feed(f"Used {it.name}", (200, 220, 255))
            else:
                self.push_feed(f"Permanent potion cap reached ({PERMANENT_POTION_CAP})", (220, 150, 90))
        elif it.slot == "temp_potion":
            p.use_potion(idx)
            self.push_feed(f"Used {it.name}", (200, 220, 255))
        elif it.slot == "egg":
            from game.items import PET_KINDS
            pet_name = PET_KINDS.get(it.pet_kind, {}).get("name", it.name)
            p.use_potion(idx)
            self.push_feed(f"{pet_name} hatched!", (170, 220, 255))
        elif it.slot == "shard":
            if self.state != STATE_REALM:
                self.push_feed("You can only open a Dungeon Shard out in the Realm.", (220, 120, 120))
                return
            theme_name = p.use_shard(idx)
            if theme_name is not None:
                theme_label = DUNGEON_THEMES.get(theme_name, DUNGEON_THEMES["generic"])["label"]
                # rolled NOW (not on arrival) so the difficulty can be shown as a
                # label on the portal itself before anyone steps through it
                diff_name = random.choices(BONUS_DIFFICULTIES, weights=[d["weight"] for d in BONUS_DIFFICULTIES])[0]["name"]
                self.realm_sim.portals.append(Portal(p.pos, theme=theme_name, kind="dungeon_shard",
                                                      difficulty=diff_name))
                self.push_feed(f"A {diff_name} portal to the {theme_label} tears open!", (190, 120, 230))
        else:
            p.backpack.pop(idx)
            p.equip(it, backpack_idx=idx)
            self.push_feed(f"Equipped {it.display_name}", it.color)

    # ------------------------------------------------------------- update --
    ROTATE_SPEED_DEG = 120  # RotMG has a real Q/E camera-rotate feature; this matches its feel

    _THEME_ZONE_FOR_STATE = {
        STATE_NEXUS: "nexus", STATE_BAZAAR: "bazaar", STATE_VAULT_ROOM: "nexus",
        STATE_VAULT: "vault", STATE_REALM: "realm", STATE_BONUS: "dungeon",
    }

    def update(self, dt):
        if self.state == STATE_INTRO:
            self.intro_timer += dt
            if self.intro_timer >= INTRO_DURATION:
                self.state = STATE_NAME_ENTRY
                self.name_entry_timer = 0.0
            return
        if self.state == STATE_NAME_ENTRY:
            self.name_entry_timer += dt
            return
        if self.player is not None and self.player.alive:
            self._autosave_cd -= dt
            if self._autosave_cd <= 0:
                self._autosave_cd = AUTOSAVE_INTERVAL
                self._save_character_progress()
        if self.state == STATE_BONUS and self.bonus_sim is not None:
            # a real distinct track per dungeon theme (Cave Warren, Frozen
            # Crypt, ...) instead of one generic "dungeon" track for all of
            # them - see game.audio.dungeon_zone_for_key.
            audio.play_theme(audio.dungeon_zone_for_key(self.bonus_sim.theme_key))
        else:
            zone = self._THEME_ZONE_FOR_STATE.get(self.state)
            if zone is not None:
                audio.play_theme(zone)
        for m in self.feed:
            m[2] -= dt
        self.feed = [m for m in self.feed if m[2] > 0]
        for b in self._speech_bubbles:
            b["age"] += dt
        self._speech_bubbles = [b for b in self._speech_bubbles if b["age"] < SPEECH_BUBBLE_LIFETIME]
        for m in self.chat_log:
            m["age"] = m.get("age", 0.0) + dt
        self.chat_log = [m for m in self.chat_log if m["age"] < CHAT_LOG_LIFETIME]

        # Typing in chat no longer pauses the whole sim (enemies/bullets/regen all
        # kept ticking is the correct co-op-consistent behavior - coop_client.py's
        # server-authoritative world never paused for a typing client either, only
        # that client's OWN movement/firing input was suppressed). keys=None below
        # is how Player.update()/​_handle_firing achieve the same thing locally.
        if self.state in (STATE_CLASS_SELECT, STATE_DEAD):
            pass
        elif not self.chat_open and not self.help_open:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_q]:
                self.cam.rotate(-self.ROTATE_SPEED_DEG * dt)
            if keys[pygame.K_e]:
                self.cam.rotate(self.ROTATE_SPEED_DEG * dt)

        if self.state in (STATE_NEXUS, STATE_BAZAAR, STATE_VAULT_ROOM):
            if self._map_open():
                return  # full map open - pause, same as in the Realm/Bonus Room
            tmap = {STATE_NEXUS: self.nexus_map, STATE_BAZAAR: self.bazaar_map,
                    STATE_VAULT_ROOM: self.vault_room_map}[self.state]
            # keys=None while the options/help menu (or the Echo Keeper shop) is
            # open too, same "typing in chat suppresses movement" pattern just
            # above - otherwise WASD leaks through the menu and moves the player
            # by accident while browsing it.
            keys = None if (self.chat_open or self.help_open or self.echo_shop_open) else pygame.key.get_pressed()
            self.player.update(dt, keys, tmap.bounds(), tmap.is_solid, tmap.speed_multiplier,
                                cam_angle=self.cam.angle)
            self.cam.follow(self.player.pos)
            vfx.update(dt)
            if self.state == STATE_NEXUS:
                self._interact_nexus_tile()
                self.nexus_bot.update(dt, self.nexus_map, self.player.pos.distance_to(self.nexus_bot.pos))
                if self.nexus_bot._speech_pending:
                    self.nexus_bot._speech_pending = False
                    self.chat_log.append({"name": self.nexus_bot.name, "text": self.nexus_bot.speech, "age": 0.0})
                    self.chat_log = self.chat_log[-ui.CHAT_LOG_STORE_CAP:]
                self.nexus_ambience.update(dt, self.nexus_map.bounds())
            elif self.state == STATE_VAULT_ROOM:
                self._interact_vault_room_tile()
            else:
                self.bazaar_ground_items = [g for g in self.bazaar_ground_items if g.update(dt)]
                if self.bazaar_map.tile_at(*self.player.pos) == world.PORTAL:
                    self.go_nexus()
        elif self.state == STATE_REALM:
            self._update_sim(dt, self.realm_sim, on_portal=self.enter_bonus_room)
        elif self.state == STATE_BONUS:
            self._update_sim(dt, self.bonus_sim, on_portal=self.leave_bonus_room)

    def _update_sim(self, dt, sim, on_portal):
        p = self.player
        mm = self.realm_minimap if sim is self.realm_sim else self.bonus_minimap
        if mm.full_map_open:
            # checking the full map is a menu screen - pause the action while it's up
            weather_kind = world.weather_for_tile(sim.realm_map.tile_at(p.pos.x, p.pos.y))
            mm.reveal(p.pos, radius=weather.reveal_radius_for(weather_kind, minimap.REVEAL_RADIUS_TILES))
            return
        keys = None if (self.chat_open or self.help_open) else pygame.key.get_pressed()
        prev_pos = pygame.Vector2(p.pos)
        p.update(dt, keys, sim.realm_map.bounds(), sim.is_solid_at, sim.realm_map.speed_multiplier,
                 cam_angle=self.cam.angle)
        self.cam.follow(p.pos)
        vfx.update(dt)
        dx, dy = vfx.shake_offset(dt)
        self.cam.pos.x += dx
        self.cam.pos.y += dy
        tile_here = sim.realm_map.tile_at(p.pos.x, p.pos.y)
        weather_kind = world.weather_for_tile(tile_here)
        mm.reveal(p.pos, radius=weather.reveal_radius_for(weather_kind, minimap.REVEAL_RADIUS_TILES))
        self.weather_fx.update(dt, weather_kind)
        self._dust_cd = max(0.0, self._dust_cd - dt)
        if self._dust_cd <= 0 and p.pos.distance_to(prev_pos) > 2:
            self._dust_cd = 0.15
            ground_color = world.TILE_COLORS.get(tile_here, (150, 140, 120))
            vfx.spawn_dust((p.pos.x, p.pos.y + 14), ground_color)
        if not sim.is_bonus_room:
            # bonus dungeons get their own theme-fixed ambient inside RealmSim itself
            # (see _ambient); the open Realm's flavor instead follows whichever
            # biome the LOCAL player currently stands in, so it's client-side/cosmetic
            # exactly like weather_fx already is, not simulated/broadcast
            biome_name = world.GROUND_TO_BIOME_NAME.get(tile_here)
            bounds = (p.pos.x - 300, p.pos.y - 300, p.pos.x + 300, p.pos.y + 300)
            self.realm_ambience.update(dt, bounds, kinds=vfx.REALM_AMBIENT_KINDS.get(biome_name))
        boss_before = sim.boss
        backpack_before = len(p.backpack)
        self._handle_firing(p, sim, dt)
        sim.update(dt, {p.pid: p})
        for pid, msg, color in sim.events:
            self.push_feed(msg, color)
        vfx.dispatch(sim.vfx_events)
        for kind, family, sx, sy in sim.sound_events:
            # a continent-sized realm can have combat/idle-barks happening anywhere -
            # without a distance check every one of those played at full volume as if
            # it were right next to you, which read as "random sounds" out of nowhere
            if (sx - p.pos.x) ** 2 + (sy - p.pos.y) ** 2 > SOUND_HEARING_RADIUS ** 2:
                continue
            if kind == "mob_hit":
                audio.play_mob_hit(family)
            elif kind == "mob_death":
                audio.play_mob_death(family)
            elif kind == "mob_bark":
                audio.play_mob_bark(family)
        for kind, text in sim.mob_speech_events:
            self.chat_log.append({"name": kind.replace("_", " ").title(), "text": text, "age": 0.0})
            self.chat_log = self.chat_log[-ui.CHAT_LOG_STORE_CAP:]
        hurt = False
        for x, y, amount, color in sim.damage_popups:
            self.popups.append({"x": x, "y": y, "amount": amount, "color": color, "age": 0.0})
            if color == (255, 90, 90):
                hurt = True
        if hurt:
            audio.play_hit()
        # (enemy-hit feedback now comes from sim.sound_events above - family-tinted
        # play_mob_hit() instead of one generic play_enemy_hit() for every kind)
        for pop in self.popups:
            pop["age"] += dt
        self.popups = [pop for pop in self.popups if pop["age"] < ui.DAMAGE_POPUP_LIFETIME]
        if p.level > self._last_level:
            audio.play_levelup()
            vfx.dispatch([("levelup", p.pos.x, p.pos.y, (255, 215, 90))])
            self._last_level = p.level
        if len(p.backpack) > backpack_before:
            audio.play_pickup()
        if sim.boss is not None and boss_before is None:
            audio.play_boss_spawn()
        if not p.alive:
            audio.play_death()
            vfx.spawn_burst(p.pos, (255, 90, 90), count=24, speed=(60, 220), life=(0.3, 0.65))
            self.die()
            self._portal_prompt = None
        elif on_portal:
            # standing near/on a portal no longer auto-triggers it - shows a
            # "press ENTER" prompt (bottom-right, see ui.draw_portal_prompt)
            # instead, and only actually enters on that key press
            entry = next((e for e in sim.portal_entries if e[0] == p.pid), None)
            self._portal_prompt = (on_portal, entry[1], entry[2], entry[3], entry[5]) if entry is not None else None
        # ready for next frame's handle_events() (ability/loot/fish/wish presses) to
        # safely append fresh events/popups without stepping on ones we haven't read
        # yet - see RealmSim.begin_tick()'s docstring
        sim.begin_tick()

    def _handle_firing(self, p, sim, dt):
        if self.chat_open or self.help_open:
            self._fire_buffer = 0.0
            return  # typing, or browsing the options menu, shouldn't also fire your weapon
        wants_fire = (self.auto_fire_enabled or pygame.mouse.get_pressed()[0]) and not self._ui_click_active
        if wants_fire:
            self._fire_buffer = FIRE_BUFFER_WINDOW
        elif self._fire_buffer > 0:
            self._fire_buffer = max(0.0, self._fire_buffer - dt)
        if self._fire_buffer > 0 and p.can_fire():
            self._fire_buffer = 0.0
            mx, my = pygame.mouse.get_pos()
            target = self.cam.inverse((mx, my))
            direction = target - p.pos
            if direction.length_squared() < 1:
                direction = p.facing
            direction = direction.normalize()
            weather_kind = world.weather_for_tile(sim.realm_map.tile_at(p.pos.x, p.pos.y))
            cone_deg = weather.aim_cone_for(weather_kind, AUTO_AIM_CONE_DEG)
            direction = auto_aim_direction(p.pos, direction, sim.enemies, cone_deg=cone_deg)
            p.register_fire()
            sim.player_fire(p, direction)
            audio.play_shoot(p.cls_name)

    # --------------------------------------------------------------- draw --
    def draw(self):
        s = self.screen
        s.fill(C.COL_BG)
        if self.state == STATE_INTRO:
            ui.draw_intro_screen(s, self.intro_timer, self.intro_joke)
        elif self.state == STATE_NAME_ENTRY:
            ui.draw_name_entry(s, self.name_entry_buffer, self.name_entry_timer)
        elif self.state == STATE_CLASS_SELECT:
            ui.draw_class_select(s, self.select_idx, mouse_pos=pygame.mouse.get_pos())
        elif self.state == STATE_NEXUS:
            self._draw_hub(self.nexus_map, self.nexus_minimap, "Nexus",
                            "Walk onto a portal: Realm | Vault | Bazaar")
        elif self.state == STATE_BAZAAR:
            self._draw_hub(self.bazaar_map, self.bazaar_minimap, "Bazaar",
                            "Drop items for others - walk onto the portal to return")
        elif self.state == STATE_VAULT_ROOM:
            self._draw_hub(self.vault_room_map, self.vault_room_minimap, "Vault",
                            "Walk onto a chest to open it - the portal returns to the Nexus")
        elif self.state == STATE_REALM:
            self._draw_sim(self.realm_sim, "The Godlands")
        elif self.state == STATE_BONUS:
            self._draw_sim(self.bonus_sim, f"{self.bonus_sim.theme_name} [{self.bonus_sim.difficulty['name']}]",
                            extra_hint="R or the portal to leave")
        elif self.state == STATE_VAULT:
            mp = pygame.mouse.get_pos()
            ui.draw_vault_screen(s, self.player, self.vault_items, VAULT_SLOTS, mp,
                                 selected_chest=self.vault_chest, dragging_from=self.drag_from)
            dragged = self._dragged_item()
            if dragged:
                ui.draw_dragged_item(s, dragged, mp)
        elif self.state == STATE_DEAD:
            d = self.death_info
            ui.draw_center_text(s, "YOU DIED",
                                 f"{d['cls'].title()} reached level {d['level']} with {d['kills']} kills. "
                                 f"Earned {d.get('earned_echoes', 0)} Echoes. "
                                 f"Permadeath - press Enter or click below to try again.", (220, 60, 60))
            ui.draw_death_screen_button(s, pygame.mouse.get_pos())
        if self.help_open:
            items = self._menu_items()
            self.menu_selected %= len(items)
            ui.draw_help_overlay(s, menu_items=items, selected_idx=self.menu_selected, mouse_pos=pygame.mouse.get_pos())
        if self.echo_shop_open:
            items = self._echo_shop_items()
            self.echo_shop_selected %= len(items)
            ui.draw_echo_shop_overlay(s, accounts.get_echoes(self.player_name), menu_items=items,
                                       selected_idx=self.echo_shop_selected, mouse_pos=pygame.mouse.get_pos())

    def _draw_right_switch_panel(self, s, mp):
        """Tab key (see handle_events) switches this dock slot between the
        inventory grid and pet stats - only one is ever drawn per frame, with
        a small tab-label strip above it so the key is discoverable. Falls
        back to inventory if there's no pet to show, so Tab can never leave
        the player looking at a blank panel."""
        mode = self.right_panel_mode
        if mode == "pet" and getattr(self.player, "pet", None) is None:
            mode = "inventory"
        ui.draw_panel_tabs(s, mode)
        if mode == "pet":
            ui.draw_pet_panel(s, self.player, dragging=self.drag_from is not None)
        else:
            ui.draw_inventory(s, self.player, mp, dragging_from=self.drag_from)

    def _draw_hub(self, tmap, mm, name, hint_text):
        s = self.screen
        if mm.full_map_open:
            minimap.draw_full_map(s, tmap, mm, self.player.pos, zone_name=name)
            return
        if tmap is self.nexus_map:
            tmap.draw_backdrop(s, self.cam)
        # RotMG itself works this way: Q/E turns the MAP, characters stay upright -
        # only the tile floor goes through the rotate-a-buffer pipeline; entities are
        # drawn straight onto the screen afterward with the (now rotation-aware)
        # self.cam, which places them correctly without tilting their sprite.
        world.render_rotated_world(s, self.cam, lambda surf, cam: tmap.draw(surf, cam, surf.get_size()))
        if tmap is self.bazaar_map:
            for g in self.bazaar_ground_items:
                g.draw(s, self.cam)
        elif tmap is self.nexus_map:
            self.nexus_bot.draw(s, self.cam)
            if self.nexus_bot.speech and self.nexus_bot.speech_age < self.nexus_bot.SPEECH_LIFETIME:
                ui.draw_speech_bubble(s, self.cam, self.nexus_bot.pos, self.nexus_bot.speech, self.nexus_bot.speech_age)
        self.player.draw(s, self.cam)
        self._draw_speech_bubbles(s)
        vfx.draw(s, self.cam)
        hint = ui._FONT_M.render(hint_text, True, (220, 210, 230))
        s.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, 82))
        if tmap is self.nexus_map:
            event_label = live_events.active_label()
            if event_label:
                banner = ui._FONT_S.render(f"Live event: {event_label}", True, (255, 220, 120))
                s.blit(banner, (C.SCREEN_W // 2 - banner.get_width() // 2, 104))
        ui.draw_hud(s, name, 0, False)
        ui.draw_fps_counter(s, self.clock.get_fps())
        mp = pygame.mouse.get_pos()
        ui.draw_player_panel(s, self.player, auto_fire=False)
        self._draw_right_switch_panel(s, mp)
        dragged = self._dragged_item()
        if dragged:
            ui.draw_dragged_item(s, dragged, mp)
        elif not self.drag_from and tmap is self.bazaar_map:
            ui.draw_ground_item_tooltip(s, self.cam, mp, self.bazaar_ground_items)
            ui.draw_nearby_loot_panel(s, [g for g in self.bazaar_ground_items
                                           if g.pos.distance_to(self.player.pos) <= 160])
        open_bag = self._current_bag()
        if open_bag is not None:
            ui.draw_bag_window(s, self.cam(open_bag.pos), open_bag.items, mp, dragging_from=self.drag_from)
        minimap.draw_corner(s, tmap, mm, self.player.pos)
        ui.draw_chat_log(s, self.chat_log, scroll=self.chat_scroll)
        if self.chat_open:
            ui.draw_chat_box(s, self.chat_buffer, selected=self._chat_select_all)

    def _draw_sim(self, sim, name, extra_hint=None):
        s = self.screen
        mm = self.realm_minimap if sim is self.realm_sim else self.bonus_minimap
        if mm.full_map_open:
            minimap.draw_full_map(s, sim.realm_map, mm, self.player.pos, portals=sim.portals, zone_name=name,
                                   enemies=sim.enemies)
            return
        fog = mm.explored if sim.is_bonus_room else None
        world.render_rotated_world(s, self.cam, lambda surf, cam: sim.realm_map.draw(surf, cam, surf.get_size(), fog=fog))
        for g in sim.ground_items:
            g.draw(s, self.cam)
        for pt in sim.portals:
            pt.draw(s, self.cam)
        ui.draw_portal_labels(s, self.cam, sim.portals)
        for ob in sim.obstacles:
            ob.draw(s, self.cam)
        for e in sim.enemies:
            # real line-of-sight (walls + live obstacles), not a static room-tag
            # match - a room-tag approach hid enemies that had physically wandered/
            # chased into the player's own room (tag set once at spawn, never
            # updated) and hid an entire room's pod the instant the player stood
            # one tile outside its rect even with a clear sightline in (no doors
            # in this dungeon style). has_line_of_sight is the same check already
            # used for enemy aggro/fire-gating, just applied to player visibility.
            if sim.is_bonus_room and not sim.has_line_of_sight(self.player.pos.x, self.player.pos.y,
                                                                 e.pos.x, e.pos.y):
                continue
            e.draw(s, self.cam)
            if e.speech and e.speech_age < ui.SPEECH_BUBBLE_LIFETIME:
                ui.draw_speech_bubble(s, self.cam, e.pos, e.speech, e.speech_age, text_color=ui.MOB_SPEECH_COLOR)
        for b in sim.bullets:
            b.draw(s, self.cam)
        self.player.draw(s, self.cam)
        if self.player.fishing_state is not None:
            vfx.draw_fishing_bobber(s, self.cam, self.player.pos, self.player.fishing_state)
        self._draw_speech_bubbles(s)
        vfx.draw(s, self.cam)
        ui.draw_damage_popups(s, self.cam, self.popups)
        torch_positions = [self.cam(pos) for pos in
                           world.nearby_torch_world_positions(sim.realm_map, self.player.pos.x, self.player.pos.y)]
        ui.draw_day_night_overlay(s, sim.light_level, sim.blood_moon_active, torch_positions)
        if not sim.is_bonus_room:
            ui.draw_day_night_clock(s, sim.light_level, sim.blood_moon_active)
        self.weather_fx.draw(s)
        ui.draw_hud(s, name, sim.kill_count, sim.boss is not None)
        ui.draw_fps_counter(s, self.clock.get_fps())
        if self._portal_prompt is not None:
            ui.draw_portal_prompt(s)
        if sim.is_bonus_room:
            ui.draw_quest_panel(s, sim.secret_quest, sim.secret_quest_progress, sim._quest_timer,
                                 secret_quest_target=sim._secret_quest_target,
                                 phase2_quest=sim.phase2_quest, phase2_progress=sim.phase2_quest_progress,
                                 phase2_quest_target=sim._phase2_quest_target)
        mp = pygame.mouse.get_pos()
        ui.draw_player_panel(s, self.player, auto_fire=self.auto_fire_enabled)
        self._draw_right_switch_panel(s, mp)
        dragged = self._dragged_item()
        if dragged:
            ui.draw_dragged_item(s, dragged, mp)
        elif not self.drag_from:
            ui.draw_ground_item_tooltip(s, self.cam, mp, sim.ground_items)
            ui.draw_nearby_loot_panel(s, sim.nearby_ground_items(self.player.pos))
        open_bag = self._current_bag()
        if open_bag is not None:
            ui.draw_bag_window(s, self.cam(open_bag.pos), open_bag.items, mp, dragging_from=self.drag_from)
        ui.draw_item_feed(s, self.feed)
        if extra_hint:
            hint = ui._FONT_S.render(extra_hint, True, (200, 170, 230))
            s.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, 82))
        minimap.draw_corner(s, sim.realm_map, mm, self.player.pos, portals=sim.portals, enemies=sim.enemies)
        ui.draw_chat_log(s, self.chat_log, scroll=self.chat_scroll)
        if self.chat_open:
            ui.draw_chat_box(s, self.chat_buffer, selected=self._chat_select_all)

    def _draw_speech_bubbles(self, s):
        for b in self._speech_bubbles:
            if b["pid"] == "local":
                ui.draw_speech_bubble(s, self.cam, self.player.pos, b["text"], b["age"], name=self.player.name)


def main():
    Game().run()


if __name__ == "__main__":
    main()

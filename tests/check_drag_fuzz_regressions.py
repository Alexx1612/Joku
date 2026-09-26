"""
Regressions found by fuzzing the real Game with random drags/clicks/keys and
forced zone transitions mid-drag (the long-open "I was dragging an item, went
through a portal, the game crashed" report):

- Firing with NO weapon equipped crashed: dragging the equipped weapon off the
  dock onto the world drops it (legit), and RealmSim.player_fire then did
  p.weapon.min_dmg on None -> AttributeError. Before the drag-cancel-on-zone-
  change hardening, "hold the weapon, walk through a portal, let go in the new
  zone" dropped it there - the very next shot crashed, matching the report.
  In co-op the same thing broke every server tick for everyone.
- Co-op client: GhostPortal borrowed only `draw = Portal.draw`, but Portal.draw
  also needs the class-level KIND_COLORS/ARCH_STONE and _draw_* helpers ->
  AttributeError (client crash) the first time any portal came into view.
- Co-op client: GhostBag borrowed Bag.draw, which reads len(self.items) - a
  ghost only carries `count` -> client crash the first time a loot bag was drawn.
- Co-op client: GhostChest had no bag_color/name, which the Bazaar's nearby-
  loot panel reads -> client crash on walking up to any Bazaar chest.

Plus a short fixed-seed fuzz smoke so this keeps being exercised.

Run with: .venv\\Scripts\\python.exe tests\\check_drag_fuzz_regressions.py
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import achievements, items, characters, accounts
achievements._DIR = tempfile.mkdtemp(prefix="rr_fuzzreg_ach_")
items.VAULT_DIR = tempfile.mkdtemp(prefix="rr_fuzzreg_vault_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_fuzzreg_char_")
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_fuzzreg_acc_")

import main
import server
from game import ui, constants as C
from game.entities import Player, Pet
from game.items import make_old_boot, make_egg, make_potion, STAT_KEYS

# every Game.enter_realm() generates a full 900x900 Realm (seconds each) - map
# generation isn't under test here, so reuse one open-Realm instance for the whole
# file (dungeon instances stay real: they're small and part of the transitions)
_RealmSim = main.RealmSim
_realm_cache = []


def _cached_realm_sim(*a, bonus=False, **kw):
    if bonus:
        return _RealmSim(*a, bonus=bonus, **kw)
    if not _realm_cache:
        _realm_cache.append(_RealmSim(*a, bonus=False, **kw))
    return _realm_cache[0]


main.RealmSim = _cached_realm_sim
# the first play of each zone's procedural music theme synthesizes ~20s of audio
# (10s+ each, ~75% of this file's runtime when profiled) - zone music has nothing
# to do with drag/zone-transition safety; one-shot SFX stay real
main.audio.play_theme = lambda *a, **kw: None


def _post(ev_type, **kw):
    pygame.event.post(pygame.event.Event(ev_type, **kw))


def _realm_game():
    g = main.Game()
    g.player_name = "FuzzReg"
    g.start_run("archer")
    g.enter_realm()
    return g


def _world_pos():
    return (C.SCREEN_W // 3, C.SCREEN_H // 2)  # open play area, clear of the dock


def check_sp_fire_after_dropping_weapon():
    g = _realm_game()
    weapon_rect = next(r for r, slot in ui.equip_slot_rects() if slot == "weapon")
    _post(pygame.MOUSEBUTTONDOWN, button=1, pos=weapon_rect.center)
    g.handle_events()
    assert g.drag_from == ("equip", "weapon")
    _post(pygame.MOUSEBUTTONUP, button=1, pos=_world_pos())
    g.handle_events()
    assert g.player.weapon is None, "dragging the weapon onto the world drops it"
    g.auto_fire_enabled = True  # fire every tick regardless of the (headless) mouse
    before = len(g.realm_sim.bullets)
    for _ in range(30):
        g.update(1 / 30)  # used to raise AttributeError in RealmSim.player_fire
        g.draw()
    assert not [b for b in g.realm_sim.bullets[before:] if b.owner == g.player.pid], "no weapon -> no shots"
    print("check_sp_fire_after_dropping_weapon: PASSED")


def check_sp_weapon_drag_through_portal_is_cancelled():
    """The reported scenario: weapon mid-drag in the Nexus, zone change, release
    in the Realm - the drag is dropped with the zone, the weapon stays equipped,
    and firing afterwards works."""
    g = main.Game()
    g.player_name = "FuzzPortal"
    g.start_run("wizard")
    weapon_rect = next(r for r, slot in ui.equip_slot_rects() if slot == "weapon")
    _post(pygame.MOUSEBUTTONDOWN, button=1, pos=weapon_rect.center)
    g.handle_events()
    assert g.drag_from == ("equip", "weapon")
    g.enter_realm()  # the portal
    g.update(1 / 30)
    _post(pygame.MOUSEBUTTONUP, button=1, pos=_world_pos())
    g.handle_events()
    assert g.drag_from is None and g.player.weapon is not None
    g.auto_fire_enabled = True
    for _ in range(10):
        g.update(1 / 30)
        g.draw()
    print("check_sp_weapon_drag_through_portal_is_cancelled: PASSED")


class _FakeSock:
    def sendall(self, data):
        pass


def check_coop_server_fire_without_weapon():
    state = server.ServerState()
    p = Player("archer", name="NoWeapon", pid="nw")
    s = server.Session("nw", _FakeSock(), p)
    s.zone = server.ZONE_REALM
    p.pos = state.realm_sim.spawn_point()
    state.sessions[s.pid] = s
    p.weapon = None
    s.last_input = {"move": [0, 0], "fire": True, "aim": [1, 0]}
    for _ in range(10):
        server.step(state, 1 / 30)  # used to raise inside step() -> every tick lost for everyone
    assert not [b for b in state.realm_sim.bullets if b.owner == p.pid]
    print("check_coop_server_fire_without_weapon: PASSED")


def check_coop_ghost_portal_draws_every_kind():
    import coop_client
    from game.entities import Portal
    surf = pygame.Surface((400, 300))
    cam = lambda pos: (int(pos[0]), int(pos[1]))
    for kind in list(Portal.KIND_COLORS) + ["island_link", "something_new"]:
        gp = coop_client.GhostPortal({"x": 200, "y": 150, "kind": kind, "difficulty": "Easy", "label": "Isle"}, t=1.3)
        gp.draw(surf, cam)  # used to raise AttributeError: no KIND_COLORS
    print("check_coop_ghost_portal_draws_every_kind: PASSED")


def check_coop_ghost_bag_draws():
    import coop_client
    from game.entities import Bag
    surf = pygame.Surface((400, 300))
    cam = lambda pos: (int(pos[0]), int(pos[1]))
    for n in (0, 1, 8):
        bag = Bag([make_old_boot() for _ in range(n)], pygame.Vector2(100, 100))
        coop_client.GhostBag(bag.net_state()).draw(surf, cam)  # used to raise: no attribute 'items'
    # Bazaar chests: the nearby-loot panel + hover tooltip over real chest ghosts
    from game.entities import spawn_bazaar_chests
    ghosts = [coop_client.GhostChest(ch.net_state()) for ch in spawn_bazaar_chests()]
    ghosts.append(coop_client.GhostBag(Bag([make_old_boot()], pygame.Vector2(5, 5)).net_state()))
    for g in ghosts:
        g.draw(surf, cam)
    ui.draw_nearby_loot_panel(surf, ghosts)  # used to raise: GhostChest has no 'bag_color'
    ui.draw_ground_item_tooltip(surf, cam, cam(ghosts[0].pos), ghosts)
    print("check_coop_ghost_bag_draws: PASSED")


def check_fuzz_smoke():
    """A few hundred frames of seeded random drags/clicks/keys with forced zone
    transitions (the full harness lives outside the repo; this is its fast core)."""
    rnd = random.Random(1234)
    mouse = [(400, 400)]
    real_get_pos, real_pressed = pygame.mouse.get_pos, pygame.mouse.get_pressed
    pygame.mouse.get_pos = lambda: mouse[0]
    pygame.mouse.get_pressed = lambda num_buttons=3: (False, False, False)
    try:
        g = main.Game()
        g.player_name = "FuzzSmoke"
        g.start_run("rogue")
        keys = [pygame.K_1, pygame.K_3, pygame.K_TAB, pygame.K_j, pygame.K_i, pygame.K_r, pygame.K_ESCAPE,
                pygame.K_RETURN, pygame.K_f, pygame.K_o, pygame.K_SPACE]
        transitions = [g.enter_realm, g.enter_bazaar, g.enter_vault_room, g.go_nexus,
                       lambda: g.open_vault(0) if g.state == main.STATE_VAULT_ROOM else None,
                       lambda: g.enter_bonus_room("cave") if g.state == main.STATE_REALM else None,
                       lambda: g.leave_bonus_room() if g.state == main.STATE_BONUS else None]
        mid_drag = 0
        for f in range(400):
            p = g.player
            if f % 50 == 0:
                p.backpack = p.backpack[:4] + [make_old_boot(), make_egg("hatchling"), make_potion(rnd.choice(STAT_KEYS))]
                if rnd.random() < 0.5:
                    p.pet = Pet("wisp", p.pos)
            pts = ([r.center for r in ui.backpack_slot_rects(p)] + [r.center for r, _ in ui.equip_slot_rects()]
                   + [ui.pet_tab_rect().center, _world_pos(), (rnd.randrange(C.SCREEN_W), rnd.randrange(C.SCREEN_H))])
            r = rnd.random()
            if r < 0.3:
                mouse[0] = rnd.choice(pts)
                _post(pygame.MOUSEBUTTONDOWN, button=1 if rnd.random() < 0.85 else 3, pos=mouse[0])
            elif r < 0.5:
                mouse[0] = rnd.choice(pts)
                _post(pygame.MOUSEMOTION, pos=mouse[0], rel=(1, 1), buttons=(1, 0, 0))
            elif r < 0.62:
                _post(pygame.MOUSEBUTTONUP, button=1, pos=mouse[0])
            elif r < 0.72:
                k = rnd.choice(keys)
                _post(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)
                _post(pygame.KEYUP, key=k, mod=0, unicode="", scancode=0)
            elif r < 0.80 and g.state not in (main.STATE_DEAD, main.STATE_CLASS_SELECT):
                mid_drag += g.drag_from is not None
                rnd.choice(transitions)()
            if g.state in (main.STATE_DEAD, main.STATE_CLASS_SELECT):
                g.start_run("rogue")
            if not g.handle_events():
                g.quit_confirm_open = False
            g.update(1 / 30)
            g.draw()
        assert mid_drag > 0, "the smoke run should actually exercise transitions mid-drag"
    finally:
        pygame.mouse.get_pos, pygame.mouse.get_pressed = real_get_pos, real_pressed
    print(f"check_fuzz_smoke: PASSED (400 frames, {mid_drag} transitions mid-drag)")


if __name__ == "__main__":
    check_sp_fire_after_dropping_weapon()
    check_sp_weapon_drag_through_portal_is_cancelled()
    check_coop_server_fire_without_weapon()
    check_coop_ghost_portal_draws_every_kind()
    check_coop_ghost_bag_draws()
    check_fuzz_smoke()
    print("PASSED: drag fuzz regression checks all green.")

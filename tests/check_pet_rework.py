"""
Regression checks for the pet rework (item 3): Bond (lifetime feed investment
scaling pet power), pet carriers (pack a pet into a tradable/vaultable item and
back out again), fusion (two maxed same-rarity pets -> one next-rarity pet,
mythic being fusion-only), old-save compatibility, the co-op server actions,
and the Inventory-mode feed drop target no longer covering the equip bar.

Run with: .venv\\Scripts\\python.exe tests\\check_pet_rework.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((100, 100))

from game import achievements, items, characters, accounts
achievements._DIR = tempfile.mkdtemp(prefix="rr_pet_ach_")  # hatching unlocks egg_parent
items.VAULT_DIR = tempfile.mkdtemp(prefix="rr_pet_vault_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_pet_char_")
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_pet_acc_")

import server
from game import constants as C, ui
from game.entities import Player, Pet
from game.items import (Item, SLOT_WEAPON, SLOT_EGG, PET_KINDS, PET_RARITY_MAX_LEVEL, PET_RARITY_ORDER,
                        PET_FEED_XP_PER_TIER, pet_ability_stats, pet_bond_level, make_egg, make_carrier,
                        _EGG_RARITY_WEIGHT, _random_egg)

SHOT_DIR = os.environ.get("RR_SHOT_DIR")


def _food(tier=5):
    return Item("Snack", SLOT_WEAPON, tier, "sword", min_dmg=1, max_dmg=2)


def _maxed(kind):
    pet = Pet(kind, (0, 0))
    cap = PET_RARITY_MAX_LEVEL[pet.rarity]
    for st in pet.abilities.values():
        st["level"], st["xp"] = cap, 0.0
    return pet


def check_bond_accrues_even_when_capped():
    p = Player("wizard", "Bondy", pid="b1")
    p.pet = Pet("hatchling", p.pos)
    p.backpack = [_food(5)]
    assert p.feed_pet(0) and p.pet.bond == 5 * PET_FEED_XP_PER_TIER
    p.pet = _maxed("hatchling")
    p.backpack = [_food(11)]
    levels_before = {k: v["level"] for k, v in p.pet.abilities.items()}
    assert p.feed_pet(0), "feeding a capped pet still works (for bond)"
    assert p.pet.bond == 11 * PET_FEED_XP_PER_TIER
    assert {k: v["level"] for k, v in p.pet.abilities.items()} == levels_before
    assert p.pet_msg and "bond" in p.pet_msg[0]
    print("check_bond_accrues_even_when_capped: PASSED")


def check_bond_scales_stats():
    m0, c0 = pet_ability_stats("heal", 10, 0)
    m25, c25 = pet_ability_stats("heal", 10, 25)
    assert m25 == round(8 * (1 + 0.15 * 9) * 2.0) and m25 > m0
    assert c25 < c0 and c25 >= c0 * 0.75 - 0.01
    assert pet_ability_stats("heal", 10, 999) == (m25, c25), "bond bonus is capped"
    assert pet_bond_level(0) == 0 and pet_bond_level(10 ** 9) == 25
    # a real Pet heals by the bonded amount
    owner = Player("wizard", "Heal", pid="b2")
    owner.hp_max, owner.hp = 1000, 1
    pet = Pet("hatchling", owner.pos)
    pet.bond = 10 ** 9
    for st in pet.abilities.values():
        st["cd"] = 0.0
    pet.update(1 / 30, owner, [], [])
    assert owner.hp - 1 == pet_ability_stats("heal", pet.abilities["heal"]["level"], 25)[0]
    # sustain cooldown floor: even a maxed, max-bond mythic keeps a real heal cadence
    assert pet_ability_stats("heal", 40, 25)[1] >= items.PET_SUSTAIN_COOLDOWN_FLOOR
    print("check_bond_scales_stats: PASSED")


def check_pack_roundtrip_unpack():
    p = Player("wizard", "Packer", pid="b3")
    p.pet = Pet("griffin_cub", p.pos)
    p.pet.abilities["attack"]["level"], p.pet.abilities["heal"]["xp"], p.pet.bond = 13, 7.5, 321.0
    p.backpack = []
    assert p.pack_pet() and p.pet is None and len(p.backpack) == 1
    carrier = p.backpack[0]
    assert carrier.slot == SLOT_EGG and carrier.shape == "carrier" and carrier.pet_state
    restored = Item.from_json(json.loads(json.dumps(carrier.to_json())))
    assert restored.pet_state == carrier.pet_state
    p.backpack = [restored]
    assert p.use_potion(0) and not p.backpack
    assert p.pet.kind == "griffin_cub" and p.pet.abilities["attack"]["level"] == 13
    assert p.pet.abilities["heal"]["xp"] == 7.5 and p.pet.bond == 321.0
    # full-state save of a player holding a carrier
    p.pack_pet()
    again = Player.from_full_state(json.loads(json.dumps(p.full_state())))
    assert again.backpack[0].pet_state["bond"] == 321.0
    # pack fails cleanly with a full backpack / no pet
    p.use_potion(0)
    p.backpack = [_food() for _ in range(p.backpack_size)]
    assert not p.pack_pet() and p.pet is not None and len(p.backpack) == p.backpack_size
    p.pet = None
    assert not p.pack_pet() and p.pet_msg
    print("check_pack_roundtrip_unpack: PASSED")


def check_hatch_with_active_pet_autopacks():
    p = Player("wizard", "Hatcher", pid="b4")
    p.pet = Pet("wisp", p.pos)
    p.pet.bond = 99.0
    # a completely full backpack still works: the carrier takes the egg's own slot
    p.backpack = [_food() for _ in range(p.backpack_size - 1)] + [make_egg("imp_pup")]
    assert p.use_potion(p.backpack_size - 1)
    assert p.pet.kind == "imp_pup"
    assert len(p.backpack) == p.backpack_size
    last = p.backpack[-1]
    assert last.shape == "carrier" and last.pet_state["kind"] == "wisp" and last.pet_state["bond"] == 99.0
    print("check_hatch_with_active_pet_autopacks: PASSED")


def check_fusion_success():
    for rarity in PET_RARITY_ORDER[:-1]:
        kinds = [k for k, d in PET_KINDS.items() if d["rarity"] == rarity]
        p = Player("wizard", "Fuser", pid="b5")
        p.pet = _maxed(kinds[0])
        p.pet.bond = 100.0
        other = _maxed(kinds[-1])
        other.bond = 50.0
        p.backpack = [_food(), make_carrier(other.net_state())]
        assert p.feed_pet(1), p.pet_msg
        next_rarity = PET_RARITY_ORDER[PET_RARITY_ORDER.index(rarity) + 1]
        assert p.pet.rarity == next_rarity and p.pet.bond == 150.0
        family = PET_KINDS[kinds[0]]["family"]
        pool_families = {d["family"] for d in PET_KINDS.values() if d["rarity"] == next_rarity}
        if family in pool_families:
            assert PET_KINDS[p.pet.kind]["family"] == family, "family is kept when possible"
        assert len(p.backpack) == 1 and p.backpack[0].name == "Snack", "carrier consumed, food untouched"
        assert p.pet_fused and "FUSION" in p.pet_msg[0]
        cap = PET_RARITY_MAX_LEVEL[rarity] // 2
        assert all(st["level"] >= cap for st in p.pet.abilities.values())
        assert all(st["level"] <= PET_RARITY_MAX_LEVEL[next_rarity] for st in p.pet.abilities.values())
    print("check_fusion_success: PASSED")


def check_fusion_rejects_consume_nothing():
    cases = [
        (_maxed("hatchling"), Pet("imp_pup", (0, 0)), "isn't yet"),      # carried not maxed
        (Pet("hatchling", (0, 0)), _maxed("imp_pup"), "isn't yet"),      # active not maxed
        (_maxed("hatchling"), _maxed("wisp"), "same rarity"),            # rarity mismatch
        (_maxed("hangover_hydra"), _maxed("brewmaster_djinn"), "Mythic"),  # mythic can't fuse
    ]
    for active, carried, reason in cases:
        p = Player("wizard", "Nope", pid="b6")
        p.pet = active
        kind_before = active.kind
        p.backpack = [make_carrier(carried.net_state())]
        assert not p.feed_pet(0)
        assert len(p.backpack) == 1 and p.pet.kind == kind_before
        assert reason in p.pet_msg[0], (reason, p.pet_msg)
    # a plain egg dropped on the pet is refused with a reason too, not consumed
    p.backpack = [make_egg("wisp")]
    assert not p.feed_pet(0) and len(p.backpack) == 1 and p.pet_msg
    print("check_fusion_rejects_consume_nothing: PASSED")


def check_mythic_never_drops_and_old_saves_load():
    assert "mythic" not in _EGG_RARITY_WEIGHT
    for _ in range(300):
        assert PET_KINDS[_random_egg().pet_kind]["rarity"] != "mythic"
    old_pet = {"kind": "wisp", "x": 1.0, "y": 2.0, "levels": {"heal": 2, "magic": 6, "attack": 1},
               "xp": {"heal": 0.0, "magic": 3.0, "attack": 0.0}}
    pet = Pet.from_net_state(old_pet)
    assert pet.bond == 0.0 and pet.abilities["magic"]["level"] == 6
    old_item = {"name": "Old Sword", "slot": "weapon", "tier": 3, "shape": "sword", "is_ut": False,
                "stat_bonus": {}, "min_dmg": 1, "max_dmg": 2, "proc": "", "effect": "", "mp_cost": 0,
                "magnitude": 0, "description": "", "pet_kind": "", "shard_theme": "", "socketed_proc": None}
    assert Item.from_json(old_item).pet_state is None
    p = Player("wizard", "Oldie", pid="b7")
    p.pet = pet
    state = p.full_state()
    state["pet"].pop("bond", None)
    assert Player.from_full_state(state).pet.bond == 0.0
    print("check_mythic_never_drops_and_old_saves_load: PASSED")


class FakeSock:
    def __init__(self):
        self.msgs = []

    def sendall(self, data):
        for line in data.decode("utf-8").splitlines():
            self.msgs.append(json.loads(line))

    def of(self, kind):
        return [m for m in self.msgs if m.get("type") == kind]


def _act(state, s, action, **kw):
    server._apply_action(state, s, dict(action=action, **kw))


def check_coop_server_actions_trade_and_vault():
    state = server.ServerState()
    sessions = []
    for i, name in enumerate(("PetA", "PetB")):
        p = Player("wizard", name=name, pid=f"q{i}")
        p.pos = server._nexus_spawn_pos(state) + pygame.Vector2(i * 30, 0)
        s = server.Session(f"q{i}", FakeSock(), p)
        state.sessions[s.pid] = s
        sessions.append(s)
    a, b = sessions
    # pack_pet through the real action handler
    a.player.pet = _maxed("hatchling")
    a.player.pet.bond = 40.0
    _act(state, a, "pack_pet")
    assert a.player.pet is None and a.player.backpack[-1].shape == "carrier"
    assert a.sock.of("pet_result")[-1]["message"].startswith("Packed")
    # the carrier survives a trade intact
    _act(state, a, "trade_request", pid=b.pid)
    _act(state, b, "trade_invite_accept")
    _act(state, a, "trade_offer", idx=0)
    _act(state, a, "trade_accept")
    _act(state, b, "trade_accept")
    for _ in range(int((server.TRADE_CONFIRM_SECONDS + 0.5) / 0.1)):
        server.step(state, 0.1)
    carrier = b.player.backpack[-1]
    assert carrier.shape == "carrier" and carrier.pet_state["bond"] == 40.0, "carrier arrived via trade"
    # ... and a vault deposit/withdraw (a real JSON round trip through save_vault/load_vault)
    b.zone = server.ZONE_VAULT_ROOM
    b.vault_items = items.load_vault(b.player.name)
    idx = len(b.player.backpack) - 1
    _act(state, b, "vault_deposit", idx=idx)
    assert not any(it.shape == "carrier" for it in b.player.backpack)
    b.vault_items = items.load_vault(b.player.name)  # reload from disk
    slot = next(i for i, it in enumerate(b.vault_items) if it is not None and it.shape == "carrier")
    _act(state, b, "vault_withdraw", idx=slot)
    carrier = b.player.backpack[-1]
    assert carrier.pet_state["kind"] == "hatchling" and carrier.pet_state["bond"] == 40.0
    # feed_pet with a carrier -> fusion, decided server-side
    b.player.pet = _maxed("imp_pup")
    _act(state, b, "feed_pet", idx=len(b.player.backpack) - 1)
    res = b.sock.of("pet_result")[-1]
    assert res["fused"] and b.player.pet.rarity == "uncommon" and b.player.pet.bond == 40.0
    # using the (now gone) ... a fresh egg via "equip" with a pet out auto-packs it
    b.player.backpack.append(make_egg("hatchling"))
    _act(state, b, "equip", idx=len(b.player.backpack) - 1)
    assert b.player.pet.kind == "hatchling" and b.player.backpack[-1].shape == "carrier"
    assert "carrier" in b.sock.of("pet_result")[-1]["message"]
    print("check_coop_server_actions_trade_and_vault: PASSED")


def check_feed_target_no_longer_covers_equip_bar():
    p = Player("wizard", "Dock", pid="b8")
    p.pet = Pet("hatchling", p.pos)
    inv_target = ui.pet_feed_target_rect(p, "inventory")
    for rect, _ in ui.equip_slot_rects():
        assert not inv_target.colliderect(rect), "inventory-mode feed target must not overlap equip slots"
    for rect in ui.backpack_slot_rects(p):
        assert not inv_target.colliderect(rect)
    assert ui.pet_feed_target_rect(p, "pet") == ui.pet_panel_rect(p)
    btn = ui.pet_pack_button_rect(p)
    assert ui.pet_panel_rect(p).contains(btn)
    assert ui.pet_panel_rect(p).bottom <= C.SCREEN_H - 8, "pet panel stays on screen"
    print("check_feed_target_no_longer_covers_equip_bar: PASSED")


def check_ui_renders_and_client_wiring():
    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    surf.fill((30, 34, 30))
    p = Player("wizard", "Shot", pid="b9")
    p.pet = _maxed("phoenix_chick")
    p.pet.bond = 5000.0
    carrier = make_carrier(_maxed("tipsy_thunderbird").net_state())
    p.backpack = [carrier, _food()]
    ui.draw_panel_tabs(surf, "pet")
    ui.draw_pet_panel(surf, p, dragging=True, mouse_pos=ui.pet_pack_button_rect(p).center)
    ui._tooltip(surf, (700, 600), carrier)
    if SHOT_DIR:
        pygame.image.save(surf, os.path.join(SHOT_DIR, "pet_panel_and_carrier.png"))
    surf2 = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    ui.draw_panel_tabs(surf2, "inventory", feed_drop_hint=True)
    ui.draw_inventory(surf2, p, (0, 0))

    # SP Game: the pack button click + feed drop via the Pet tab in inventory mode
    import main
    game = main.Game()
    game.state = main.STATE_NEXUS
    game.player = Player("wizard", "SPPet", pid="sp")
    game.player.pet = Pet("hatchling", game.player.pos)
    game.player.backpack = [_food(9)]
    game.right_panel_mode = "inventory"
    assert game._slot_at(ui.equip_slot_rects()[0][0].center) == ("equip", "weapon")
    assert game._slot_at(ui.pet_tab_rect().center) == ("pet", None)
    game.right_panel_mode = "pet"
    btn = ui.pet_pack_button_rect(game.player).center
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn))
    game.handle_events()
    assert game.player.pet is None and game.player.backpack[-1].shape == "carrier"
    assert any("Packed" in f[0] for f in game.feed)
    game.draw()
    print("check_ui_renders_and_client_wiring: PASSED")


if __name__ == "__main__":
    check_bond_accrues_even_when_capped()
    check_bond_scales_stats()
    check_pack_roundtrip_unpack()
    check_hatch_with_active_pet_autopacks()
    check_fusion_success()
    check_fusion_rejects_consume_nothing()
    check_mythic_never_drops_and_old_saves_load()
    check_coop_server_actions_trade_and_vault()
    check_feed_target_no_longer_covers_equip_bar()
    check_ui_renders_and_client_wiring()
    print("PASSED: pet rework checks all green.")

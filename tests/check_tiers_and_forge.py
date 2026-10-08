"""
Endgame tiers, the Anvil (forging) and Divine items.

- T12-T14 exist for every weapon line, armor type, ring and ability line; normal
  loot never rolls above T11; T12-T13 only come from the new loot sources
  (Heroic dungeons / big islands / the Mad God's Room); T14 never drops at all
- the forge: 3 same-slot same-tier items -> the next tier (ingots from T12 up),
  UT reforging, bad inputs rejected, equipped gear never consumed; forging
  counts for Act III; the Anvil NPC offers it in dialogue
- Divine items only drop from the Mad God's Room's evolved forms; their effects
  work (Starfall volley, Second Wind); items round-trip through saves
- new tier bands / bag colours / icons / event sounds all exist

Run with: .venv\\Scripts\\python.exe tests\\check_tiers_and_forge.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((200, 200))

from game import items as I, forge, story, dialogue, npcs, sprites, audio
from game.constants import TIER_COLORS, BAG_COLORS
from game.entities import Player

CLASSES = list(I.WEAPONS)


def check_endgame_tiers_exist():
    for cls in CLASSES:
        tiers = [r[2] for r in I.WEAPONS[cls]]
        assert tiers == list(range(1, 15)), (cls, tiers)
        dmg = [r[3][1] for r in I.WEAPONS[cls]]
        assert dmg[11] > dmg[10] and dmg[12] > dmg[11] and dmg[13] > dmg[12], (cls, dmg[10:])
        ab = [r[2] for r in I.ABILITIES[cls]]
        assert ab == [1, 5, 9, 12, 14], (cls, ab)
    for rows in (I.HEAVY_ARMORS, I.LIGHT_ARMORS, I.ROBES, I.RINGS):
        assert [r[1] for r in rows] == list(range(1, 15))
    assert I.tier_band(11) == "t_top" and I.tier_band(12) == I.tier_band(13) == "t_mythic"
    assert I.tier_band(14) == "t_forged"
    for band in ("t_mythic", "t_forged", "divine"):
        assert band in TIER_COLORS
    assert "cyan" in BAG_COLORS and "gold" in BAG_COLORS
    print("check_endgame_tiers_exist: PASSED")


def check_normal_loot_stops_at_t11():
    random.seed(7)
    top = 0
    for _ in range(3000):
        for rank in ("trash", "elite", "boss"):
            for _bag, it in I.roll_loot("warrior", rank, 1.0):
                if not it.is_ut and it.slot in ("weapon", "armor", "ring", "ability"):
                    top = max(top, it.tier)
                assert not it.divine and it.slot != I.SLOT_MATERIAL
    assert top == 11, top
    print("check_normal_loot_stops_at_t11: PASSED")


def check_new_sources_drop_mythic_ingots_and_divine():
    random.seed(11)

    def roll(src, rank, n):
        out = []
        for _ in range(n):
            out.extend(it for _b, it in I.roll_loot("wizard", rank, 1.0, source=src))
        return out

    heroic = roll("heroic", "boss", 200)
    assert any(it.tier in (12, 13) and not it.is_ut for it in heroic)
    assert any(it.slot == I.SLOT_MATERIAL for it in heroic)
    assert not any(it.divine for it in heroic) and max(it.tier for it in heroic if not it.divine) <= 13
    assert not any(it.divine for it in roll("island", "boss", 200) + roll("mg_room_1", "boss", 200))
    evo1 = roll("mg_room_2", "boss", 300)
    assert 0 < sum(it.divine for it in evo1) < 300 * 0.35, sum(it.divine for it in evo1)
    evo2 = roll("mg_room_3", "boss", 20)
    assert sum(it.divine for it in evo2) >= 20  # always at least one
    assert not any(it.tier == 14 for it in heroic + evo1 + evo2 if not it.divine), "T14 is forge-only"
    print("check_new_sources_drop_mythic_ingots_and_divine: PASSED")


def _items_of(slot, tier, n, cls="warrior"):
    out = []
    for _ in range(n):
        if slot == "weapon":
            r = next(r for r in I.WEAPONS[cls] if r[2] == tier)
            out.append(I.Item(r[0], I.SLOT_WEAPON, tier, r[1], min_dmg=r[3][0], max_dmg=r[3][1]))
        elif slot == "ring":
            r = next(r for r in I.RINGS if r[1] == tier)
            out.append(I.Item(r[0], I.SLOT_RING, tier, "ring", stat_bonus=dict(r[2])))
        elif slot == "ability":
            r = next(r for r in I.ABILITIES[cls] if r[2] == tier)
            out.append(I.Item(r[0], I.SLOT_ABILITY, tier, "ability", effect=r[1], mp_cost=r[3], magnitude=r[4]))
    return out


def check_forge_recipes():
    p = Player("warrior", "Smith", pid="s")
    # 2 of a kind: nothing to forge; the equipped weapon never counts
    p.backpack = _items_of("weapon", 5, 2)
    p.weapon = _items_of("weapon", 5, 1)[0]
    assert forge.forge_options(p) == []
    p.backpack.append(_items_of("weapon", 5, 1)[0])
    opts = forge.forge_options(p)
    assert len(opts) == 1 and opts[0]["result"].tier == 6 and opts[0]["result"].slot == "weapon"
    ok, msg, res = forge.apply_forge(p, opts[0])
    assert ok and res.tier == 6 and len(p.backpack) == 1 and p.weapon.tier == 5
    # abilities follow their own ladder (5 -> 9)
    p.backpack = _items_of("ability", 5, 3)
    assert forge.forge_options(p)[0]["result"].tier == 9
    # T11 -> T12 needs an ingot; T13 -> T14 needs two
    p.backpack = _items_of("ring", 11, 3)
    assert forge.forge_options(p) == []
    p.backpack.append(I.make_forge_ingot())
    r = forge.forge_options(p)[0]
    assert r["result"].tier == 12 and len(r["ingots"]) == 1
    p.backpack = _items_of("weapon", 13, 3) + [I.make_forge_ingot()]
    assert forge.forge_options(p) == []
    p.backpack.append(I.make_forge_ingot())
    r = forge.forge_options(p)[0]
    assert r["result"].tier == 14 and r["result"].name.startswith("Anvil-Wrought")
    ok, _m, res = forge.apply_forge(p, r)
    assert ok and p.backpack == [res]
    # T14 is the top: three T14s don't temper further; different tiers never combine
    p.backpack = _items_of("weapon", 14, 3) + [I.make_forge_ingot()] * 3
    assert all(o["kind"] != "temper" for o in forge.forge_options(p))
    p.backpack = _items_of("weapon", 7, 1) + _items_of("ring", 7, 1) + _items_of("ability", 9, 1)
    assert forge.forge_options(p) == []
    # mixed slots of the SAME tier do combine; the result keeps the first item's slot/line
    p.backpack = _items_of("ring", 7, 1) + _items_of("weapon", 7, 2)
    r = forge.forge_options(p)[0]
    assert r["result"].slot == "ring" and r["result"].tier == 8 and "items" in r["label"], r["label"]
    # a stale recipe (items no longer in the bag) is refused, nothing lost
    p.backpack = _items_of("weapon", 3, 3)
    stale = forge.forge_options(p)[0]
    p.backpack.pop()
    ok, _m, _r = forge.apply_forge(p, stale)
    assert not ok and len(p.backpack) == 2
    # UT reforge keeps the proc (socketed, so the rename doesn't lose it) and hits harder
    ut = I._random_ut("warrior")
    p.backpack = [ut, I.make_forge_ingot(), I.make_forge_ingot()]
    r = next(o for o in forge.forge_options(p) if o["kind"] == "reforge")
    ok, _m, res = forge.apply_forge(p, r)
    assert ok and res.is_ut and res.name == "Reforged " + ut.name and res.max_dmg > ut.max_dmg
    assert res.socketed_proc == (ut.socketed_proc or I.identify_proc_kind(ut))
    assert forge.reforge_result(res) is None, "a Reforged UT can't be reforged again"
    print("check_forge_recipes: PASSED")


def check_anvil_dialogue_forges_and_counts_for_act_iii():
    assert "hammerstein" in npcs.NPCS and npcs.NPCS["hammerstein"]["zone"] == "nexus"
    p = Player("warrior", "Apprentice", pid="a")
    from game import sidequests
    p.sidequests = sidequests.SideQuestProgress()
    p.story = story.StoryProgress(story.ACT_GEAR)
    p.backpack = _items_of("weapon", 8, 3)
    conv = dialogue.start_conversation(p, npc=npcs.NPC("hammerstein", pygame.Vector2(0, 0)))
    view = conv.view()
    # the chat leads with "Open the Forge"; recipes live in the Forge window (game/forge_menu.py)
    assert view["options"][0] == dialogue.OPEN_FORGE, view["options"]
    assert not any(o.startswith("Temper") for o in view["options"])
    assert conv.choose(0) is None and conv.open_forge and conv.done
    from game import forge_menu
    r = forge_menu.catalog(p)["temper"][0]
    assert r["ok"] and r["label"].startswith("Temper 3 T8 weapons"), r["label"]
    res = forge_menu.apply(p, r)
    assert res["ok"] and res["result"].tier == 9 and res["sfx"] == "forge_success"
    assert p.story.done.get("gear_forge"), p.story.done
    # nothing left to forge: the Forge's Temper tab is empty, the chat still offers the window
    assert not any(r["ok"] for r in forge_menu.catalog(p)["temper"])
    conv2 = dialogue.start_conversation(p, npc=npcs.NPC("hammerstein", pygame.Vector2(0, 0)))
    assert conv2.view()["options"][0] == dialogue.OPEN_FORGE
    print("check_anvil_dialogue_forges_and_counts_for_act_iii: PASSED")


def check_divine_items_and_effects():
    for cls in CLASSES:
        for piece in ("weapon", "armor", "ring", "ability"):
            d = I.make_divine(cls, piece)
            assert d.divine and d.band == "divine" and d.display_name.startswith("[Divine]")
            back = I.Item.from_json(d.to_json())
            assert back.divine and back.divine_proc == d.divine_proc and back.name == d.name
        w = I.make_divine(cls, "weapon")
        t14 = I.WEAPONS[cls][13]
        assert w.max_dmg > t14[3][1] and w.divine_proc == "starfall"
    # Second Wind: a killing blow leaves you at 1 HP, once per cooldown
    p = Player("warrior", "Lucky", pid="l")
    p.armor = I.make_divine("warrior", "armor")
    p.hp = 10
    p.take_damage(10 ** 6, pierce_armor=True)
    assert p.alive and p.hp == 1 and p.second_wind_fired
    p._dash_iframes = 0
    p.take_damage(10 ** 6, pierce_armor=True)
    assert not p.alive, "only once per cooldown"
    # Starfall: every Nth shot adds 3 piercing star bolts
    from game.realm_sim import RealmSim
    sim = RealmSim(bonus=True, theme="cave", difficulty_name="Easy", story_act=0)
    s = Player("wizard", "Star", pid="st")
    s.weapon = I.make_divine("wizard", "weapon")
    counts = [len(sim.player_fire(s, pygame.Vector2(1, 0))) for _ in range(I.DIVINE_STARFALL_EVERY * 2)]
    base = min(counts)
    assert counts.count(base + 3) == 2, counts
    assert any(ev[0] == "sfx" and ev[1] == "starfall" for ev in sim.sound_events)
    # old saves (no divine keys) still load
    old = I.make_forge_ingot().to_json()
    old.pop("divine")
    old.pop("divine_proc")
    assert I.Item.from_json(old).divine is False
    print("check_divine_items_and_effects: PASSED")


def check_icons_and_sounds():
    for shape in ("ingot", "key"):
        a = sprites.item_icon(TIER_COLORS["t_mythic"], shape)
        b = sprites.item_icon(TIER_COLORS["t_mythic"], "sword")
        assert pygame.image.tobytes(a, "RGBA") != pygame.image.tobytes(b, "RGBA"), shape
    for key in ("forge_success", "forge_hammer", "gate_denied", "heroic_portal", "harbour_bell", "mg_transform",
                "divine_drop", "mythic_drop", "starfall", "second_wind", "trial_done", "forge_fail",
                "mg_enrage"):
        assert key in audio.EVENT_SOUND, key
        samples = audio._event_sound(key)
        assert len(samples) > 1000 and max(abs(v) for v in samples) > 500, key
    # every sound is its own thing
    sigs = {tuple(audio._event_sound(k)[:400:7]) for k in audio.EVENT_SOUND}
    assert len(sigs) == len(audio.EVENT_SOUND)
    audio.play_event("forge_success")  # never raises (dummy audio)
    audio.play_event("no_such_sound")
    out = os.environ.get("RR_SHOT_DIR")
    if out:
        surf = pygame.Surface((8 * 32, 40))
        for i, (band, shape) in enumerate([("t_mythic", "sword"), ("t_forged", "staff"), ("divine", "armor"),
                                           ("divine", "ring"), ("t_mythic", "ingot"), ("divine", "key"),
                                           ("t_forged", "ability"), ("t_top", "bow")]):
            surf.blit(sprites.item_icon(TIER_COLORS[band], shape), (i * 32 + 2, 6))
        pygame.image.save(surf, os.path.join(out, "endgame_item_icons.png"))
    print("check_icons_and_sounds: PASSED")


if __name__ == "__main__":
    check_endgame_tiers_exist()
    check_normal_loot_stops_at_t11()
    check_new_sources_drop_mythic_ingots_and_divine()
    check_forge_recipes()
    check_anvil_dialogue_forges_and_counts_for_act_iii()
    check_divine_items_and_effects()
    check_icons_and_sounds()
    print("PASSED: endgame tiers + forge + divine checks all green.")

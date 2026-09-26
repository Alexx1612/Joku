"""
The Dictionary's data (Batch 15, item 1.5) plus the "where is it" area info the
Quest Log / Quest Map / Dictionary share (items 1.4 / 1.6).

Every entry is built from the game's own tables (ENEMY_KINDS, BIOME_LAIR_KIND_SETS,
ISLAND_THEMES, DUNGEON_THEMES, LANDMARK_DEFS, PET_KINDS, npcs.NPCS, ...) so the
numbers shown can never drift from what the game actually uses. No pygame drawing
here - see game/journal.py for the windows.

Entry dict: id, cat, title, sprite (dict src/key/tint or None), stats [(label, value)],
text (str, may contain blank-line paragraphs), where {"biomes": [...], "areas": [...]}
and a lower-case `search` blob.
"""
import math

from game import constants as C

CATEGORIES = [
    ("mobs", "Mobs"),
    ("bosses", "Bosses"),
    ("friendly", "Friendly creatures"),
    ("npcs", "NPCs"),
    ("portals", "Portals & Dungeons"),
    ("areas", "Areas"),
    ("pets", "Pets & mechanics"),
    ("items", "Items & UT"),
    ("story", "Story"),
]

PATTERN_TEXT = {
    "aimed": "fires single shots straight at you",
    "erratic": "flits around and fires wild, unreliable shots",
    "spread": "fires a 3-shot fan - dodge sideways, not backwards",
    "burst": "fires an 8-way ring of bullets",
    "volley": "fires quick double-tap volleys",
    "spiral": "sprays a slowly rotating spiral",
    "charge": "charges at you instead of shooting",
    "boss": "spins bullet rings with a periodic red nova",
    "boss_root": "fires thorn rings and root pulses that pin you in place",
    "boss_burrow": "burrows underground and erupts in a bullet ring",
    "mad_god": "rings, aimed armor-piercing volleys and red novas (a 2nd ring in phase 2)",
}

BIOME_LABELS = {
    "forest": "Forest", "desert": "Desert", "tundra": "Tundra", "swamp": "Swamp",
    "highlands": "Highlands", "ashlands": "Ashlands", "jungle": "Jungle",
    "wasteland": "Wasteland", "ice": "Ice Fields", "cave": "Caves",
}

_ENTRIES = None
_BY_ID = None


def cap(text):
    """First letter upper-cased, the rest untouched ('the Sunken Idol' -> 'The Sunken Idol')."""
    return text[:1].upper() + text[1:]


def _pretty(kind):
    return kind.replace("_phase2", " (phase 2)").replace("_", " ").title()


def mob_biomes():
    """{kind: [biome names]} from the lair rosters."""
    from game import realm_sim, world
    out = {}
    for ground, sets in realm_sim.BIOME_LAIR_KIND_SETS.items():
        biome = world.GROUND_TO_BIOME_NAME.get(ground)
        if biome is None:
            continue
        for kinds, _w in sets:
            for k in kinds:
                lst = out.setdefault(k, [])
                if biome not in lst:
                    lst.append(biome)
    return out


def _mob_extra_areas():
    """{kind: [area keys]} - island waves, dungeon rosters and dungeon bosses."""
    from game import realm_sim
    out = {}
    for theme in realm_sim.ISLAND_THEMES.values():
        for k in theme["guardians"] + [theme["anchor"]]:
            out.setdefault(k, []).append("islands")
    for k in realm_sim.ISLAND_MINI_BOSS.values():
        out.setdefault(k, []).append("islands")
    for key, th in realm_sim.DUNGEON_THEMES.items():
        for k in list(th["kinds"]) + list(th["bosses"]):
            lst = out.setdefault(k, [])
            if f"dungeon:{key}" not in lst:
                lst.append(f"dungeon:{key}")
    return out


def _enemy_entry(kind, d, biomes, extra):
    from game import entities
    rank = d.get("rank", "trash")
    neutral = d.get("neutral") and d.get("unshootable")
    cat = "friendly" if neutral else ("bosses" if rank == "boss" else "mobs")
    lo, hi = d.get("dmg", (0, 0))
    stats = [("Rank", rank.title()), ("HP", d.get("hp")), ("Speed", d.get("speed")),
             ("Defense", d.get("deF", 0)), ("XP", entities.RANK_XP.get(rank, 0))]
    if not neutral:
        stats.insert(2, ("Damage", f"{lo}-{hi}"))
        stats.append(("Attack", d.get("pattern", "?")))
    where_names = [BIOME_LABELS.get(b, b) for b in biomes] + [area_label(a) for a in extra]
    if neutral:
        text = ("Harmless wildlife - it can't be shot, and it runs from gunfire. Walk up and press F to "
                "talk to it (some side quests want you to stand near a group of them).")
    else:
        text = f"It {PATTERN_TEXT.get(d.get('pattern'), 'attacks you')}."
        if kind.endswith("_phase2"):
            text += " A tougher second phase: more HP, harder hits and faster fire."
        if rank == "boss":
            text += " Bosses don't leash - they chase you anywhere."
    if where_names:
        text += "\n\nFound in: " + ", ".join(where_names) + "."
    sprite_kind = kind
    return dict(id=f"enemy:{kind}", cat=cat, title=_pretty(kind),
                sprite={"src": "enemy", "key": sprite_kind}, stats=stats, text=text,
                where={"biomes": list(biomes), "areas": list(extra)})


def area_label(key):
    from game import realm_sim, story
    if key == "islands":
        return "The Reforging islands"
    if key.startswith("dungeon:"):
        th = realm_sim.DUNGEON_THEMES.get(key.split(":", 1)[1])
        return th["label"] if th else key
    if key.startswith("landmark:"):
        return cap(story.landmark_name(key.split(":", 1)[1]))
    if key.startswith("island:"):
        return realm_sim.ISLAND_NAMES[int(key.split(":", 1)[1])]
    if key.startswith("place:"):
        from game import areas as areas_mod
        d = areas_mod.AREA_DEFS.get(key.split(":", 1)[1])
        return d["name"] if d else key
    return BIOME_LABELS.get(key, key.replace("_", " ").title())


def _npc_entries():
    from game import npcs
    out = []
    kind_label = {"person": "Person", "creature": "Friendly creature group"}
    for npc_id, d in npcs.NPCS.items():
        src, key = d["sprite"]
        area = d["area"]
        if area.startswith("landmark:") or area.startswith("vignette:"):
            where = {"biomes": [area.split(":", 1)[1]], "areas": [f"npc:{npc_id}"]}
            place = f"Near {area_label(area.split(':', 1)[1])}"
            if area.startswith("landmark:"):
                place = f"Beside {area_label(area)}"
        elif area == "spawn":
            where, place = {"biomes": [], "areas": [f"npc:{npc_id}"]}, "On the arrival beach"
        else:
            where, place = {"biomes": [], "areas": [f"npc:{npc_id}"]}, "In the Nexus tavern"
        quests = list((d.get("quests") or {}).keys())
        text = f"\"{d['greeting']}\"\n\nWhere: {place}. Walk up and press F to talk."
        if quests:
            from game import sidequests
            text += "\n\nGives quests: " + ", ".join(sidequests.QUESTS[q]["title"] for q in quests
                                                     if q in sidequests.QUESTS) + "."
        out.append(dict(id=f"npc:{npc_id}", cat="npcs" if d["kind"] == "person" else "friendly",
                        title=d["name"], sprite={"src": src, "key": key, "tint": d.get("tint")},
                        stats=[("Type", kind_label.get(d["kind"], d["kind"].title())), ("Where", place)],
                        text=text, where=where))
    out.append(dict(id="npc:father_given", cat="npcs", title="Father Given",
                    sprite={"src": "player", "key": "priest"},
                    stats=[("Type", "Person"), ("Where", "The Nexus")],
                    text="The Nexus's wandering guide and your story's narrator. Walk up and press F: he gives "
                         "the current act's hint and, in the Finale, opens the Forge.",
                    where={"biomes": [], "areas": []}))
    return out


def _npc_defs():
    from game import npcs
    return npcs.NPCS


def _area_entries():
    from game import realm_sim, world, story
    out = []
    for b in story.OUTER_BIOMES + story.INNER_BIOMES:
        tier = "Outer (easier)" if b in story.OUTER_BIOMES else "Inner (harder)"
        lm = world.LANDMARK_DEFS.get(b, {})
        mobs = [k for k, bs in mob_biomes().items() if b in bs]
        out.append(dict(id=f"area:{b}", cat="areas", title=BIOME_LABELS.get(b, b.title()), sprite=None,
                        stats=[("Tier", tier), ("Landmark", lm.get("name", "-")),
                               ("Guardian", _pretty(story.GUARDIAN_KIND.get(b, "?")))],
                        text=f"{tier} biome. Mobs here: " + ", ".join(_pretty(k) for k in mobs) + ".",
                        where={"biomes": [b], "areas": []}))
    for b, lm in world.LANDMARK_DEFS.items():
        out.append(dict(id=f"area:landmark:{b}", cat="areas", title=cap(lm["name"]), sprite=None,
                        stats=[("Biome", BIOME_LABELS.get(b, b)),
                               ("Guardian", _pretty(story.GUARDIAN_KIND.get(b, "?")))],
                        text=lm["lore"] + "\n\nWalking up to it can wake its Landmark Guardian if your story "
                             "act needs it. Discovering it drops a bonus bag.",
                        where={"biomes": [b], "areas": [f"landmark:{b}"]}))
    for i, name in enumerate(realm_sim.ISLAND_NAMES):
        boss = realm_sim.ISLAND_MINI_BOSS.get(i)
        out.append(dict(id=f"area:island:{i}", cat="areas", title=name, sprite=None,
                        stats=[("Theme", "Shard" if i % 2 == 0 else "Choir"),
                               ("Mini-boss", _pretty(boss) if boss else "-")],
                        text="One of the ten Reforging islands. Reach it through the island portals in the "
                             "beach plaza. Every few minutes it flares up with a guardian wave led by its "
                             "mini-boss; calming it counts for Act II. Its chest refills when calmed.",
                        where={"biomes": [], "areas": [f"island:{i}"]}))
    for key, label, text in (
            ("islands", "The Reforging islands", "Ten drink-pun islands in the ocean around the continent."),
            ("landmarks", "Landmarks", "One ancient landmark per biome - each has a Landmark Guardian."),
            ("island_chests", "Island chests", "Each island has a chest you can open once; it refills when "
                                                "the island is calmed. Quest items for NPCs can be inside."),
            ("realm", "The Godlands (the Realm)", "The whole continent. Difficulty rises toward the centre."),
            ("dungeons", "Dungeons", "Opened with Dungeon Shards (dropped by elites and inner Guardians).")):
        out.append(dict(id=f"area:{key}", cat="areas", title=label, sprite=None, stats=[], text=text,
                        where={"biomes": [], "areas": [key]}))
    from game import areas as areas_mod
    for key in areas_mod.AREA_ORDER:
        d = areas_mod.AREA_DEFS[key]
        biome = d["biome"]
        people = [n["name"] for nid, n in _npc_defs().items() if n.get("area") == f"area:{key}"]
        out.append(dict(id=f"area:place:{key}", cat="areas", title=d["name"], sprite=None,
                        stats=[("Biome", BIOME_LABELS.get(biome, biome) if biome else "Any outer biome"),
                               ("Size", f"{d['size'][0]}x{d['size'][1]} tiles"),
                               ("Who's here", ", ".join(people) or "-")],
                        text=d["lore"] + "\n\nA safe named place - no monster lairs inside.",
                        where={"biomes": [], "areas": [f"place:{key}"]}))
    for zone, label, text in (
            ("nexus", "The Nexus", "The safe hub: Father Given, the fountain wish, the Echo Keeper, the "
                                   "tavern, and portals to the Realm, Bazaar and Vault."),
            ("bazaar", "The Bazaar", "A market room with permanent chests and space to drop items for others."),
            ("vault", "Your Vault", "Private storage chests that survive permadeath.")):
        out.append(dict(id=f"area:{zone}", cat="areas", title=label, sprite=None, stats=[], text=text,
                        where={"biomes": [], "areas": []}))
    return out


def _portal_entries():
    from game import realm_sim
    out = []
    for key, th in realm_sim.DUNGEON_THEMES.items():
        opened = ("Only opened by Father Given once Act III is done." if key == "forge" else
                  "Opened by a Dungeon Shard dropped by: " +
                  (", ".join(sorted({_pretty(k) for k, t in realm_sim.THEME_FOR_KIND.items() if t == key}))
                   or "any elite") + ".")
        out.append(dict(id=f"area:dungeon:{key}", cat="portals", title=th["label"],
                        sprite={"src": "portal", "key": "dungeon_shard"},
                        stats=[("Bosses", ", ".join(_pretty(b) for b in th["bosses"][:3])),
                               ("Mobs", ", ".join(_pretty(k) for k in th["kinds"][:4]))],
                        text=f"{opened}\n\nDungeons come in Easy / Medium / Hard; harder ones hit harder and "
                             "drop more loot. Beat the boss to clear it (counts for Act III).",
                        where={"biomes": [], "areas": ["dungeons"]}))
    for kind, label, text in (
            ("entrance", "Realm portal", "The big swirly portal in the Nexus - step through to reach the Realm."),
            ("island_link", "Island portals", "The ring of amber portals in the beach plaza - each teleports "
                                              "you to one island; every island has one back."),
            ("realm_exit", "Exit portal", "Appears after a dungeon boss dies - takes you back to the Realm."),
            ("phase2", "Phase-2 door", "Some dungeons open a red door to a harder second boss phase.")):
        out.append(dict(id=f"portal:{kind}", cat="portals", title=label, sprite={"src": "portal", "key": kind},
                        stats=[], text=text, where={"biomes": [], "areas": []}))
    return out


def _pet_entries():
    from game import items
    out = []
    for kind, d in items.PET_KINDS.items():
        fusion_only = d["rarity"] == "mythic"
        out.append(dict(id=f"pet:{kind}", cat="pets", title=d["name"],
                        sprite={"src": "enemy", "key": d["base"], "tint": d["tint"]},
                        stats=[("Rarity", d["rarity"].title()), ("Specialty", d["family"].title()),
                               ("Max level", items.PET_RARITY_MAX_LEVEL[d["rarity"]])],
                        text=d["description"] + ("\n\nFusion only - it never hatches from an egg." if fusion_only
                                                 else "\n\nHatches from its egg (a loot drop)."),
                        where={"biomes": [], "areas": []}))
    order = items.PET_RARITY_ORDER
    help_pages = [
        ("help:pets", "How pets work",
         "HATCHING: use a pet egg from your backpack (1-8 or double-click) and it hatches into a pet that "
         "follows you everywhere.\n\n"
         "ABILITIES: every pet has three - Heal, Magic (mana) and Attack - each on its own cooldown. The "
         "pet's specialty starts higher. Tab switches the right dock to the pet panel.\n\n"
         "FEEDING: drag any item onto the pet (or the Pet tab) to feed it. Food xp is split over the three "
         f"abilities; a level needs {items.PET_LEVEL_XP_STEP} xp. Rarity caps levels: " +
         ", ".join(f"{r} {items.PET_RARITY_MAX_LEVEL[r]}" for r in order) + "."),
        ("help:bond", "Pet bond",
         "Every feed also adds its full xp to the pet's lifetime BOND - even when it's already maxed. Bond "
         f"level (max {items.PET_BOND_MAX_LEVEL}) makes all three abilities stronger (up to x2) and faster "
         "(up to -25% cooldown). The more you invest, the more it helps."),
        ("help:carriers", "Pet carriers (Pack)",
         "The Pack button in the pet panel puts your pet into a Carrier item in your backpack - it keeps its "
         "levels and bond. Store it in the Vault, trade it, or use it to let that pet back out. Hatching a new "
         "egg while a pet is out packs the old one automatically."),
        ("help:fusion", "Pet fusion",
         "Drop a Carrier onto your active pet to FUSE them - both must be the SAME rarity and have EVERY "
         "ability at max level. The result is a pet of the next rarity (" + " -> ".join(order) + "), keeping "
         "your pet's specialty if possible, with both pets' bond added together. Mythic pets are fusion-only "
         "and can't fuse further."),
    ]
    for eid, title, text in help_pages:
        out.append(dict(id=eid, cat="pets", title=title, sprite=None, stats=[], text=text,
                        where={"biomes": [], "areas": []}))
    return out


def _item_entries():
    from game import items, live_events
    out = []
    for cls, uts in items.UT_WEAPONS.items():
        for i, ut in enumerate(uts):
            name, shape, dmg = ut[0], ut[1], ut[2]
            effect = ut[3] if len(ut) > 3 else ""
            lore = ut[4] if len(ut) > 4 else ""
            proc = items._UT_PROC_KIND_BY_INDEX.get(i)
            out.append(dict(id=f"item:ut:{cls}:{i}", cat="items", title=name,
                            sprite={"src": "item", "key": shape, "tint": (255, 120, 220)},
                            stats=[("Class", cls.title()), ("Damage", f"{dmg[0]}-{dmg[1]}"),
                                   ("Socket proc", proc or "-")],
                            text=f"{effect}. {lore}".strip(),
                            where={"biomes": [], "areas": []}))
    helps = [
        ("help:ut_sockets", "UT sockets",
         "Untiered (UT) weapons with a special proc (bleed, boomerang, burn, vulnerable) can be SOCKETED: drag "
         "the UT onto another weapon in your backpack, then press Enter to confirm. The UT is consumed and its "
         "proc is copied onto the target weapon (replacing any old socket)."),
        ("help:loot", "Loot, tiers and bags",
         "Kills drop bags; tougher mobs and harder dungeons roll higher tiers. Right-click opens the nearest "
         "bag; drag items between bag, backpack and equipment. In co-op everyone who damaged a mob gets their "
         "OWN bag that only they can see and open."),
        ("help:echoes", "Echoes and the Echo Keeper",
         "Echoes are an account-wide currency (earned as you gain XP, plus a bonus on death). Spend them at the "
         "Echo Keeper in the Nexus on permanent unlocks like extra backpack slots."),
        ("help:events", "Live events",
         "Every " + str(live_events.EVENT_WINDOW // 60) + " minutes the Realm rotates to a new live event "
         "(or none): " + ", ".join(e["label"] for e in live_events.EVENTS.values()) + "."),
        ("help:trading", "Trading",
         "Right-click a player (co-op) and choose Trade - they must accept. Offered items stay in your backpack "
         "until both accept and a short countdown finishes; any change resets it."),
        ("help:potions", "Potions",
         "Stat potions permanently raise a stat (up to a cap); temporary potions give a short buff."),
    ]
    for eid, title, text in helps:
        out.append(dict(id=eid, cat="items", title=title, sprite=None, stats=[], text=text,
                        where={"biomes": [], "areas": []}))
    return out


def _story_entries():
    from game import story
    out = []
    for i, act in enumerate(story.ACTS):
        text = act["hint"] + "\n\nObjectives:\n" + "\n".join("- " + o["text"] for o in act["objectives"])
        out.append(dict(id=f"story:act{i}", cat="story", title=act["title"], sprite=None, stats=[],
                        text=text, where={"biomes": [], "areas": []}))
    for eid, title, text in (
            ("help:checkpoints", "Act checkpoints",
             "Finishing an act saves it on your ACCOUNT - even permadeath can't take it back. A new character "
             "resumes at your current act (that act's objective progress starts over). Enemies get tougher "
             f"with every finished act (+{int(story.ACT_SCALE_STEP * 100)}% HP per act)."),
            ("help:sidequests", "Side quests",
             "Side quests come from NPCs (talk to them with F) and from a random board of 3 that refills as you "
             "finish them. Open the Quest Log from the O menu to track them, click a target to look it up here, "
             "or press Map to see where to go. Rewards: XP, Echoes and loot."),
            ("help:coop", "Co-op fairness",
             "Everyone who damages a mob gets the kill's story and side-quest credit and XP, and their own "
             "personal loot bag - nobody can steal your quest kills or your drops.")):
        out.append(dict(id=eid, cat="story", title=title, sprite=None, stats=[], text=text,
                        where={"biomes": [], "areas": []}))
    return out


def entries():
    """All dictionary entries (built once)."""
    global _ENTRIES, _BY_ID
    if _ENTRIES is None:
        from game import entities
        biomes = mob_biomes()
        extra = _mob_extra_areas()
        out = []
        for kind, d in entities.ENEMY_KINDS.items():
            out.append(_enemy_entry(kind, d, biomes.get(kind, []), extra.get(kind, [])))
        out += _npc_entries() + _area_entries() + _portal_entries() + _pet_entries()
        out += _item_entries() + _story_entries()
        for e in out:
            e["search"] = " ".join([e["title"], e["id"], e["text"]] +
                                   [f"{k} {v}" for k, v in e["stats"]]).lower()
        order = {c: i for i, (c, _l) in enumerate(CATEGORIES)}
        out.sort(key=lambda e: (order.get(e["cat"], 99), not e["id"].startswith("help:"), e["title"]))
        _ENTRIES = out
        _BY_ID = {e["id"]: e for e in out}
    return _ENTRIES


def entry(entry_id):
    entries()
    return _BY_ID.get(entry_id)


def search(query="", cat=None):
    """Entries matching every word of `query` (case-insensitive); a non-empty
    query searches ALL categories, an empty one lists `cat`."""
    words = query.lower().split()
    if words:
        return [e for e in entries() if all(w in e["search"] for w in words)]
    return [e for e in entries() if cat is None or e["cat"] == cat]


def entry_for_target(target):
    """A quest target {kind, key, label} -> dictionary entry id (or None)."""
    if not target:
        return None
    kind, key = target.get("kind"), target.get("key")
    if kind == "npc":
        return f"npc:{key}"
    if kind == "mob":
        return f"enemy:{key}"
    if kind == "boss":
        return {"guardians": "area:landmarks", "island_minibosses": "area:islands",
                "world_boss": "enemy:boss", "mad_god": "enemy:mad_god"}.get(key, f"enemy:{key}")
    if kind == "area":
        if key == "pets":
            return "help:pets"
        return f"area:{key}"
    return None


def where_for_target(target):
    """Quest target -> the same {"biomes", "areas"} 'where' shape entries use."""
    eid = entry_for_target(target)
    e = entry(eid) if eid else None
    if target and target.get("kind") == "boss" and target.get("key") == "guardians":
        return {"biomes": [], "areas": ["landmarks"]}
    if target and target.get("kind") == "boss" and target.get("key") in ("island_minibosses",):
        return {"biomes": [], "areas": ["islands"]}
    if e is None:
        return {"biomes": [], "areas": []}
    return e["where"]


# ------------------------------------------------------------ realm areas --
_AREA_CACHE = {}
LABEL_CELL = 12  # tiles per cell when finding biome regions for map labels


def _biome_regions(grid):
    """[(biome, (tile_x, tile_y), cells)] - one label point per sizeable connected
    region of each biome, found on a coarse cell grid (cheap, ~5-7k cells)."""
    from game import world
    h, w = len(grid), len(grid[0])
    cw, ch = w // LABEL_CELL, h // LABEL_CELL
    names = world.TILE_TO_BIOME_NAME if hasattr(world, "TILE_TO_BIOME_NAME") else world.GROUND_TO_BIOME_NAME
    cells = [[None] * cw for _ in range(ch)]
    for cy in range(ch):
        row = grid[cy * LABEL_CELL + LABEL_CELL // 2]
        for cx in range(cw):
            cells[cy][cx] = names.get(row[cx * LABEL_CELL + LABEL_CELL // 2])
    seen = [[False] * cw for _ in range(ch)]
    out = []
    for cy in range(ch):
        for cx in range(cw):
            b = cells[cy][cx]
            if b is None or seen[cy][cx]:
                continue
            stack, comp = [(cx, cy)], []
            seen[cy][cx] = True
            while stack:
                x, y = stack.pop()
                comp.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < cw and 0 <= ny < ch and not seen[ny][nx] and cells[ny][nx] == b:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if len(comp) < 12:
                continue
            mx = sum(x for x, _ in comp) / len(comp)
            my = sum(y for _, y in comp) / len(comp)
            px, py = min(comp, key=lambda c: (c[0] - mx) ** 2 + (c[1] - my) ** 2)
            out.append((b, (px * LABEL_CELL + LABEL_CELL // 2, py * LABEL_CELL + LABEL_CELL // 2), len(comp)))
    return out


def realm_areas(sim):
    """JSON-safe area info for one open-Realm RealmSim (cached per sim): tile-space
    points for biome regions, landmarks, islands, NPCs, island chests and spawn.
    Sent once to co-op clients alongside the map."""
    if sim is None:
        return None
    cached = _AREA_CACHE.get(id(sim))
    if cached is not None and cached[0] is sim:
        return cached[1]
    t = C.TILE
    grid = sim.realm_map.grid
    regions = _biome_regions(grid)
    info = {
        "w": len(grid[0]), "h": len(grid),
        "biomes": [{"biome": b, "x": x, "y": y, "size": n} for b, (x, y), n in regions],
        "landmarks": [{"biome": lm["biome"], "name": lm["name"], "x": lm["pos"].x / t, "y": lm["pos"].y / t}
                      for lm in getattr(sim, "landmarks", [])],
        "islands": [{"idx": isl["idx"], "label": isl["label"], "x": isl["pos"].x / t, "y": isl["pos"].y / t}
                    for isl in getattr(sim, "islands", [])],
        "npcs": [{"id": n.npc_id, "name": n.name, "x": n.home.x / t, "y": n.home.y / t}
                 for n in getattr(sim, "npcs", [])],
        "chests": [{"idx": ch["idx"], "x": ch["pos"].x / t, "y": ch["pos"].y / t}
                   for ch in getattr(sim, "island_chests", [])],
        # Batch 15 big named places (game/areas.py) - centre + size in tiles
        "places": [{"key": a["key"], "name": a["name"], "biome": a["biome"],
                    "x": a["rect"].centerx, "y": a["rect"].centery, "w": a["rect"].w, "h": a["rect"].h}
                   for a in getattr(sim, "areas", [])],
    }
    sp = sim.spawn_point()
    info["spawn"] = {"x": sp.x / t, "y": sp.y / t}
    if len(_AREA_CACHE) > 4:
        _AREA_CACHE.clear()
    _AREA_CACHE[id(sim)] = (sim, info)
    return info


def markers_for(where, areas):
    """Resolve a 'where' dict against realm `areas` -> [(tile_x, tile_y, label)] points.
    Biomes resolve to their region label points (the biggest few)."""
    if not areas or not where:
        return []
    pts = []
    for b in where.get("biomes", []):
        regs = sorted((r for r in areas["biomes"] if r["biome"] == b), key=lambda r: -r["size"])[:4]
        pts += [(r["x"], r["y"], BIOME_LABELS.get(b, b)) for r in regs]
    for a in where.get("areas", []):
        if a.startswith("npc:"):
            pts += [(n["x"], n["y"], n["name"]) for n in areas["npcs"] if n["id"] == a[4:]]
        elif a.startswith("landmark:"):
            pts += [(l["x"], l["y"], cap(l["name"])) for l in areas["landmarks"] if l["biome"] == a[9:]]
        elif a == "landmarks":
            pts += [(l["x"], l["y"], cap(l["name"])) for l in areas["landmarks"]]
        elif a.startswith("island:"):
            pts += [(i["x"], i["y"], i["label"]) for i in areas["islands"] if str(i["idx"]) == a[7:]]
        elif a in ("islands", "island_chests"):
            pts += [(i["x"], i["y"], i["label"]) for i in areas["islands"]]
        elif a.startswith("place:"):
            pts += [(pl["x"], pl["y"], pl["name"]) for pl in areas.get("places", []) if pl["key"] == a[6:]]
        elif a == "places":
            pts += [(pl["x"], pl["y"], pl["name"]) for pl in areas.get("places", [])]
        elif a == "realm" and areas.get("spawn"):
            pts.append((areas["spawn"]["x"], areas["spawn"]["y"], "Arrival beach"))
        else:
            regs = sorted((r for r in areas["biomes"] if r["biome"] == a), key=lambda r: -r["size"])[:4]
            pts += [(r["x"], r["y"], BIOME_LABELS.get(a, a)) for r in regs]
    return pts


def target_note(target):
    """Extra text for targets that have no fixed map location."""
    if not target:
        return ""
    k = target.get("key")
    if k == "world_boss":
        return "The world boss roams - watch chat for its announcement."
    if k == "dungeons":
        return "Dungeons open from Dungeon Shards (elite drops) - anywhere."
    if k == "pets":
        return "Pets: feed them from your backpack (Tab = pet panel)."
    if k == "mad_god":
        return "The Forge opens via Father Given in the Nexus."
    return ""


def tile_biome(grid, tx, ty):
    from game import world
    if not grid or not (0 <= ty < len(grid) and 0 <= tx < len(grid[0])):
        return None
    names = world.TILE_TO_BIOME_NAME if hasattr(world, "TILE_TO_BIOME_NAME") else world.GROUND_TO_BIOME_NAME
    return names.get(grid[ty][tx])


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

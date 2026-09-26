"""
Side quests (Batch 15): 30 optional quests layered on top of the story (game/story.py).

Two sources:
  * the random BOARD - BOARD_SIZE quests with no giver are always active; when one is
    finished (or abandoned) a new random one takes its slot, so there's always something
    small to do while out in the Realm;
  * NPC quests - offered in dialogue (game/dialogue.py) by the NPC named in `giver`;
    quests with a `turn_in` NPC are handed back to them, the rest finish on their own.

Progress runs on the same (kind, key) event shape as the story, plus an optional ctx dict
({"biome", "count", "night", "uid", "npc", "person"}) - see SideQuestProgress.on_event.
Events come from RealmSim (kills, standing near wildlife groups, reaching places, island
chests, fishing, dungeon clears, nights survived, world boss kills) and from the dialogue
engine (talking, hearing tales). Pure Python, no pygame - persisted per character inside
Player.full_state()["sidequests"].
"""
import random

BOARD_SIZE = 3
NEAR_RADIUS = 170.0  # world units - "standing next to a group" of wildlife
NEAR_TICK = 0.5      # RealmSim scans for nearby wildlife groups this often (seconds)


def _q(title, desc, ev, need, target, reward, giver=None, turn_in=None, key=None, **extra):
    d = dict(title=title, desc=desc, ev=ev, need=need, target=target, reward=reward,
             giver=giver, turn_in=turn_in, key=key)
    d.update(extra)
    return d


def _t(kind, key, label):
    """A quest's target, for the quest log / dictionary / quest map (Phase 1B):
    kind is mob | npc | area | boss."""
    return {"kind": kind, "key": key, "label": label}


def _r(xp, echoes=0, loot="elite"):
    return {"xp": xp, "echoes": echoes, "loot": loot}


# quest items (see make_quest_item) - what they're called and where they come from
QUEST_ITEMS = {
    "glowcap": ("Glowcap Mushroom", "A mushroom that glows faintly and smells like a sock. Mossbeard wants these."),
    "camel_bell": ("Sandy Sal's Camel Bell", "A dented brass bell. Somewhere, a camel is very quiet about it."),
    "driftwood_rum": ("Bottle of Driftwood Rum", "Aged in a shipwreck. Tastes like a shipwreck."),
    "ember_core": ("Ember Core", "Still warm. Cinder Pete says it's 'the good stuff'."),
}

QUESTS = {
    # ---- board (no giver): wildlife groups, hunting, exploring ----------------------
    "herd_whisperer": _q("Herd Whisperer", "Stand among a herd of 3+ deer for 10 seconds.",
                         "near", 10, _t("mob", "deer", "Deer"), _r(160, 1), key="deer", group=3),
    "hare_census": _q("Hare Census", "Stand near a group of 2+ forest hares for 8 seconds. Count them. Twice.",
                      "near", 8, _t("mob", "forest_hare", "Forest Hare"), _r(120, 1), key="forest_hare", group=2),
    "birdwatcher": _q("Birdwatcher", "Stand near songbirds in 2 different biomes.",
                      "near", 2, _t("mob", "songbird", "Songbird"), _r(180, 1), key="songbird", group=1,
                      distinct="biome", min_time=3.0),
    "pest_control": _q("Pest Control", "Slay 15 goblins. They started it. Probably.",
                       "kill", 15, _t("mob", "goblin", "Goblin"), _r(220, 1), key="goblin"),
    "yeti_tag": _q("Yeti Tag", "Defeat 3 yetis without dying. You're it.",
                   "kill", 3, _t("mob", "yeti", "Yeti"), _r(260, 2), key="yeti", reset_on_death=True),
    "island_hopper": _q("Island Hopper", "Set foot on 5 different islands of the Reforging.",
                        "reach", 5, _t("area", "islands", "The Reforging islands"), _r(300, 2), key="island",
                        distinct="idx"),
    "chest_raider": _q("Chest Raider", "Open 3 island treasure chests.",
                       "chest", 3, _t("area", "island_chests", "Island chests"), _r(260, 2), distinct="idx"),
    "dungeon_crawl": _q("Dungeon Crawl", "Clear any 2 dungeons (beat their boss).",
                        "dungeon", 2, _t("area", "dungeons", "Dungeon portals"), _r(400, 2, "boss")),
    "snack_time": _q("Snack Time", "Feed your pet 5 items. It is always hungry. Always.",
                     "feed_pet", 5, _t("area", "pets", "Pets"), _r(120, 1)),
    "night_watch": _q("Night Watch", "Survive one whole night out in the Realm.",
                      "night", 1, _t("area", "realm", "The Godlands at night"), _r(250, 2)),
    "lizard_race": _q("Lizard Race", "Stand near a group of 2+ desert lizards for 6 seconds. Nobody wins.",
                      "near", 6, _t("mob", "desert_lizard", "Desert Lizard"), _r(130, 1), key="desert_lizard", group=2),
    "heron_haiku": _q("Heron Haiku", "Talk to 3 different marsh herons. Five, seven, five.",
                      "talk", 3, _t("mob", "marsh_heron", "Marsh Heron"), _r(150, 1), key="marsh_heron",
                      distinct="uid"),
    "miniboss_menace": _q("Mini-boss Menace", "Defeat 2 island mini-bosses.",
                          "kill", 2, _t("boss", "island_minibosses", "Island mini-bosses"), _r(450, 3, "boss"),
                          key=("cinder_colossus", "choir_sovereign", "rubble_warlord", "coral_leviathan",
                               "ashreach_revenant", "tideglass_warden", "thornrock_colossus",
                               "driftbell_matriarch", "ashenreach_devourer", "abyssal_choirmaster")),
    "guardian_groupie": _q("Guardian Groupie", "Defeat 2 Landmark Guardians.",
                           "guardian", 2, _t("boss", "guardians", "Landmark Guardians"), _r(400, 2, "boss")),
    "world_boss_witness": _q("World Boss Witness", "Be close by when a roaming world boss falls.",
                             "world_boss", 1, _t("boss", "world_boss", "The roaming world boss"), _r(500, 3, "boss")),
    # ---- NPC quests ------------------------------------------------------------------
    "flamingo_gossip": _q("Flamingo Gossip", "Captain Driftwood wants the latest gossip from the Gossiping Flamingos.",
                          "talk", 1, _t("npc", "flamingos", "Gossiping Flamingos"), _r(140, 1),
                          key="flamingos", giver="driftwood"),
    "tortoise_wisdom": _q("Tortoise Wisdom", "Hear all 3 of the Philosopher Tortoise's tales.",
                          "tale", 3, _t("npc", "tortoise", "Philosopher Tortoise"), _r(200, 2),
                          key="tortoise", giver="tortoise", distinct="topic"),
    "mossbeard_mushrooms": _q("Mossbeard's Mushrooms", "Collect 6 Glowcap Mushrooms from forest monsters "
                              "and bring them to Old Mossbeard.", "deliver", 6,
                              _t("npc", "mossbeard", "Old Mossbeard"), _r(260, 2), giver="mossbeard",
                              turn_in="mossbeard", item="glowcap"),
    "camel_bell": _q("Sal's Lost Camel Bell", "Find Sandy Sal's camel bell in an island chest and bring it back.",
                     "deliver", 1, _t("area", "island_chests", "Island chests"), _r(280, 2), giver="sal",
                     turn_in="sal", item="camel_bell"),
    "ice_fishing": _q("Ice Fishing Derby", "Catch 5 things while fishing in the tundra or ice fields.",
                      "fish", 5, _t("npc", "frostine", "Frostine the Ice Fisher"), _r(220, 2), giver="frostine",
                      turn_in="frostine", biomes=("tundra", "ice")),
    "rum_run": _q("Captain's Rum Run", "Bring Captain Driftwood 3 bottles of Driftwood Rum from island chests.",
                  "deliver", 3, _t("area", "island_chests", "Island chests"), _r(320, 2), giver="driftwood",
                  turn_in="driftwood", item="driftwood_rum"),
    "bog_brew": _q("Bog Brew", "Slay 8 bog crawlers for Madame Murk's cauldron.",
                   "kill", 8, _t("mob", "bog_crawler", "Bog Crawler"), _r(240, 2), key="bog_crawler",
                   giver="murk", turn_in="murk"),
    "pilgrimage": _q("Monk's Pilgrimage", "Visit 4 different landmarks, then report back to Brother Tipsy.",
                     "reach", 4, _t("area", "landmarks", "Landmarks"), _r(300, 2), key="landmark",
                     distinct="idx", giver="tipsy", turn_in="tipsy"),
    "hot_iron": _q("Hot Iron", "Bring Cinder Pete 3 Ember Cores from salamanders and cinder wisps.",
                   "deliver", 3, _t("mob", "salamander", "Salamander"), _r(300, 2), giver="pete",
                   turn_in="pete", item="ember_core"),
    "fern_samples": _q("Fern Samples", "Visit 3 curious spots in the jungle for Professor Fernleaf.",
                       "reach", 3, _t("area", "jungle", "Jungle"), _r(260, 2), key="vignette:jungle",
                       distinct="idx", giver="fernleaf", turn_in="fernleaf"),
    "scrap_for_rusty": _q("Scrap for Rusty", "Defeat 10 husk wanderers so Rusty can salvage their bits.",
                          "kill", 10, _t("mob", "husk_wanderer", "Husk Wanderer"), _r(260, 2), key="husk_wanderer",
                          giver="rusty", turn_in="rusty"),
    "map_the_deep": _q("Map the Deep", "Chart 3 spots in the caves for Glimmer.",
                       "reach", 3, _t("area", "cave", "Caves"), _r(280, 2), key="vignette:cave",
                       distinct="idx", giver="glimmer", turn_in="glimmer"),
    "moth_to_a_flame": _q("Moth to a Flame", "Stand near cave moths at night for 6 seconds. The Mushroom Folk "
                          "call it 'a vibe'.", "near", 6, _t("mob", "cave_moth", "Cave Moth"), _r(200, 2),
                          key="cave_moth", group=1, night=True, giver="mushroom_folk"),
    "barkeeps_tab": _q("Barkeep's Tab", "Talk to 5 different people around the world, then tell Bitterwick "
                       "who owes him money.", "talk", 5, _t("npc", "bitterwick", "Barkeep Bitterwick"),
                       _r(200, 2), distinct="npc", person_only=True, giver="bitterwick", turn_in="bitterwick"),
    "elk_escort": _q("Elk Escort", "Walk with the Grand Elk Herd for 30 seconds. Keep up.",
                     "near", 30, _t("npc", "elk_herd", "Grand Elk Herd"), _r(240, 2), key="npc:elk_herd",
                     group=1, giver="elk_herd"),
}

BOARD_POOL = [qid for qid, q in QUESTS.items() if q["giver"] is None]


def make_quest_item(key):
    from game.items import Item
    name, desc = QUEST_ITEMS[key]
    return Item(name, "quest", 0, "quest", description=desc + " (quest item)", quest_key=key)


def count_quest_items(player, key):
    return sum(1 for it in getattr(player, "backpack", ()) if getattr(it, "quest_key", "") == key)


def _key_matches(want, key):
    if want is None:
        return True
    if isinstance(want, (tuple, list)):
        return key in want
    return want == key


class SideQuestProgress:
    def __init__(self):
        self.active = {}        # qid -> {"have": float, "seen": [distinct values]}
        self.done = []          # finished NPC quests (never offered again); board quests just rotate
        self.board_done = 0     # how many board quests this character has finished
        self.talked = {}        # npc_id -> [topic ids already heard] (dialogue: chats don't repeat)
        self.pending_items = []  # reward Items that didn't fit in the backpack yet (see flush)

    # ------------------------------------------------------------- board --
    def ensure_board(self, rng=random, exclude=()):
        board = [q for q in self.active if QUESTS[q]["giver"] is None]
        pool = [q for q in BOARD_POOL if q not in self.active and q not in exclude]
        rng.shuffle(pool)
        while len(board) < BOARD_SIZE and pool:
            qid = pool.pop()
            self.active[qid] = {"have": 0.0, "seen": []}
            board.append(qid)

    def abandon(self, qid):
        """Drops an active quest (a board quest is replaced right away)."""
        if qid in self.active:
            del self.active[qid]
            self.ensure_board(exclude=(qid,))
            return True
        return False

    # -------------------------------------------------------------- npc --
    def can_offer(self, qid):
        return qid in QUESTS and qid not in self.active and qid not in self.done

    def accept(self, qid):
        if not self.can_offer(qid):
            return []
        self.active[qid] = {"have": 0.0, "seen": []}
        return [(f"New quest: {QUESTS[qid]['title']}", (255, 215, 120))]

    def progress(self, qid, player=None):
        q = QUESTS[qid]
        if q["ev"] == "deliver":
            return count_quest_items(player, q["item"]) if player is not None else 0
        st = self.active.get(qid)
        return st["have"] if st else 0

    def ready(self, qid, player=None):
        return qid in self.active and self.progress(qid, player) >= QUESTS[qid]["need"]

    def wants_item(self, key, player=None):
        """True while an active deliver quest still needs more of quest item `key`."""
        for qid in self.active:
            q = QUESTS[qid]
            if q["ev"] == "deliver" and q.get("item") == key and self.progress(qid, player) < q["need"]:
                return True
        return False

    # ----------------------------------------------------------- events --
    def on_event(self, kind, key=None, amount=1.0, ctx=None, player=None):
        """Feeds one game event to every matching active quest. Returns feed lines.
        Quests with no turn-in NPC complete (and pay out, if `player` is given) here."""
        ctx = ctx or {}
        msgs = []
        for qid in list(self.active):
            q = QUESTS[qid]
            if q["ev"] != kind or not _key_matches(q["key"], key):
                continue
            if q.get("group") and ctx.get("count", 1) < q["group"]:
                continue
            if q.get("night") and not ctx.get("night"):
                continue
            if q.get("biomes") and ctx.get("biome") not in q["biomes"]:
                continue
            if q.get("person_only") and not ctx.get("person"):
                continue
            st = self.active[qid]
            need = q["need"]
            if st["have"] >= need:
                continue
            before = int(st["have"])
            dist = q.get("distinct")
            if dist:
                val = ctx.get(dist)
                if val is None or val in st["seen"]:
                    continue
                if q.get("min_time"):  # e.g. "stand near songbirds in 2 biomes" - linger a moment in each
                    st.setdefault("linger", {})
                    t = st["linger"].get(str(val), 0.0) + amount
                    st["linger"][str(val)] = t
                    if t < q["min_time"]:
                        continue
                st["seen"].append(val)
                st["have"] = float(len(st["seen"]))
            else:
                st["have"] = min(float(need), st["have"] + amount)
            if int(st["have"]) != before or st["have"] >= need:
                if st["have"] >= need:
                    if q["turn_in"] is None:
                        msgs.extend(self._complete(qid, player))
                    else:
                        msgs.append((f"{q['title']}: done - go see {_npc_name(q['turn_in'])}",
                                     (150, 230, 150)))
                elif q["ev"] != "near":
                    msgs.append((f"{q['title']}: {int(st['have'])}/{need}", (200, 200, 150)))
        return msgs

    def on_death(self):
        for qid in list(self.active):
            if QUESTS[qid].get("reset_on_death"):
                self.active[qid] = {"have": 0.0, "seen": []}

    # ---------------------------------------------------------- turn-in --
    def turn_in(self, qid, player):
        """Hands a finished quest to its NPC. Returns (ok, feed lines)."""
        if not self.ready(qid, player):
            return False, [("You're not done with that one yet.", (220, 170, 120))]
        q = QUESTS[qid]
        if q["ev"] == "deliver":
            taken = 0
            for it in list(player.backpack):
                if taken < q["need"] and getattr(it, "quest_key", "") == q["item"]:
                    player.backpack.remove(it)
                    taken += 1
        return True, self._complete(qid, player)

    def _complete(self, qid, player):
        q = QUESTS[qid]
        del self.active[qid]
        if q["giver"] is None:
            self.board_done += 1
        elif qid not in self.done:
            self.done.append(qid)
        msgs = [(f"Quest complete: {q['title']}!", (255, 225, 120))]
        if player is not None:
            msgs.extend(grant_reward(self, player, q["reward"]))
        if q["giver"] is None:
            self.ensure_board(exclude=(qid,))  # a different quest takes the slot
        return msgs

    def flush(self, player):
        """Moves reward items that didn't fit earlier into the backpack, as room allows."""
        msgs = []
        while self.pending_items and len(player.backpack) < player.backpack_size:
            it = self.pending_items.pop(0)
            player.backpack.append(it)
            msgs.append((f"Reward claimed: {it.display_name}", it.color))
        return msgs

    # -------------------------------------------------------------- log --
    def log(self, player=None):
        """Quest-log entries (HUD log, Phase 1B quest log/dictionary/quest map)."""
        out = []
        for qid in self.active:
            q = QUESTS[qid]
            out.append({"id": qid, "title": q["title"], "desc": q["desc"],
                        "have": int(self.progress(qid, player)), "need": q["need"],
                        "ready": self.ready(qid, player), "board": q["giver"] is None,
                        "giver": q["giver"], "turn_in": q["turn_in"], "target": dict(q["target"])})
        out.sort(key=lambda e: (not e["ready"], e["board"], e["title"]))
        return out

    # ------------------------------------------------------ persistence --
    def to_json(self):
        return {"active": {k: {"have": v["have"], "seen": list(v["seen"])} for k, v in self.active.items()},
                "done": list(self.done), "board_done": self.board_done,
                "talked": {k: list(v) for k, v in self.talked.items()},
                "pending_items": [it.to_json() for it in self.pending_items]}

    @staticmethod
    def from_json(d):
        sq = SideQuestProgress()
        if isinstance(d, dict):
            for k, v in (d.get("active") or {}).items():
                if k in QUESTS:
                    sq.active[k] = {"have": float(v.get("have", 0)), "seen": list(v.get("seen", []))}
            sq.done = [q for q in d.get("done", []) if q in QUESTS]
            sq.board_done = int(d.get("board_done", 0))
            sq.talked = {k: list(v) for k, v in (d.get("talked") or {}).items()}
            if d.get("pending_items"):
                from game.items import Item
                sq.pending_items = [Item.from_json(it) for it in d["pending_items"]]
        sq.ensure_board()
        return sq


def grant_reward(progress, player, reward):
    """XP + account echoes + one rolled item (into the backpack, or held in
    progress.pending_items until there's room - never lost)."""
    msgs = []
    xp = reward.get("xp", 0)
    if xp:
        player.gain_xp(xp)
        msgs.append((f"+{xp} XP", (170, 220, 255)))
    echoes = reward.get("echoes", 0)
    if echoes and getattr(player, "name", None):
        try:
            from game import accounts
            accounts.add_echoes(player.name, echoes)
            msgs.append((f"+{echoes} Echo{'es' if echoes != 1 else ''}", (200, 170, 255)))
        except Exception:  # no account on disk (tests / display-only players) - just skip the echoes
            pass
    rank = reward.get("loot")
    if rank:
        from game.items import roll_loot
        rolled = roll_loot(getattr(player, "cls_name", "wizard"), rank, 1.0)
        for _color, it in rolled[:1]:
            if len(player.backpack) < player.backpack_size:
                player.backpack.append(it)
                msgs.append((f"Reward: {it.display_name}", it.color))
            else:
                progress.pending_items.append(it)
                msgs.append((f"Reward {it.display_name} waiting - free a backpack slot", it.color))
    return msgs


def quest_drops(progress, player, enemy_kind, biome, rank):
    """Quest items a kill drops for THIS player (added to their personal loot)."""
    out = []
    if biome == "forest" and progress.wants_item("glowcap", player) and random.random() < 0.4:
        out.append(make_quest_item("glowcap"))
    if enemy_kind in ("salamander", "cinder_wisp") and progress.wants_item("ember_core", player) \
            and random.random() < 0.5:
        out.append(make_quest_item("ember_core"))
    return out


def chest_quest_items(progress, player):
    """Quest items an island chest adds for THIS player (one of each still needed)."""
    return [make_quest_item(key) for key in ("camel_bell", "driftwood_rum") if progress.wants_item(key, player)]


def _npc_name(npc_id):
    try:
        from game.npcs import NPCS
        return NPCS[npc_id]["name"]
    except (ImportError, KeyError):
        return npc_id

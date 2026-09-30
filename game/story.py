"""
The story / critical path: seven acts that go exploration -> combat -> gear ->
the deep inland -> the big islands -> the Mad God (Prologue, Act I "The Grand
Tour" ... Act V "Last Call", Finale), each a short list of objectives fed by
plain (kind, key) events from RealmSim/main.py/server.py/dialogue.py/entities.py.
After the Finale the endgame is the Mad God's Room (a rare key from heroic
dungeons - see realm_sim). Pure data + logic - no pygame, no file I/O.

Save versions: STORY_VERSION 2 is the seven-act arc. Saves / accounts without a
version are from the old five-act arc and are mapped with OLD_ACT_TO_NEW.

Persistence split (see the design notes in the v0.2 final-fixes plan):
- account-wide `story_act` (accounts.py) = number of acts completed. It never
  goes down, so permadeath only costs you the progress INSIDE the current act.
- per-character objective progress = StoryProgress.done, saved in
  Player.full_state()["story"] and deleted with the character.

Soft gates: nothing is ever locked. The acts just point you somewhere, and
act_scale() makes the world meaner as you go.
"""

OUTER_BIOMES = ("forest", "desert", "tundra", "swamp")
INNER_BIOMES = ("highlands", "ashlands", "jungle", "wasteland", "ice", "cave")

# the signature elite each biome's Landmark Guardian is built from (see
# RealmSim._wake_landmark_guardian) - one of that biome's own lair kinds
GUARDIAN_KIND = {
    "forest": "thornling", "desert": "dune_stalker", "tundra": "yeti", "swamp": "troll",
    "highlands": "cliff_strider", "ashlands": "salamander", "jungle": "panther",
    "wasteland": "husk_wanderer", "ice": "frost_wraith", "cave": "deep_stalker",
}

_LANDMARK_NAME = {
    "forest": "the Sunken Idol", "desert": "the Buried Obelisk", "tundra": "the Frozen Watchpost",
    "swamp": "the Drowned Shrine", "highlands": "the Wind-Worn Cairn", "ashlands": "the Charred Altar",
    "jungle": "the Vine-Wrapped Ruin", "wasteland": "the Rusted Beacon", "ice": "the Glacial Monument",
    "cave": "the Forgotten Totem Circle",
}


def landmark_name(biome):
    return _LANDMARK_NAME.get(biome, "a landmark")


# pacing knobs, measured with a headless bot playthrough (16 runs, 4 classes): at 5
# islands / 3 inner guardians the median full run was ~50 min with Act II only ~9.5 min;
# 7 / 4 (+ 3 dungeons fed by guaranteed Guardian shards) adds content without adding waiting (all 10
# islands start armed and each re-arms independently, so 7 distinct ones never queue)
ISLANDS_NEEDED = 7
INNER_GUARDIANS_NEEDED = 4
DUNGEONS_NEEDED = 2  # Act III (every outer/inner Landmark Guardian drops a guaranteed Dungeon Shard)
TOUR_AREAS_NEEDED = 5  # of the 10 big named places (game/areas.py)
TOUR_NPCS_NEEDED = 3
EQUIP_TIER_NEEDED = 8  # Act III: wear a real piece of gear (a T8+ weapon/armor/ring/ability)
HEROIC_DUNGEONS_NEEDED = 2
HEROIC_MIN_LEVEL = 16  # see game/gates.py

STORY_VERSION = 2
# the old five-act arc (Prologue, guardians, islands, deep end, finale, done) -> the seven-act arc
OLD_ACT_TO_NEW = {0: 0, 1: 1, 2: 3, 3: 4, 4: 6, 5: 7}

# act indices, for code/tests that need a specific chapter
ACT_PROLOGUE, ACT_TOUR, ACT_BOUNCERS, ACT_GEAR, ACT_DEEP, ACT_ISLANDS, ACT_FINALE = range(7)


def _obj(obj_id, text, kind, need=1, keys=None):
    """keys=None -> any key of that kind counts; each distinct key counts once."""
    return {"id": obj_id, "text": text, "kind": kind, "need": need, "keys": keys}


ACTS = [
    {"title": "Prologue: Welcome, Sucker",
     "intro": "Ah, fresh meat! I mean... a hero! Father Given, at your service. Mostly.",
     "hint": "Talk to me with F, then take the big swirly portal north into the Realm. It's fine. Probably.",
     "done": "You survived the tutorial! Statistically that puts you ahead of most.",
     "objectives": [
         _obj("talk_given", "Talk to Father Given in the Nexus (F)", "talk"),
         _obj("enter_realm", "Step through the Realm portal", "zone", keys=("realm",)),
     ]},
    {"title": "Act I: The Grand Tour",
     "intro": "Before you go punching anything, see the place. Tourists live longer. Slightly.",
     "hint": f"Wander the Realm: visit {TOUR_AREAS_NEEDED} of the big named places, spot the landmark in every outer biome (forest, desert, tundra, swamp), chat with {TOUR_NPCS_NEEDED} locals (F) and catch a fish at the water (F).",
     "done": "Postcards sent. Now the landmarks have noticed you. Uh oh.",
     "objectives": [
         _obj("tour_areas", f"Visit {TOUR_AREAS_NEEDED} of the Realm's big named places", "area",
              need=TOUR_AREAS_NEEDED),
         _obj("tour_landmarks", "Spot the landmark in each outer biome", "landmark", need=len(OUTER_BIOMES),
              keys=OUTER_BIOMES),
         _obj("tour_npcs", f"Chat with {TOUR_NPCS_NEEDED} Realm locals (F)", "npc", need=TOUR_NPCS_NEEDED),
         _obj("tour_fish", "Catch a fish (F at the water's edge)", "fish"),
     ]},
    {"title": "Act II: Bouncer Problems",
     "intro": "Four old landmarks ring the coast, and each one grew a bouncer. Go un-bounce them.",
     "hint": "Walk up to the landmark in each outer biome - its Guardian wakes up grumpy (and drops a Dungeon Shard). Then clear a dungeon.",
     "done": "The coast is quiet. The bouncers have been... bounced.",
     "objectives": [
         _obj(f"guardian_{b}", f"Defeat the Guardian of {landmark_name(b)} ({b})", "guardian", keys=(b,))
         for b in OUTER_BIOMES
     ] + [_obj("first_dungeon", "Clear a dungeon (beat its boss)", "dungeon")]},
    {"title": "Act III: Retail Therapy",
     "intro": "You're dressed like a tutorial. Let's fix that. Brother Hammerstein runs the Anvil in the Nexus.",
     "hint": f"Wear a T{EQUIP_TIER_NEEDED}+ item, clear {DUNGEONS_NEEDED} more dungeons, finish one Heroic trial quest (their givers hang around the dungeon biomes) and forge something at the Anvil (3 same-tier items -> 1 better one).",
     "done": "Look at you. Shiny. Dangerous. Slightly overdrawn.",
     "objectives": [
         _obj("gear_equip", f"Wear a T{EQUIP_TIER_NEEDED}+ weapon, armor, ring or ability", "equip_tier"),
         _obj("gear_dungeons", f"Clear {DUNGEONS_NEEDED} more dungeons", "dungeon", need=DUNGEONS_NEEDED),
         _obj("gear_heroic_unlock", "Finish a Heroic trial quest (unlocks that Heroic dungeon)", "heroic_unlock"),
         _obj("gear_forge", "Forge an item at Brother Hammerstein's Anvil (Nexus)", "forge"),
     ]},
    {"title": "Act IV: The Deep End",
     "intro": "The inland biomes are where the real trouble brews. Bring snacks. And a will.",
     "hint": f"Beat {INNER_GUARDIANS_NEEDED} inner-biome Landmark Guardians and clear {HEROIC_DUNGEONS_NEEDED} Heroic dungeons (level {HEROIC_MIN_LEVEL}+).",
     "done": "You went off the deep end and came back. Nobody does that.",
     "objectives": [
         _obj("inner_guardians", f"Defeat {INNER_GUARDIANS_NEEDED} inner-biome Landmark Guardians", "guardian",
              need=INNER_GUARDIANS_NEEDED, keys=INNER_BIOMES),
         _obj("heroic_dungeons", f"Clear {HEROIC_DUNGEONS_NEEDED} Heroic dungeons", "heroic_dungeon",
              need=HEROIC_DUNGEONS_NEEDED),
     ]},
    {"title": "Act V: Last Call",
     "intro": "The islands are having a very loud party. They grew. A lot. Bring a level-20 liver and your best gear.",
     "hint": f"Take the ferry from any island harbour (level 20). Calm {ISLANDS_NEEDED} of the 10 islands: beat each island's anchor wave and its mini-boss.",
     "done": "Last call has been called. The islands are sleeping it off.",
     "objectives": [
         _obj("islands", f"Calm any {ISLANDS_NEEDED} islands", "island", need=ISLANDS_NEEDED),
     ]},
    {"title": "Finale: Closing Time",
     "intro": "Right. The Mad God. He's been reforging this place like a bad remix. Time to unplug him.",
     "hint": "Talk to me (F) and I'll open the Forge. Beat the Mad God - twice, he never knows when to leave.",
     "done": "The Mad God is out cold. Drinks are on the house. The house is you. You're buying.",
     "objectives": [
         _obj("mad_god", "Defeat the Mad God in the Forge", "mad_god"),
     ]},
]
FINAL_ACT = len(ACTS)  # story_act == FINAL_ACT means the story is finished (free play)

FREE_PLAY_TITLE = "Free Play"
FREE_PLAY_HINT = ("You beat the Mad God. Mostly. Rumour says Heroic bosses sometimes drop a key to his Room, "
                  "where he's been practising two new forms. Level 20 and T12 gear, or don't bother.")

# difficulty ramps with story progress - applied to every enemy's HP at spawn
ACT_SCALE_STEP = 0.1  # 7 acts: 1.0 (Prologue) .. 1.6 (Finale), the same top end as the old 5-act arc


def act_scale(act):
    return 1.0 + ACT_SCALE_STEP * max(0, min(act, FINAL_ACT - 1))


CREDITS_LINES = [
    "REALM REFORGED",
    "",
    "Starring",
    "YOU, reluctantly",
    "",
    "Father Given .............. as himself (unpaid)",
    "The Mad God ............... as the Mad God (also unpaid, very mad about it)",
    "Every goblin you hit ...... as 'Goblin #1' through 'Goblin #9,412'",
    "",
    "Island catering by",
    "Coral Colada Choir, Tidricane Sanctum, and the rest of the bar crawl",
    "",
    "No landmarks were harmed in the making of this adventure.",
    "The Guardians, however, have filed complaints.",
    "",
    "Special thanks to",
    "Whoever keeps refilling the fountain",
    "",
    "The Realm is still out there.",
    "It's just a little quieter now.",
    "",
    "THE END ...?",
    "(free play unlocked - press Enter)",
]


class StoryProgress:
    """act = index into ACTS (FINAL_ACT when finished); done = {obj_id: [keys...]}."""

    def __init__(self, act=0, done=None):
        self.act = max(0, min(int(act), FINAL_ACT))
        self.done = {k: list(v) for k, v in (done or {}).items()}
        self.just_completed = []  # act indices completed since the owner last looked -
        # the owner (main.py / server.py) drains this to show the banner + save the account

    @property
    def finished(self):
        return self.act >= FINAL_ACT

    def current(self):
        return None if self.finished else ACTS[self.act]

    def _count(self, obj):
        return min(obj["need"], len(self.done.get(obj["id"], [])))

    def wants(self, kind, key=None):
        """True if an event of this kind/key would advance the current act."""
        act = self.current()
        if act is None:
            return False
        for obj in act["objectives"]:
            if obj["kind"] != kind or self._count(obj) >= obj["need"]:
                continue
            if obj["keys"] is not None and key not in obj["keys"]:
                continue
            if key is not None and key in self.done.get(obj["id"], []):
                continue
            return True
        return False

    def on_event(self, kind, key=None):
        """Feeds one event. Returns a list of (message, color) lines to show."""
        act = self.current()
        if act is None:
            return []
        msgs = []
        for obj in act["objectives"]:
            if obj["kind"] != kind or self._count(obj) >= obj["need"]:
                continue
            if obj["keys"] is not None and key not in obj["keys"]:
                continue
            got = self.done.setdefault(obj["id"], [])
            tag = key if key is not None else len(got)
            if tag in got:
                continue
            got.append(tag)
            n = self._count(obj)
            suffix = f" ({n}/{obj['need']})" if obj["need"] > 1 else ""
            msgs.append((f"Quest: {obj['text']}{suffix}" + (" - done!" if n >= obj["need"] else ""),
                         (240, 220, 140)))
            break
        if msgs and all(self._count(o) >= o["need"] for o in act["objectives"]):
            msgs.append((act["done"], (255, 200, 90)))
            self.just_completed.append(self.act)
            self.act += 1
            self.done = {}
            nxt = self.current()
            if nxt is not None:
                msgs.append((f"New chapter: {nxt['title']}", (255, 230, 150)))
        return msgs

    def quest_log(self):
        """Plain dict for the quest-log panel / co-op snapshot."""
        act = self.current()
        if act is None:
            return {"act": self.act, "title": FREE_PLAY_TITLE, "hint": FREE_PLAY_HINT, "objectives": []}
        return {"act": self.act, "title": act["title"], "hint": act["hint"],
                "objectives": [{"text": o["text"], "have": self._count(o), "need": o["need"],
                                "target": objective_target(o)}
                               for o in act["objectives"]]}

    def to_json(self):
        return {"act": self.act, "done": {k: list(v) for k, v in self.done.items()}, "v": STORY_VERSION}

    @staticmethod
    def from_json(d, account_act=0):
        """A character save's story progress, never behind the account's checkpoint.
        A missing/old save (d=None) starts the account's current act fresh. A save from
        the old five-act arc (no "v") is mapped onto the new arc; its in-act progress
        (objective ids that no longer exist) is dropped."""
        d = d or {}
        act = int(d.get("act", 0)) if isinstance(d, dict) else 0
        done = d.get("done", {}) if isinstance(d, dict) and isinstance(d.get("done"), dict) else {}
        if isinstance(d, dict) and d and d.get("v") is None:
            act, done = migrate_act(act), {}
        if act < account_act:
            return StoryProgress(account_act)
        return StoryProgress(act, done)


def migrate_act(old_act):
    """Old five-act index -> seven-act index (see OLD_ACT_TO_NEW)."""
    old_act = max(0, int(old_act))
    return OLD_ACT_TO_NEW.get(old_act, FINAL_ACT)


def objective_target(o):
    """The Quest Log / Dictionary / Quest Map target for a story objective
    (same {kind, key, label} shape as sidequests' targets)."""
    kind, keys = o["kind"], o.get("keys")
    if kind == "talk":
        return {"kind": "npc", "key": "father_given", "label": "Father Given"}
    if kind == "zone":
        return {"kind": "area", "key": "realm", "label": "the Realm portal"}
    if kind == "area":
        return {"kind": "area", "key": "areas", "label": "the big named places"}
    if kind == "landmark":
        return {"kind": "area", "key": "landmarks", "label": "outer-biome landmarks"}
    if kind == "npc":
        return {"kind": "area", "key": "locals", "label": "Realm locals"}
    if kind == "fish":
        return {"kind": "area", "key": "water", "label": "any shoreline"}
    if kind == "equip_tier":
        return {"kind": "area", "key": "gear", "label": f"T{EQUIP_TIER_NEEDED}+ gear"}
    if kind == "forge":
        return {"kind": "area", "key": "anvil", "label": "Brother Hammerstein's Anvil (Nexus)"}
    if kind == "heroic_unlock":
        return {"kind": "area", "key": "heroic_trials", "label": "a Heroic trial quest giver"}
    if kind == "heroic_dungeon":
        return {"kind": "area", "key": "heroic_dungeons", "label": "Heroic dungeons"}
    if kind == "guardian":
        if keys and len(keys) == 1:
            return {"kind": "area", "key": f"landmark:{keys[0]}", "label": landmark_name(keys[0])}
        return {"kind": "boss", "key": "guardians", "label": "Landmark Guardians"}
    if kind == "island":
        return {"kind": "area", "key": "islands", "label": "the islands"}
    if kind == "dungeon":
        return {"kind": "area", "key": "dungeons", "label": "dungeons"}
    if kind == "mad_god":
        return {"kind": "boss", "key": "mad_god", "label": "the Mad God"}
    return None


def given_line(progress, heard):
    """What Father Given says when you talk to him: the act's intro the first time
    this session (`heard` = set of act indices already introduced, updated here),
    then its hint every time after."""
    act = progress.current()
    if act is None:
        return FREE_PLAY_HINT
    if progress.act not in heard:
        heard.add(progress.act)
        return f"{act['intro']} {act['hint']}"
    return act["hint"]

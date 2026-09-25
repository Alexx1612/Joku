"""
The story / critical path: five acts (Prologue -> Act I -> Act II -> Act III ->
Finale), each a short list of objectives fed by plain (kind, key) events from
RealmSim/main.py/server.py. Pure data + logic - no pygame, no file I/O.

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
    {"title": "Act I: The Rim Job",
     "intro": "Four old landmarks ring the coast, and each one grew a bouncer. Go un-bounce them.",
     "hint": "Find the landmark in each outer biome - forest, desert, tundra, swamp. Walk up to it and its Guardian wakes up grumpy.",
     "done": "The Rim is quiet. The bouncers have been... bounced.",
     "objectives": [
         _obj(f"guardian_{b}", f"Defeat the Guardian of {landmark_name(b)} ({b})", "guardian", keys=(b,))
         for b in OUTER_BIOMES
     ]},
    {"title": "Act II: Last Call",
     "intro": "The islands are having a very loud party and the neighbours - that's everyone - are complaining.",
     "hint": "Calm 5 of the 10 islands. Use the island portals in the beach plaza, beat each wave and its mini-boss.",
     "done": "Last call has been called. The islands are sleeping it off.",
     "objectives": [
         _obj("islands", "Calm any 5 islands", "island", need=5),
     ]},
    {"title": "Act III: The Deep End",
     "intro": "The inland biomes are where the real trouble brews. Bring snacks. And a will.",
     "hint": "Beat 3 inner-biome Landmark Guardians, then clear 2 dungeons - use Dungeon Shards that elites drop.",
     "done": "You went off the deep end and came back. Nobody does that.",
     "objectives": [
         _obj("inner_guardians", "Defeat 3 inner-biome Landmark Guardians", "guardian", need=3, keys=INNER_BIOMES),
         _obj("dungeons", "Clear 2 dungeons (beat the boss)", "dungeon", need=2),
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
FREE_PLAY_HINT = "You beat the Mad God. Everything is still out there, just angrier. Enjoy!"

# difficulty ramps with story progress - applied to every enemy's HP at spawn
ACT_SCALE_STEP = 0.15


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
                "objectives": [{"text": o["text"], "have": self._count(o), "need": o["need"]}
                               for o in act["objectives"]]}

    def to_json(self):
        return {"act": self.act, "done": {k: list(v) for k, v in self.done.items()}}

    @staticmethod
    def from_json(d, account_act=0):
        """A character save's story progress, never behind the account's checkpoint.
        A missing/old save (d=None) starts the account's current act fresh."""
        d = d or {}
        act = int(d.get("act", 0)) if isinstance(d, dict) else 0
        done = d.get("done", {}) if isinstance(d, dict) and isinstance(d.get("done"), dict) else {}
        if act < account_act:
            return StoryProgress(account_act)
        return StoryProgress(act, done)


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

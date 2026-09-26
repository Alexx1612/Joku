"""
Dialogue-game conversations (Batch 15) with the NPCs in game/npcs.py and with ambient
wildlife ("animal speak").

A Conversation walks an NPC's data as a small state machine:

    root -> chat topic -> back to root        (each topic is heard once, then gone - chats
                                               never loop forever, and stay heard across
                                               conversations via SideQuestProgress.talked)
    root -> quest offer -> accept / not now   (accepted quests show a reminder instead)
    root -> hand in finished quest -> thanks  (rewards via game/sidequests.py)
    anywhere -> "Bye."                        (always the last option, Esc does the same)

Every non-"Back" option can be taken at most once per conversation, so the graph is
finite by construction: always picking the first option eventually leaves only "Bye."

Pure logic, no drawing - main.py drives it directly; in co-op the SERVER owns the
Conversation (quest grants are authoritative) and sends view() dicts to the client.
"""
from game.npcs import NPCS, WILDLIFE_TALK, WILDLIFE_DEFAULT
from game.sidequests import QUESTS

BYE = "Bye."
BACK = "Back."
MAX_OPTIONS = 5


class Conversation:
    def __init__(self, player, npc_id=None, wildlife_kind=None, uid=None):
        self.player = player
        self.npc_id = npc_id
        self.wildlife_kind = wildlife_kind
        self.uid = uid
        self.node = ("root",)
        self.used = set()        # option keys taken this conversation
        self.first = True
        self.done = False
        self.msgs = []           # feed lines produced by the last start()/choose()
        self.granted = []        # quest ids accepted in this conversation (for callers/tests)

    # ------------------------------------------------------------------ data --
    @property
    def progress(self):
        return self.player.sidequests

    @property
    def name(self):
        if self.npc_id:
            return NPCS[self.npc_id]["name"]
        return self.wildlife_kind.replace("_", " ").title()

    def portrait(self):
        """(source, key) for ui.draw_dialogue's portrait - same sprite the world uses."""
        if self.npc_id:
            d = NPCS[self.npc_id]
            return {"src": d["sprite"][0], "key": d["sprite"][1], "tint": d.get("tint")}
        return {"src": "enemy", "key": self.wildlife_kind, "tint": None}

    def start(self):
        """Opening the conversation counts as 'talking to' this NPC (side quests)."""
        if self.npc_id:
            person = NPCS[self.npc_id]["kind"] == "person"
            self.msgs = self.progress.on_event("talk", self.npc_id,
                                               ctx={"npc": self.npc_id, "person": person, "uid": self.npc_id},
                                               player=self.player)
        else:
            self.msgs = self.progress.on_event("talk", self.wildlife_kind,
                                               ctx={"npc": self.wildlife_kind, "person": False, "uid": self.uid},
                                               player=self.player)
        return self.view()

    # --------------------------------------------------------------- options --
    def _heard(self):
        return self.progress.talked.setdefault(self.npc_id or ("wild:" + self.wildlife_kind), [])

    def _root_options(self):
        opts = []
        if self.npc_id is None:
            label = (WILDLIFE_TALK.get(self.wildlife_kind) or WILDLIFE_DEFAULT)[1]
            if ("chat",) not in self.used:
                opts.append((label, ("chat",)))
            return opts
        d = NPCS[self.npc_id]
        heard = self._heard()
        # quest hand-ins first - that's what you came back for
        for qid in d.get("quests", {}):
            q = QUESTS[qid]
            if q["turn_in"] == self.npc_id and self.progress.ready(qid, self.player):
                opts.append(("I've done what you asked.", ("turnin", qid)))
        for qid, offer in d.get("quests", {}).items():
            if self.progress.can_offer(qid) and ("offer", qid) not in self.used:
                opts.append((offer["label"], ("offer", qid)))
            elif (qid in self.progress.active and not self.progress.ready(qid, self.player)
                  and ("remind", qid) not in self.used):
                opts.append(("About that job...", ("remind", qid)))
        for tid, label, _text, _tale in d.get("topics", []):
            if tid not in heard and ("topic", tid) not in self.used:
                opts.append((label, ("topic", tid)))
        return opts[:MAX_OPTIONS - 1]

    def options(self):
        """[(label, key)] for the current node - "Bye." is always last."""
        kind = self.node[0]
        if kind == "root":
            opts = self._root_options()
        elif kind == "offer":
            opts = [("I'll do it!", ("accept", self.node[1])), ("Not right now.", ("back",))]
        else:
            opts = [(BACK, ("back",))] if self._root_options() else []
        return opts + [(BYE, ("bye",))]

    def text(self):
        kind = self.node[0]
        if self.npc_id is None:
            greet, _label, reply = WILDLIFE_TALK.get(self.wildlife_kind) or WILDLIFE_DEFAULT
            return greet if kind == "root" else reply
        d = NPCS[self.npc_id]
        if kind == "root":
            if self.first:
                return d["greeting"]
            return d["again"] if self._root_options() else d["exhausted"]
        if kind == "topic":
            return next(t[2] for t in d["topics"] if t[0] == self.node[1])
        offer = d["quests"][self.node[1]]
        return {"offer": offer["offer"], "accepted": offer["accept"], "remind": offer["remind"],
                "thanks": offer["thanks"]}.get(kind, "...")

    def view(self):
        if self.done:
            return None
        return {"npc": self.npc_id or self.wildlife_kind, "name": self.name, "text": self.text(),
                "options": [label for label, _ in self.options()], "portrait": self.portrait()}

    # ---------------------------------------------------------------- choose --
    def choose(self, idx):
        """Picks option `idx` (0-based). Returns the new view (None once ended);
        feed lines produced by the choice are left in self.msgs."""
        self.msgs = []
        opts = self.options()
        if not (0 <= idx < len(opts)):
            return self.view()
        _label, key = opts[idx]
        self.first = False
        act = key[0]
        if act == "bye":
            self.done = True
            return None
        if act == "back":
            self.node = ("root",)
            return self.view()
        self.used.add(key)
        if act == "chat":
            self.node = ("topic", "wild")
            self._heard()
        elif act == "topic":
            tid = key[1]
            self._heard().append(tid)
            self.node = ("topic", tid)
            tale = next((t[3] for t in NPCS[self.npc_id]["topics"] if t[0] == tid), False)
            if tale:
                self.msgs.extend(self.progress.on_event("tale", self.npc_id, ctx={"topic": tid},
                                                        player=self.player))
        elif act == "offer":
            self.node = ("offer", key[1])
        elif act == "accept":
            qid = key[1]
            self.msgs.extend(self.progress.accept(qid))
            self.granted.append(qid)
            self.used.add(("offer", qid))
            self.used.add(("remind", qid))
            self.node = ("accepted", qid)
        elif act == "remind":
            self.node = ("remind", key[1])
        elif act == "turnin":
            ok, msgs = self.progress.turn_in(key[1], self.player)
            self.msgs.extend(msgs)
            self.node = ("thanks", key[1]) if ok else ("root",)
        return self.view()

    def bye(self):
        self.done = True
        return None


def start_conversation(player, npc=None, wildlife=None):
    """npc: an npcs.NPC (in-world) or None; wildlife: a neutral Enemy or None."""
    if npc is not None:
        conv = Conversation(player, npc_id=npc.npc_id)
    else:
        conv = Conversation(player, wildlife_kind=wildlife.kind, uid=id(wildlife))
    conv.start()
    return conv


def tree_is_finite(npc_id=None, wildlife_kind=None, player=None, max_steps=200):
    """Test helper: repeatedly picking the FIRST option must reach the end (only
    "Bye." left / chosen) within max_steps."""
    conv = Conversation(player, npc_id=npc_id, wildlife_kind=wildlife_kind, uid=1)
    conv.start()
    for _ in range(max_steps):
        opts = conv.options()
        if len(opts) == 1:  # only Bye
            return True
        conv.choose(0)
        if conv.done:
            return True
    return False

"""
Friendly NPCs and talkable creatures (Batch 15).

NPCS holds 11 people and 4 friendly creature groups - who they are, what they look like,
where they live (an `area` key resolved at world-gen by realm_positions()/nexus_positions()
so Phase 3's big new areas only have to change the area keys), and their dialogue
(greeting, finite chat topics, quest offers - see game/dialogue.py for how a
conversation walks this data).

WILDLIFE_TALK is "animal speak": every neutral ambient wildlife kind (deer, hares, the
Batch 15 elk/penguins/frogs/...) can be talked to with F as well.

The NPC class is the in-world entity: non-hostile, can't be hit by anything (it isn't
in the enemy list at all), wanders a little around its home spot, and barks the odd
ambient line in a speech bubble.
"""
import math
import random

import pygame

from game import constants as C

TALK_RADIUS = 72  # world units - how close you have to be to press F and talk


def _offer(offer, accept, remind, thanks, label="Got any work for me?"):
    return dict(offer=offer, accept=accept, remind=remind, thanks=thanks, label=label)


NPCS = {
    # ------------------------------------------------------------------ people --
    "bitterwick": dict(
        name="Barkeep Bitterwick", kind="person", sprite=("player", "warrior"), tint=(210, 160, 120),
        zone="nexus", area="nexus:tavern", wander=2,
        greeting="Welcome to the Nexus's only tavern! It's a tavern because I said so and there's a barrel.",
        again="Anything else, friend? The barrel's listening too.",
        exhausted="I've told you everything I know. Twice. The barrel remembers.",
        topics=[("barrel", "What's in the barrel?",
                 "Rum. Or water. Or rum-flavoured water. I lost the label in the Reforging and never looked back.", False),
                ("given", "What's the deal with Father Given?",
                 "Father Given? Nice fella. Forgives everyone. Never pays his tab, though, so I'm working on forgiving HIM.", False),
                ("islands", "Why are the islands named after drinks?",
                 "The Mad God reforged the world during happy hour. Everyone names things after drinks during happy hour.", False)],
        quests={"barkeeps_tab": _offer(
            "Folks all over the Realm owe me for drinks. Go chat with five different people out there and "
            "find out who's good for it.",
            "Splendid! Talk to anyone with a face. Report back.",
            "Still collecting names? Five different people, friend. Faces required.",
            "Five debtors! Mostly Brother Tipsy, but still. Here's your cut.",
            label="Need help running the tavern?")},
        barks=["Tavern's open! It's always open. There's no door.", "Who ordered the mystery barrel?"]),
    "mossbeard": dict(
        name="Old Mossbeard", kind="person", sprite=("player", "necromancer"), tint=(120, 170, 110),
        zone="realm", area="area:tavern_town", wander=3,
        greeting="Eh? Visitor! Mind the moss. It's been growing on me for forty years. We're very close.",
        again="What else, sprout?",
        exhausted="That's all the wisdom I've got. The rest is moss.",
        topics=[("hermit", "Why do you live out here?",
                 "The goblins think I'm a very old tree. I haven't had the heart to correct them.", False),
                ("idol", "What's the Sunken Idol?",
                 "An old stone head. It's been sinking for a thousand years. Very patient. Very damp.", False)],
        quests={"mossbeard_mushrooms": _offer(
            "Forest monsters keep eating my Glowcap Mushrooms. Beat six of them back out of the monsters. "
            "Don't ask how. I don't.",
            "Good lad. Or lass. Or whatever you are under all that armour.",
            "Six Glowcaps, sprout. Forest monsters have 'em. Go on.",
            "Glowcaps! Oh, they glow. They glow so much. Take this, before I get sentimental.")},
        barks=["Hmm. Moss.", "The trees are gossiping about you again."]),
    "sal": dict(
        name="Sandy Sal", kind="person", sprite=("player", "rogue"), tint=(230, 200, 130),
        zone="realm", area="area:oasis_bazaar", wander=3,
        greeting="Sand in your boots? Sand in your soul? Sandy Sal has deals on everything except sand.",
        again="Another question? First one's free. Also the second.",
        exhausted="That's my whole sales pitch. I'd do it again but my throat's full of sand.",
        topics=[("trade", "What are you selling?",
                 "Mostly directions. Mostly the wrong ones. Very reasonably priced.", False),
                ("camel", "Where's your camel?",
                 "Dune Stalker spooked him. He ran off and I haven't heard his bell since. Very quiet camel.", False)],
        quests={"camel_bell": _offer(
            "My camel's bell washed away to the islands. A treasure chest out there probably has it. "
            "Bring it back and he'll come home. Camels are simple creatures.",
            "Deal! I'll keep an ear out. For the camel. Not the bell.",
            "No bell yet? Check the island chests. Camels can't swim, but bells float. Apparently.",
            "My bell! *ding* ...Listen. Hear that? That's the sound of a camel NOT coming back. Anyway, thanks!")},
        barks=["Sand! Get your fresh sand!", "No refunds on directions."]),
    "frostine": dict(
        name="Frostine the Ice Fisher", kind="person", sprite=("player", "archer"), tint=(180, 220, 255),
        zone="realm", area="area:frozen_lake_camp", wander=2,
        greeting="Shh! You'll scare the fish. They're frozen, but they're still very jumpy.",
        again="Still here? You're letting the cold in. Somehow. Outside.",
        exhausted="Nothing more to say. Go fish.",
        topics=[("cold", "Aren't you cold?",
                 "Cold is a state of mind. My mind is in a very cold state.", False),
                ("record", "Biggest catch?",
                 "A boot. Still had the foot of a yeti in it. We don't talk about the yeti.", False)],
        quests={"ice_fishing": _offer(
            "It's derby season! Catch five things in the tundra or the ice fields. Anything counts. Even boots.",
            "That's the spirit! Face the water, press F, pretend to be patient.",
            "Five catches in the cold, champ. Tundra or ice. Boots count.",
            "Five! A true Ice Fisher. Here, a prize. Don't lick it, it's frozen.")},
        barks=["...bite. Bite. BITE. ...no.", "The ice is thin today. It's always thin. That's the fun part."]),
    "driftwood": dict(
        name="Captain Driftwood", kind="person", sprite=("player", "paladin"), tint=(170, 130, 90),
        zone="realm", area="spawn", wander=3,
        greeting="Ahoy! Welcome to the Godlands' finest dock. It's the only dock. I built it from a shipwreck. My shipwreck.",
        again="Anything else, landlubber?",
        exhausted="That's every sea story I've got. And a couple I made up.",
        topics=[("ship", "What happened to your ship?",
                 "The islands moved in the Reforging. One moved right into my ship. Very rude island.", False),
                ("islands", "Tell me about the islands.",
                 "Ten of 'em, flaring and singing out past the beach. Each one's got a nasty guardian and a treasure chest.", False)],
        quests={"flamingo_gossip": _offer(
            "The Gossiping Flamingos in the swamp know EVERYTHING that happens on the water. "
            "Go ask them what's new and tell me later. Or don't, they'll tell me anyway.",
            "Aye! Speak slowly. Flamingos are easily offended.",
            "Found the flamingos yet? Pink, loud, standing on one leg. You can't miss 'em.",
            "Ha! So it WAS the Tidricane that ate my ship. Thanks, matey.",
            label="Heard any rumours?"),
            "rum_run": _offer(
            "My rum cellar sank with the ship. The island treasure chests have bottles of Driftwood Rum - "
            "bring me three.",
            "A true sailor! Three bottles. Don't drink them on the way.",
            "Three bottles of Driftwood Rum, from the island chests. I can smell you haven't got them.",
            "RUM! Three whole bottles! This calls for a celebration. And a nap.",
            label="Any jobs for a sailor?")},
        barks=["Mind the planks!", "Land ho! ...oh, we're already on land."]),
    "murk": dict(
        name="Madame Murk", kind="person", sprite=("player", "necromancer"), tint=(150, 110, 190),
        zone="realm", area="area:witchs_hollow", wander=2,
        greeting="Welcome to my hollow, dearie. Don't touch the cauldron. Don't smell the cauldron. Don't look at it.",
        again="More questions, dearie? The cauldron has questions too.",
        exhausted="That's all the swamp told me. It's shy.",
        topics=[("brew", "What are you brewing?",
                 "Bog Brew. Cures everything except whatever the Bog Brew gives you.", False),
                ("witch", "Are you a witch?",
                 "I'm a Wellness Consultant. The warts are a lifestyle choice.", False)],
        quests={"bog_brew": _offer(
            "My brew needs eight bog crawlers' worth of... essence. Go squish some for me, dearie.",
            "Wonderful. Squish responsibly.",
            "Eight bog crawlers, dearie. The cauldron is getting impatient. It's bubbling at me.",
            "Perfect essence! The brew is ready. You don't want any. Here's something nicer.")},
        barks=["Double, double... hm, I forgot the rest.", "Eye of newt, ear of goblin, pinch of salt..."]),
    "tipsy": dict(
        name="Brother Tipsy", kind="person", sprite=("player", "priest"), tint=(230, 180, 140),
        zone="realm", area="area:mountain_monastery", wander=4,
        greeting="Peace be with you! And also with me. Mostly with me. Hic.",
        again="Yes, my child? Speak up, the mountains are spinning.",
        exhausted="I have preached all my preachings. Now I shall nap.",
        topics=[("monastery", "Where's your monastery?",
                 "I left it to go on a pilgrimage. Then I forgot where I parked it.", False),
                ("tab", "Do you owe Bitterwick money?",
                 "Owe is a strong word. I prefer 'spiritually indebted'.", False)],
        quests={"pilgrimage": _offer(
            "A true pilgrim visits the four corners of the world! Or any four landmarks. Visit four for me "
            "and I'll consider my pilgrimage done by proxy.",
            "Bless you! My legs thank you. My liver doesn't care.",
            "Four landmarks, child. Walk right up to them. Soak in the holiness.",
            "Four! My pilgrimage is complete and I never left this rock. Take my blessing. And this.")},
        barks=["Hic.", "Blessed are the thirsty."]),
    "pete": dict(
        name="Cinder Pete", kind="person", sprite=("player", "warrior"), tint=(240, 140, 90),
        zone="realm", area="area:forge_camp", wander=2,
        greeting="Oi! Welcome to my forge camp. Mind the lava. And the other lava. And that bit's also lava.",
        again="What now? My hammer's getting cold. It's never cold.",
        exhausted="I'm a smith, not a storyteller. Out.",
        topics=[("forge", "Why forge in the Ashlands?",
                 "Free heat. The rent's a bit high though. The rent is being on fire.", False),
                ("hammer", "Nice hammer.",
                 "Thanks, I made it. With another hammer. Which I also made. It's hammers all the way down.", False)],
        quests={"hot_iron": _offer(
            "Salamanders and cinder wisps have Ember Cores in 'em. Best fuel there is. Bring me three.",
            "Top stuff. Don't hold 'em too long, they get spicy.",
            "Three Ember Cores. Salamanders, cinder wisps. Go on, the forge is hungry.",
            "Ooh, that's the good stuff! Here, something I forged earlier. It's only a little bit on fire.")},
        barks=["*CLANG*", "Hot enough for ya? Ha. It's always hot enough."]),
    "fernleaf": dict(
        name="Professor Fernleaf", kind="person", sprite=("player", "wizard"), tint=(140, 210, 140),
        zone="realm", area="area:botanists_glade", wander=3,
        greeting="Ah, a research assistant! Excellent. The last one was eaten by a plant. For science.",
        again="Yes, yes? Quickly, the ferns are listening.",
        exhausted="That concludes today's lecture. There will be a test. There won't.",
        topics=[("plants", "What do you study?",
                 "Carnivorous ferns. They study me back. It's a very close working relationship.", False),
                ("panthers", "Aren't the panthers dangerous?",
                 "Only if you're made of meat. Are you made of meat? Oh dear.", False)],
        quests={"fern_samples": _offer(
            "The jungle has curious little spots - old ruins, weird trees, a rock shaped like my aunt. "
            "Visit three of them and describe them to me. Loudly.",
            "Marvellous! Take notes. Or don't. I'll make them up anyway.",
            "Three curious jungle spots, assistant! Chop chop. Not literally.",
            "Fascinating! Especially the rock that looks like my aunt. Your payment, as promised.")},
        barks=["Fascinating!", "Don't touch that. Or do. For science."]),
    "rusty": dict(
        name="Rusty the Scrap Golem", kind="person", sprite=("enemy", "shattered_golem"), tint=(200, 150, 110),
        zone="realm", area="area:scrapyard", wander=2,
        greeting="BEEP. GREETINGS, SOFT HUMAN. I AM RUSTY. I AM ALSO RUSTY. IT IS A PUN. HA. HA.",
        again="QUERY?",
        exhausted="DIALOGUE BUFFER EMPTY. PLEASE INSERT MORE SCRAP.",
        topics=[("made", "Who made you?",
                 "I ASSEMBLED MYSELF FROM SPARE PARTS AND OPTIMISM. MOSTLY OPTIMISM. THE PARTS ARE LOOSE.", False),
                ("feelings", "Do you have feelings?",
                 "I HAVE ONE FEELING. IT IS 'SQUEAKY'. PLEASE DO NOT OIL ME, I HAVE GROWN ATTACHED TO IT.", False)],
        quests={"scrap_for_rusty": _offer(
            "HUSK WANDERERS CONTAIN EXCELLENT SCRAP. PLEASE DISASSEMBLE TEN. VIOLENTLY. BEEP.",
            "AFFIRMATIVE. I WILL WAIT HERE. I AM GOOD AT STANDING STILL. IT IS MY BEST SKILL.",
            "TEN HUSK WANDERERS REQUIRED. CURRENT HAPPINESS: SQUEAKY.",
            "SCRAP RECEIVED. HAPPINESS LEVEL: VERY SQUEAKY. HERE IS A GIFT. IT IS NOT A BOMB.")},
        barks=["BEEP.", "SQUEAK."]),
    "glimmer": dict(
        name="Glimmer the Cartographer", kind="person", sprite=("player", "assassin"), tint=(190, 170, 255),
        zone="realm", area="area:crystal_caverns", wander=2,
        greeting="Oh! A light! No wait, that's your face. Hello! I'm mapping the caves. It's going... darkly.",
        again="Yes? Careful, I just put that stalactite on the map.",
        exhausted="I've no more to tell. My map has more to tell. It's mostly blank.",
        topics=[("map", "Can I see your map?",
                 "It's a very accurate map of the dark. See? Black. All black. Very thorough.", False),
                ("lurkers", "What lives down here?",
                 "Cave lurkers, deep stalkers, and the Mushroom Folk. The Mushroom Folk are the nicest. Don't eat them.", False)],
        quests={"map_the_deep": _offer(
            "Could you visit three interesting spots in the caves and tell me what's there? "
            "My lantern ran out in 1987.",
            "Wonderful! Walk right up to anything that looks like a landmark. Or a rock. Rocks are fine.",
            "Three cave spots, please! I've drawn the frame already. It's the easy part.",
            "Now my map has THINGS on it! Look at all those things. Here, take this for your trouble.")},
        barks=["Left at the stalagmite... no, the OTHER stalagmite.", "Is it dark in here or is it me?"]),
    # ---------------------------------------------------------- friendly creatures --
    "elk_herd": dict(
        name="Grand Elk Herd", kind="creature", sprite=("enemy", "elk"), tint=None, count=3, scale=1.25,
        zone="realm", area="area:elk_meadow", wander=9,
        greeting="*The biggest elk looks at you. Somehow you understand it.* \"We are going to the lake. We are always going to the lake.\"",
        again="*The elk chews thoughtfully.*",
        exhausted="*The herd has nothing more to say. It is thinking about the lake.*",
        topics=[("lake", "Why the lake?",
                 "\"Grass is good. Lake grass is better. Lake grass has a view.\"", False),
                ("antlers", "Nice antlers.",
                 "\"Thank you. They grow back every year. Like confidence.\"", False)],
        quests={"elk_escort": _offer(
            "\"Walk with us. Wolves do not bother a herd. Or they do, but it is less awkward with company.\"",
            "\"Good. Stay close. We walk slowly. We are majestic.\"",
            "\"Stay near the herd. We are still walking. Majestically.\"",
            "\"We have walked far together. Take this. We found it in a bush.\"",
            label="Can I walk with you?")},
        barks=["*majestic snort*", "*the herd moves on, majestically*"]),
    "flamingos": dict(
        name="Gossiping Flamingos", kind="creature", sprite=("enemy", "flamingo"), tint=None, count=3, scale=1.0,
        zone="realm", area="vignette:swamp", wander=4,
        greeting="\"Oh. My. GOSH. A visitor! Deborah, LOOK. Don't look. Look!\"",
        again="\"MORE gossip? Honey, we have SO much more.\"",
        exhausted="\"We're all gossiped out, darling. Come back when something scandalous happens.\"",
        topics=[("tidricane", "Heard anything about the islands?",
                 "\"The Tidricane Sanctum ate a SHIP. A whole ship! The captain was LIVID. Captain Driftwood, honey. "
                 "Tell him we said hi.\"", False),
                ("leg", "Why do you stand on one leg?",
                 "\"If we put the other one down, we'd fall over, sweetie. That's basic science.\"", False)],
        quests={},
        barks=["\"Did you HEAR?\"", "\"I'm not one to gossip, BUT...\""]),
    "tortoise": dict(
        name="Philosopher Tortoise", kind="creature", sprite=("enemy", "tortoise"), tint=None, count=1, scale=1.6,
        zone="realm", area="area:oasis_bazaar", wander=1,
        greeting="\"...Hello. ...I have been... expecting you. ...For about... three hundred years.\"",
        again="\"...Yes?\"",
        exhausted="\"...I have no more tales. ...Come back in... a century.\"",
        topics=[("tale_haste", "Tell me a tale. (1)",
                 "\"...Once... a hare challenged me... to a race. ...He won. ...Hares are very fast. ...The end.\"", True),
                ("tale_sand", "Tell me another tale. (2)",
                 "\"...Every grain of sand... was once a rock... with big dreams. ...Be the rock.\"", True),
                ("tale_god", "Tell me one about the Mad God. (3)",
                 "\"...The Mad God... once asked me... for directions. ...I am still thinking... about the answer.\"", True)],
        quests={"tortoise_wisdom": _offer(
            "\"...I know three tales. ...Listening to all three... is a quest... in itself.\"",
            "\"...Good. ...Sit. ...This will take... a while.\"",
            "\"...There are... more tales. ...Ask.\"",
            "\"...You listened... to everything. ...Nobody does that. ...Take this.\"",
            label="Do you have any wisdom?")},
        barks=["\"...\"", "\"...slowly...\""]),
    "mushroom_folk": dict(
        name="Mushroom Folk", kind="creature", sprite=("enemy", "mushroom_folk"), tint=None, count=4, scale=1.0,
        zone="realm", area="area:crystal_caverns", wander=3,
        greeting="\"Heyyy, a tall one! Come sit in the circle. The circle is where the vibes live.\"",
        again="\"Still vibing? Nice.\"",
        exhausted="\"We've shared all our vibes, man. Go make your own.\"",
        topics=[("circle", "What's the circle for?",
                 "\"It's a fairy ring, dude. We're not fairies. We just like the ring.\"", False),
                ("eat", "Can I eat you?",
                 "\"Rude. But also... no. We'd give you SUCH weird dreams.\"", False)],
        quests={"moth_to_a_flame": _offer(
            "\"At night, the cave moths do this glowy dance thing. Go stand with them for a bit. It's a whole mood.\"",
            "\"Righteous. Night-time only, man. Moths are night people.\"",
            "\"Go hang with the cave moths after dark, dude.\"",
            "\"You felt it, right? The vibe? Here, take this glowy thing.\"",
            label="Got anything for me to do?")},
        barks=["\"Vibes.\"", "\"Spore-tacular.\""]),
}


# "animal speak" - talking to ambient wildlife with F. Kept short: a greeting and
# one chat line each (finite, like every NPC conversation).
WILDLIFE_TALK = {
    "deer": ("*The deer stares at you.* \"Are you a very tall, very loud tree?\"",
             "Just passing through.", "\"Pass quietly. We're counting the grass.\""),
    "forest_hare": ("*The hare's nose twitches at an alarming speed.* \"Did you bring carrots? Say yes.\"",
                    "No carrots, sorry.", "\"Unbelievable. Unforgivable. Hop off.\""),
    "songbird": ("\"Tweet! That's bird for 'hello'. Also for 'goodbye'. We're efficient.\"",
                 "Sing me something.", "\"Tweet tweet tweet! That was an opera. You're welcome.\""),
    "desert_lizard": ("\"Hsss. I'm not hissing at you. I'm just very dehydrated.\"",
                      "Want some water?", "\"Water? No thanks. I get all my water from sunlight and spite.\""),
    "marsh_heron": ("*The heron stands perfectly still.* \"Silent pond. One leg. A fish looks up. I am lunch.\"",
                    "Was that a haiku?", "\"Mud between my toes. / You interrupt my fishing. / Please go. Five syllables.\""),
    "cave_moth": ("\"Is that a light? Are YOU a light? Please be a light.\"",
                  "I'm not a light.", "\"Devastating. Truly the darkest day. They're all dark days down here.\""),
    "elk": ("\"Have you seen the lake? We're going to the lake.\"",
            "Which lake?", "\"THE lake. You'll know it when you see it. It's wet.\""),
    "mountain_goat": ("\"Baa. I climbed that cliff. Then I climbed back down. Then up again. Baa.\"",
                      "Why?", "\"Because it was there. And I was bored. Mostly bored.\""),
    "snow_fox": ("\"Brr! Oh, hi. Is your coat warm? Can I live in it?\"",
                 "No.", "\"Worth a shot. *curls into a tiny snowball*\""),
    "scrap_rat": ("\"Squeak! Shiny! Do you have shiny? I trade for shiny.\"",
                  "What do you trade?", "\"Other shiny. It's a very circular economy.\""),
    "tortoise": ("\"...Oh. ...Hello. ...You're walking... so fast.\"",
                 "Sorry.", "\"...Don't be. ...Be slower.\""),
    "tree_frog": ("\"RIBBIT. That's it. That's all I've got. RIBBIT.\"",
                  "Nice ribbit.", "\"...Nobody's ever said that to me before. RIBBIT.\""),
    "fire_beetle": ("\"Careful! I'm very hot right now. Literally. Please don't sit on me.\"",
                    "Wasn't going to.", "\"People always say that. Then they sit on me.\""),
    "flamingo": ("\"Pink is not a colour, sweetie, it's a LIFESTYLE.\"",
                 "Noted.", "\"Good. Now stand on one leg. No? Your loss.\""),
    "ice_penguin": ("*The penguin waddles closer.* \"Is this the way to the beach? The warm one?\"",
                    "Wrong way, sorry.", "\"Story of my life. *waddles off in the same direction anyway*\""),
    "mushroom_folk": ("\"Oh hey, dude. You look like you need a vibe.\"",
                      "I'm good, thanks.", "\"Cool cool cool. The vibe's always here if you need it.\""),
}
WILDLIFE_DEFAULT = ("*It looks at you blankly.*", "Hello?", "*It keeps looking at you blankly.*")


# Nexus spots (tile offsets from the Nexus centre) - Phase 3 enlarges the Nexus and
# only needs to change these
NEXUS_AREAS = {"nexus:tavern": (-34, 12)}   # inside the tavern district (game/areas.NEXUS_DISTRICTS)


def nexus_positions(nexus_map):
    """{npc_id: world pos} for NPCs whose zone is the Nexus."""
    c = nexus_map.center_world_pos()
    out = {}
    for npc_id, d in NPCS.items():
        if d["zone"] != "nexus":
            continue
        ox, oy = NEXUS_AREAS.get(d["area"], (0, 6))
        out[npc_id] = _walkable_near(nexus_map, pygame.Vector2(c.x + ox * C.TILE, c.y + oy * C.TILE))
    return out


FALLBACK_LANDMARK = {"mossbeard": "forest", "sal": "desert", "frostine": "tundra", "murk": "swamp",
                     "tipsy": "highlands", "pete": "ashlands", "fernleaf": "jungle", "rusty": "wasteland",
                     "glimmer": "cave", "elk_herd": "forest", "tortoise": "desert", "mushroom_folk": "cave"}


def realm_positions(sim):
    """{npc_id: world pos} for realm NPCs, resolved against this map's landmarks,
    curated vignettes and the arrival beach (see NPCS[..]["area"])."""
    tmap = sim.realm_map
    out = {}
    landmarks = {lm["biome"]: lm["pos"] for lm in sim.landmarks}
    places = {a["key"]: a for a in getattr(sim, "areas", [])}
    area_use = {}
    vignettes = {}
    for v in sim.biome_vignettes:
        vignettes.setdefault(v["biome"], []).append(v["anchor"])
    for npc_id, d in NPCS.items():
        if d["zone"] != "realm":
            continue
        area = d["area"]
        pos = None
        if area.startswith("area:"):
            a = places.get(area.split(":", 1)[1])
            if a is not None:
                spots = list(a["spots"].values()) or [a["rect"].center]
                k = area_use.get(area, 0)
                area_use[area] = k + 1
                sx, sy = spots[k % len(spots)]
                pos = pygame.Vector2((sx + 0.5 + 3 * (k // len(spots))) * C.TILE, (sy + 0.5) * C.TILE)
            else:   # the area didn't fit on this map - fall back to the biome landmark
                b = FALLBACK_LANDMARK.get(npc_id)
                if b in landmarks:
                    lm = landmarks[b]
                    pos = pygame.Vector2(lm.x + 3 * C.TILE, lm.y + 2 * C.TILE)
        elif area == "spawn":
            sp = sim.spawn_point()
            pos = pygame.Vector2(sp.x + 5 * C.TILE, sp.y - 2 * C.TILE)
        elif area.startswith("landmark:"):
            lm = landmarks.get(area.split(":", 1)[1])
            if lm is not None:
                pos = pygame.Vector2(lm.x + 3 * C.TILE, lm.y + 2 * C.TILE)
        elif area.startswith("vignette:"):
            biome = area.split(":", 1)[1]
            spots = vignettes.get(biome) or []
            if spots:
                ax, ay = spots[len(spots) // 2]
                pos = pygame.Vector2((ax + 4) * C.TILE, (ay + 4) * C.TILE)
            elif biome in landmarks:
                lm = landmarks[biome]
                pos = pygame.Vector2(lm.x - 6 * C.TILE, lm.y - 4 * C.TILE)
        if pos is None:
            continue
        out[npc_id] = _walkable_near(tmap, pos)
    return out


def _walkable_near(tmap, pos, max_r=12):
    """The closest non-solid tile centre to `pos` (spiral search, in tiles)."""
    tx, ty = int(pos.x // C.TILE), int(pos.y // C.TILE)
    for r in range(max_r + 1):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                wx, wy = (tx + dx) * C.TILE + C.TILE / 2, (ty + dy) * C.TILE + C.TILE / 2
                if not tmap.is_solid(wx, wy):
                    return pygame.Vector2(wx, wy)
    return pygame.Vector2(pos)


class NPC:
    """An in-world friendly NPC / creature group. Never in any enemy list, so no
    bullet, ability or pet can touch it."""
    SPEECH_LIFETIME = 4.0

    def __init__(self, npc_id, pos):
        d = NPCS[npc_id]
        self.npc_id = npc_id
        self.name = d["name"]
        self.pos = pygame.Vector2(pos)
        self.home = pygame.Vector2(pos)
        self.target = pygame.Vector2(pos)
        self.wander = d.get("wander", 2) * C.TILE
        self.speed = 28 if d["kind"] == "person" else 34
        self.pause = random.uniform(1.0, 4.0)
        self.speech = ""
        self.speech_age = 99.0
        self.bark_cd = random.uniform(8.0, 20.0)
        self._t = random.uniform(0, 10)

    def update(self, dt, is_solid=None):
        self._t += dt
        self.speech_age += dt
        if self.pause > 0:
            self.pause -= dt
            if self.pause <= 0:
                ang = random.uniform(0, math.tau)
                dist = random.uniform(0, self.wander)
                self.target = self.home + pygame.Vector2(math.cos(ang), math.sin(ang)) * dist
        else:
            to_t = self.target - self.pos
            if to_t.length() < 3:
                self.pause = random.uniform(2.0, 6.0)
            else:
                step = to_t.normalize() * self.speed * dt
                nxt = self.pos + step
                if is_solid is not None and is_solid(nxt.x, nxt.y):
                    self.pause = random.uniform(1.0, 3.0)
                else:
                    self.pos = nxt
        self.bark_cd -= dt
        if self.bark_cd <= 0:
            self.bark_cd = random.uniform(15.0, 30.0)
            barks = NPCS[self.npc_id].get("barks") or []
            if barks:
                self.speech = random.choice(barks)
                self.speech_age = 0.0

    def draw(self, surf, cam):
        from game import sprites
        d = NPCS[self.npc_id]
        src, key = d["sprite"]
        img = sprites.player_sprite(key) if src == "player" else sprites.enemy_sprite(key)
        scale = d.get("scale", 1.0)
        if scale != 1.0:
            img = pygame.transform.smoothscale(img, (int(img.get_width() * scale), int(img.get_height() * scale)))
        if d.get("tint"):
            img = img.copy()
            img.fill((*d["tint"], 255), special_flags=pygame.BLEND_RGBA_MULT)
        count = d.get("count", 1)
        offsets = [(0, 0), (-22, 10), (22, 12), (-6, 22)][:count]
        bob = math.sin(self._t * 2.2) * 1.5
        for i, (ox, oy) in enumerate(offsets):
            sx, sy = cam((self.pos.x + ox, self.pos.y + oy))
            surf.blit(img, img.get_rect(center=(sx, sy + (bob if i % 2 == 0 else -bob))))

    def net_state(self):
        return dict(id=self.npc_id, x=round(self.pos.x, 1), y=round(self.pos.y, 1),
                    speech=self.speech if self.speech_age < self.SPEECH_LIFETIME else "",
                    speech_age=round(self.speech_age, 2))

    @staticmethod
    def from_net_state(d):
        n = NPC(d["id"], (d["x"], d["y"]))
        n.speech = d.get("speech", "")
        n.speech_age = d.get("speech_age", 99.0)
        return n


def spawn_realm_npcs(sim):
    return [NPC(npc_id, pos) for npc_id, pos in realm_positions(sim).items()]


def spawn_nexus_npcs(nexus_map):
    return [NPC(npc_id, pos) for npc_id, pos in nexus_positions(nexus_map).items()]


def nearest_npc(npcs, pos, radius=TALK_RADIUS):
    best, bd = None, radius
    for n in npcs:
        d = n.pos.distance_to(pos)
        if d <= bd:
            best, bd = n, d
    return best


def nearest_wildlife(enemies, pos, radius=TALK_RADIUS):
    best, bd = None, radius
    for e in enemies:
        if not (e.alive and e.neutral and e.unshootable):
            continue
        d = e.pos.distance_to(pos)
        if d <= bd:
            best, bd = e, d
    return best


def npc_areas():
    """{npc_id: area key} - for the dictionary / quest map (Phase 1B)."""
    return {npc_id: d["area"] for npc_id, d in NPCS.items()}

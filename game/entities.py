"""
Core actors: Player, Enemy, Bullet, Bag.

Stat growth is a simplified, game-friendly approximation of RotMG's
per-class stat maxima - not the exact wiki table (that table is huge and
class-specific per stat-potion); the *formulas* converting stats into
gameplay numbers (game/constants.py) ARE the real RotMG formulas.
"""
import itertools
import math
import random
import pygame

from game import constants as C
from game import sprites
from game import achievements
from game.audio import sound_family  # pure classification lookup, no pygame.mixer side effects
from game.items import (make_starter_weapon, make_starter_ability, Item, SLOT_WEAPON, SLOT_ARMOR,
                         SLOT_RING, SLOT_ABILITY, SLOT_EGG, SLOT_SHARD, SLOT_TEMP_POTION,
                         PERMANENT_POTION_CAP, TEMP_POTION_DURATION, STAT_KEYS, PET_KINDS,
                         CLASS_ARMOR_ARCHETYPE, PET_ABILITY_KEYS, PET_RARITY_MAX_LEVEL,
                         PET_RARITY_START_LEVEL, PET_LEVEL_XP_STEP, PET_FEED_XP_PER_TIER,
                         pet_ability_stats)

LEVEL_CAP = 20

# base stats @ level 1, and which stats grow on level-up (cycled)
CLASS_BASE = {
    "wizard": dict(hp=100, mp=100, att=10, deF=5, spd=25, dex=15, vit=10, wis=30,
                    growth=["wis", "att", "vit", "wis", "dex"]),
    "archer": dict(hp=90, mp=70, att=15, deF=10, spd=35, dex=25, vit=15, wis=10,
                    growth=["dex", "att", "spd", "vit", "dex"]),
    "warrior": dict(hp=130, mp=50, att=15, deF=25, spd=20, dex=15, vit=25, wis=5,
                     growth=["deF", "vit", "att", "deF", "spd"]),
    "priest": dict(hp=100, mp=120, att=5, deF=10, spd=25, dex=10, vit=15, wis=35,
                    growth=["wis", "vit", "wis", "deF", "dex"]),
    "rogue": dict(hp=85, mp=60, att=12, deF=8, spd=40, dex=30, vit=12, wis=8,
                   growth=["dex", "spd", "att", "dex", "vit"]),
    "necromancer": dict(hp=95, mp=110, att=8, deF=6, spd=22, dex=12, vit=12, wis=32,
                          growth=["wis", "att", "wis", "vit", "dex"]),
    "paladin": dict(hp=140, mp=80, att=10, deF=22, spd=18, dex=12, vit=22, wis=18,
                     growth=["deF", "vit", "wis", "deF", "vit"]),
    "assassin": dict(hp=80, mp=65, att=14, deF=6, spd=38, dex=32, vit=10, wis=8,
                       growth=["dex", "att", "dex", "spd", "vit"]),
}

CLASS_DESC = {
    "wizard": "Glass cannon. High WIS -> fast MP regen for spammable magic missiles.",
    "archer": "Nimble skirmisher. High DEX -> fastest attack speed, hit and run.",
    "warrior": "Front line tank. High DEF/VIT -> soaks hits, mediocre damage.",
    "priest": "Support caster. Wide WIS pool, staff attacks heal allies on hit.",
    "rogue": "Fast striker. Very high DEX/SPD, hit-and-run melee.",
    "necromancer": "DoT caster. Huge WIS pool, bolts meant to wear enemies down.",
    "paladin": "Tanky support. High DEF/VIT, mace hits heal on contact.",
    "assassin": "Burst striker. Highest DEX in the game, punishes overextension.",
}

# per-class level-up growth (see Player.gain_xp) - HP/MP keyed off the same
# Heavy/Light/Robe archetype grouping items.CLASS_ARMOR_ARCHETYPE already uses
# for armor drops, so a tanky class is ACTUALLY tankier by level 20, not an
# identical curve to a glass-cannon one. (min, max) inclusive, rolled fresh
# every level.
HP_GROWTH_BY_ARCHETYPE = {"heavy": (16, 22), "light": (12, 17), "robe": (9, 13)}
MP_GROWTH_BY_ARCHETYPE = {"heavy": (4, 7), "light": (5, 8), "robe": (7, 11)}
SIGNATURE_STAT_GROWTH = (1, 3)  # a class's own emphasized stats (CLASS_BASE's `growth` list)
OTHER_STAT_GROWTH = (0, 1)      # every other stat still ticks up a little, just less


class Player:
    def __init__(self, cls_name: str, name: str = "Player", pid: str = "local"):
        self.cls_name = cls_name
        self.name = name
        self.pid = pid  # network identity in co-op; "local" for single-player
        b = CLASS_BASE[cls_name]
        self.level = 1
        self.xp = 0
        self.hp_max = b["hp"]
        self.mp_max = b["mp"]
        self.hp = self.hp_max
        self.mp = self.mp_max
        self.att, self.deF, self.spd, self.dex, self.vit, self.wis = (
            b["att"], b["deF"], b["spd"], b["dex"], b["vit"], b["wis"])
        self._growth_cycle = b["growth"]

        self.pos = pygame.Vector2(0, 0)
        self.radius = 12
        self.facing = pygame.Vector2(0, 1)
        self._fire_cd = 0.0
        self._hit_flash = 0.0
        self._regen_acc = 0.0

        self.weapon = make_starter_weapon(cls_name)
        self.armor = None
        self.ring = None
        self.ability = make_starter_ability(cls_name)
        self.ability_cd = 0.0
        self.haste_time = 0.0  # remaining seconds of a "haste"-effect ability buff
        self.root_time = 0.0   # remaining seconds slowed by a boss root pulse (see the Thorn Warden)
        self.shield_hp = 0.0   # remaining absorb from a "shield"-effect ability
        self.shield_time = 0.0  # remaining seconds the shield lasts before decaying
        self.pet = None  # a hatched Pet, or None - see items.PET_KINDS / hatch_egg()
        self.backpack = []  # up to 8 loose items
        self.backpack_size = 8
        self.alive = True
        self.kills = 0
        self.spawn_time = 0.0
        # e.g. "the Bloodied" - NOT loaded from disk here (this constructor runs on every
        # network snapshot reconstruction too, at 20-30Hz; a file read per tick per player
        # would be a real perf regression). Real gameplay entry points (server join/respawn,
        # single-player start_run) call load_title() explicitly instead; from_full_state/
        # from_net_state just take the already-computed title off the wire.
        self.title = ""
        self.fish_cd = 0.0
        self.fishing_state = None  # {"phase": "casting"|"biting", "timer": float} or None
        self.potions_used = {k: 0 for k in STAT_KEYS}  # permanent stat potions drunk so far, per
        # stat - see use_potion()/PERMANENT_POTION_CAP (total across all 6, freely allocated)
        self.temp_buffs = {}  # {stat_key: (amount, seconds_remaining)} - see use_potion()/total_stat()/
        # net_update() (ticks these down every frame, same as haste_time/shield_time/root_time)

    def load_title(self):
        """Reads this player's unlocked achievements from disk and sets .title -
        call once at real spawn points (join/respawn/start_run), never per-tick."""
        self.title = achievements.title_for(achievements.load(self.name))

    # ---------------------------------------------------------- stat total --
    def total_stat(self, key):
        val = getattr(self, key)
        for it in (self.armor, self.ring, self.ability):
            if it:
                val += it.stat_bonus.get(key, 0)
        if key in self.temp_buffs:
            val += self.temp_buffs[key][0]
        return val

    HASTE_MULT = 1.4  # "haste"-effect abilities (Warrior/Rogue/Assassin) speed+attack-speed boost
    ROOT_MULT = 0.35  # a boss root pulse overrides haste - crowd control beats a buff

    def speed(self):
        mult = self.ROOT_MULT if self.root_time > 0 else self.HASTE_MULT if self.haste_time > 0 else 1.0
        return C.speed_tiles_per_sec(self.total_stat("spd")) * C.TILE * mult

    def atk_interval(self):
        mult = self.HASTE_MULT if self.haste_time > 0 else 1.0
        return 1.0 / max(0.5, C.attacks_per_sec(self.total_stat("dex")) * mult)

    def gain_xp(self, amount):
        if self.level >= LEVEL_CAP:
            return
        self.xp += amount
        while self.level < LEVEL_CAP and self.xp >= C.xp_to_next(self.level):
            self.xp -= C.xp_to_next(self.level)
            self.level += 1
            # Per-class growth (was a flat +14 hp/+10 mp/+4-to-one-rotating-stat for
            # EVERY class): HP/MP now scale off this project's own already-established
            # Heavy/Light/Robe armor archetype (items.CLASS_ARMOR_ARCHETYPE - the same
            # grouping armor drops already use), so a tanky Warrior really does end up
            # meaningfully tankier by level 20 than a glass-cannon Wizard, not just a
            # reskinned copy of the same growth curve. Every one of the 6 core stats
            # now rolls a small random amount EVERY level (not just one rotating stat
            # per level) - a class's own "signature" stats (CLASS_BASE's `growth` list)
            # roll a bigger range than its non-signature ones.
            archetype = CLASS_ARMOR_ARCHETYPE.get(self.cls_name, "light")
            self.hp_max += random.randint(*HP_GROWTH_BY_ARCHETYPE[archetype])
            self.mp_max += random.randint(*MP_GROWTH_BY_ARCHETYPE[archetype])
            self.hp = self.hp_max
            self.mp = self.mp_max
            signature_stats = set(self._growth_cycle)
            for stat_key in ("att", "deF", "spd", "dex", "vit", "wis"):
                lo, hi = SIGNATURE_STAT_GROWTH if stat_key in signature_stats else OTHER_STAT_GROWTH
                setattr(self, stat_key, getattr(self, stat_key) + random.randint(lo, hi))
            if self.level in (10, 20):
                changed, title = achievements.unlock(self.name, "veteran" if self.level == 10 else "legend")
                if changed:
                    self.title = title

    def equip(self, item, backpack_idx=None):
        """backpack_idx: where the previously-equipped item (if any) should land back in
        the backpack, so a drag-swap doesn't reshuffle the whole bag - defaults to the end."""
        slot_map = {SLOT_WEAPON: "weapon", SLOT_ARMOR: "armor", SLOT_RING: "ring", SLOT_ABILITY: "ability"}
        attr = slot_map.get(item.slot)
        if attr is None:
            return False
        old = getattr(self, attr)
        setattr(self, attr, item)
        if old is not None:
            if backpack_idx is not None and backpack_idx <= len(self.backpack):
                self.backpack.insert(backpack_idx, old)
            else:
                self.backpack.append(old)
        return True

    def unequip(self, slot_type):
        """Drags an equipped item back into the backpack, if there's room."""
        if len(self.backpack) >= self.backpack_size:
            return False
        it = getattr(self, slot_type, None)
        if it is None:
            return False
        setattr(self, slot_type, None)
        self.backpack.append(it)
        return True

    def swap_backpack(self, i, j):
        """Reorders two backpack slots (drag-and-drop within the bag)."""
        if 0 <= i < len(self.backpack) and 0 <= j < len(self.backpack) and i != j:
            self.backpack[i], self.backpack[j] = self.backpack[j], self.backpack[i]
            return True
        return False

    def try_pickup(self, item):
        if len(self.backpack) >= self.backpack_size:
            return False
        self.backpack.append(item)
        return True

    def use_potion(self, index):
        if 0 <= index < len(self.backpack):
            it = self.backpack[index]
            if it.slot == "consumable":
                if sum(self.potions_used.values()) >= PERMANENT_POTION_CAP:
                    return False  # cap reached - caller (main.py/server.py) shows a rejection message
                for k, v in it.stat_bonus.items():
                    setattr(self, k, getattr(self, k) + v)
                    self.potions_used[k] = self.potions_used.get(k, 0) + v
                self.backpack.pop(index)
                return True
            if it.slot == SLOT_TEMP_POTION:
                for k, v in it.stat_bonus.items():
                    self.temp_buffs[k] = (v, TEMP_POTION_DURATION)
                self.backpack.pop(index)
                return True
            if it.slot == SLOT_EGG:
                self.pet = Pet(it.pet_kind, self.pos)
                self.backpack.pop(index)
                changed, title = achievements.unlock(self.name, "egg_parent")
                if changed:
                    self.title = title
                return True
        return False

    def feed_pet(self, index):
        """Feeds the backpack item at `index` to the hatched pet for XP (see
        items.PET_LEVEL_XP_STEP/PET_FEED_XP_PER_TIER), split evenly across
        all 3 independent ability slots, each capped at the pet's rarity-
        derived max level - eggs aren't fed (they're hatched via use_potion).
        Consumes the item and returns True on success, mirroring the other
        backpack-consumption methods (use_potion/use_shard)."""
        if self.pet is None or not (0 <= index < len(self.backpack)):
            return False
        it = self.backpack[index]
        if it.slot == SLOT_EGG:
            return False
        total_xp = max(1, it.tier or 1) * PET_FEED_XP_PER_TIER
        per_ability = total_xp / len(PET_ABILITY_KEYS)
        max_level = PET_RARITY_MAX_LEVEL[self.pet.rarity]
        for st in self.pet.abilities.values():
            if st["level"] >= max_level:
                continue
            st["xp"] += per_ability
            while st["xp"] >= PET_LEVEL_XP_STEP and st["level"] < max_level:
                st["xp"] -= PET_LEVEL_XP_STEP
                st["level"] += 1
            if st["level"] >= max_level:
                st["xp"] = 0.0
        self.backpack.pop(index)
        return True

    def use_shard(self, index):
        """Returns the Dungeon Shard's theme key (see items.make_dungeon_shard)
        if the backpack slot at `index` holds one, removing it - else None.
        The CALLER (main.py/server.py) actually spawns the Portal, since
        Player has no reference to the active RealmSim."""
        if 0 <= index < len(self.backpack):
            it = self.backpack[index]
            if it.slot == SLOT_SHARD:
                self.backpack.pop(index)
                return it.shard_theme
        return None

    def update(self, dt, keys, world_bounds, is_solid=None, speed_mult_fn=None, cam_angle=0.0):
        """cam_angle: the camera's current Q/E rotation (game.world.Camera.angle,
        degrees) - WASD/arrows are always meant as SCREEN-relative ("W" = up on
        screen), so the raw key-derived vector has to be rotated by the same
        amount the view itself is rotated, or moving "up" while rotated actually
        walks you sideways in world space (RotMG rotates the map, not the intent
        of your movement keys). keys=None means "no movement input" (e.g. while
        typing in chat) WITHOUT pausing the rest of the sim - regen/status timers
        etc. still tick via the net_update(dt, zero-vector, ...) call below."""
        move = pygame.Vector2(0, 0)
        if keys is not None:
            if keys[pygame.K_w] or keys[pygame.K_UP]:
                move.y -= 1
            if keys[pygame.K_s] or keys[pygame.K_DOWN]:
                move.y += 1
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                move.x -= 1
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                move.x += 1
        if cam_angle and move.length_squared() > 0:
            move = move.rotate(cam_angle)
        self.net_update(dt, move, world_bounds, is_solid, speed_mult_fn)

    def net_update(self, dt, move, world_bounds, is_solid=None, speed_mult_fn=None):
        """
        Same movement/regen tick as update(), but driven by a raw move
        vector instead of a pygame key map - this is what the co-op server
        calls for each connected player (whose "keys" arrive over the
        network as a direction vector, not a live pygame key state).
        speed_mult_fn(x, y): optional terrain speed multiplier (e.g. water wading
        at 0.8x) - looked up from the player's CURRENT tile, same as real RotMG
        terrain-speed tiles.
        """
        if move.length_squared() > 0:
            move = pygame.Vector2(move).normalize()
            self.facing = move
            mult = speed_mult_fn(self.pos.x, self.pos.y) if speed_mult_fn else 1.0
            delta = move * self.speed() * mult * dt
            if is_solid is None:
                self.pos += delta
            else:
                # resolve per-axis so sliding along a wall still works
                new_x = self.pos.x + delta.x
                if not is_solid(new_x, self.pos.y):
                    self.pos.x = new_x
                new_y = self.pos.y + delta.y
                if not is_solid(self.pos.x, new_y):
                    self.pos.y = new_y

        self.pos.x = max(world_bounds[0], min(world_bounds[2], self.pos.x))
        self.pos.y = max(world_bounds[1], min(world_bounds[3], self.pos.y))

        self._fire_cd = max(0.0, self._fire_cd - dt)
        self._hit_flash = max(0.0, self._hit_flash - dt)
        self.ability_cd = max(0.0, self.ability_cd - dt)
        self.haste_time = max(0.0, self.haste_time - dt)
        self.root_time = max(0.0, self.root_time - dt)
        if self.shield_time > 0:
            self.shield_time = max(0.0, self.shield_time - dt)
            if self.shield_time <= 0:
                self.shield_hp = 0.0
        self.fish_cd = max(0.0, self.fish_cd - dt)
        for k in list(self.temp_buffs.keys()):
            amount, remaining = self.temp_buffs[k]
            remaining -= dt
            if remaining <= 0:
                del self.temp_buffs[k]
            else:
                self.temp_buffs[k] = (amount, remaining)

        # VIT / WIS regen, real RotMG formulas
        self._regen_acc += dt
        if self._regen_acc >= 1.0:
            self._regen_acc -= 1.0
            self.hp = min(self.hp_max, self.hp + C.hp_regen_per_sec(self.total_stat("vit")))
            self.mp = min(self.mp_max, self.mp + C.mp_regen_per_sec(self.total_stat("wis")))

    def can_fire(self):
        return self._fire_cd <= 0.0

    def register_fire(self):
        self._fire_cd = self.atk_interval()

    def take_damage(self, dmg):
        real = C.apply_defense(dmg, self.total_stat("deF"))
        if self.shield_hp > 0:
            absorbed = min(self.shield_hp, real)
            self.shield_hp -= absorbed
            real -= absorbed
        self.hp -= real
        self._hit_flash = 0.15
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return real

    def draw(self, surf, cam):
        img = sprites.player_sprite(self.cls_name)
        r = img.get_rect(center=cam(self.pos))
        surf.blit(img, r)
        if self._hit_flash > 0:
            flash = img.copy()
            flash.fill((255, 60, 60, 120), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(flash, r)
        if self.shield_hp > 0:
            pulse = 1.0 + 0.08 * math.sin(pygame.time.get_ticks() / 120.0)
            pygame.draw.circle(surf, (140, 210, 255), r.center, int(r.width * 0.62 * pulse), 2)
        if self.pet is not None:
            self.pet.draw(surf, cam)

    def net_state(self):
        """Render-relevant snapshot a co-op client needs of a REMOTE player - includes
        equipped items and total stats so a UI can show a hover tooltip about them."""
        return dict(
            pid=self.pid, name=self.name, cls=self.cls_name,
            x=round(self.pos.x, 1), y=round(self.pos.y, 1),
            hp=round(self.hp, 1), hp_max=self.hp_max, level=self.level, alive=self.alive,
            weapon=self.weapon.to_json() if self.weapon else None,
            armor=self.armor.to_json() if self.armor else None,
            ring=self.ring.to_json() if self.ring else None,
            ability=self.ability.to_json() if self.ability else None,
            att=self.total_stat("att"), deF=self.total_stat("deF"), spd=self.total_stat("spd"),
            dex=self.total_stat("dex"), vit=self.total_stat("vit"), wis=self.total_stat("wis"),
            shield_hp=round(self.shield_hp, 1),
            pet=self.pet.net_state() if self.pet else None,
            title=self.title,
        )

    def full_state(self):
        """Full snapshot a co-op client needs of its OWN player (HUD/inventory/vault)."""
        return dict(
            pid=self.pid, name=self.name, cls=self.cls_name,
            level=self.level, xp=self.xp, kills=self.kills,
            hp=self.hp, hp_max=self.hp_max, mp=self.mp, mp_max=self.mp_max,
            x=self.pos.x, y=self.pos.y, alive=self.alive,
            att=self.att, deF=self.deF, spd=self.spd, dex=self.dex, vit=self.vit, wis=self.wis,
            weapon=self.weapon.to_json() if self.weapon else None,
            armor=self.armor.to_json() if self.armor else None,
            ring=self.ring.to_json() if self.ring else None,
            ability=self.ability.to_json() if self.ability else None,
            backpack=[it.to_json() for it in self.backpack],
            shield_hp=round(self.shield_hp, 1),
            pet=self.pet.net_state() if self.pet else None,
            title=self.title,
            potions_used=dict(self.potions_used),
            temp_buffs={k: list(v) for k, v in self.temp_buffs.items()},
        )

    @staticmethod
    def from_full_state(d):
        """Reconstruct a real (client-side, display-only) Player from full_state() JSON,
        so the existing ui.py drawing code works unchanged on co-op snapshots."""
        p = Player(d["cls"], name=d["name"], pid=d["pid"])
        p.level, p.xp, p.kills = d["level"], d["xp"], d["kills"]
        p.hp, p.hp_max, p.mp, p.mp_max = d["hp"], d["hp_max"], d["mp"], d["mp_max"]
        p.pos = pygame.Vector2(d["x"], d["y"])
        p.alive = d["alive"]
        p.att, p.deF, p.spd, p.dex, p.vit, p.wis = (
            d["att"], d["deF"], d["spd"], d["dex"], d["vit"], d["wis"])
        p.weapon = Item.from_json(d["weapon"]) if d["weapon"] else None
        p.armor = Item.from_json(d["armor"]) if d["armor"] else None
        p.ring = Item.from_json(d["ring"]) if d["ring"] else None
        p.ability = Item.from_json(d["ability"]) if d["ability"] else None
        p.backpack = [Item.from_json(j) for j in d["backpack"]]
        p.shield_hp = d.get("shield_hp", 0.0)
        p.pet = Pet.from_net_state(d["pet"]) if d.get("pet") else None
        p.title = d.get("title", "")
        p.potions_used = {**p.potions_used, **d.get("potions_used", {})}
        p.temp_buffs = {k: tuple(v) for k, v in d.get("temp_buffs", {}).items()}
        return p

    @staticmethod
    def from_net_state(d):
        """Reconstruct a display-only Player for a REMOTE co-op peer from net_state() JSON -
        enough for Player.draw(), a name/level tag, and a hover tooltip of their gear/stats."""
        p = Player(d["cls"], name=d["name"], pid=d["pid"])
        p.pos = pygame.Vector2(d["x"], d["y"])
        p.hp, p.hp_max, p.level, p.alive = d["hp"], d["hp_max"], d["level"], d["alive"]
        p.weapon = Item.from_json(d["weapon"]) if d.get("weapon") else None
        p.armor = Item.from_json(d["armor"]) if d.get("armor") else None
        p.ring = Item.from_json(d["ring"]) if d.get("ring") else None
        p.ability = Item.from_json(d["ability"]) if d.get("ability") else None
        p.shield_hp = d.get("shield_hp", 0.0)
        p.pet = Pet.from_net_state(d["pet"]) if d.get("pet") else None
        p.title = d.get("title", "")
        # IMPORTANT: this peer's base stats (p.att etc.) stay at fresh class defaults -
        # they're never synced, only the equipped items are. Calling .total_stat() on
        # a peer object silently gives a STALE value for anyone who has levelled up
        # (base-stat growth is missing). net_totals holds the sender's real, already-
        # correct total_stat() result - always read display values from here instead.
        p.net_totals = {k: d[k] for k in ("att", "deF", "spd", "dex", "vit", "wis") if k in d}
        return p


RANK_XP = {"trash": 8, "elite": 30, "boss": 250}

# aggro_range: how close a player must get before an idle enemy notices them.
# leash_range: how far from home an AGGRO'd enemy will chase before giving up
# and heading back - bosses have no leash (rank == "boss" is checked directly).
# HP values are scaled up from the original v0.2 numbers (~2.2x trash/elite, ~1.6x
# boss) to feel closer to real RotMG's Godlands HP pools - a trash mob dying in one
# hit or an elite folding in a second or two didn't feel like RotMG at all - while
# deliberately stopping well short of the real game's grindier late-game HP pools,
# since this is still meant to be testable/beatable in a single co-op session.
ENEMY_KINDS = {
    "imp": dict(kind="imp", rank="trash", hp=40, speed=70, pattern="aimed", dmg=(2, 5), radius=12,
                aggro_range=230, leash_range=380),
    "bat": dict(kind="bat", rank="trash", hp=31, speed=140, pattern="erratic", dmg=(1, 4), radius=10,
                aggro_range=260, leash_range=400),
    "ghost": dict(kind="ghost", rank="elite", hp=99, speed=55, pattern="spread", dmg=(3, 7), radius=13,
                  aggro_range=270, leash_range=450),
    "skeleton": dict(kind="skeleton", rank="elite", hp=132, speed=40, pattern="burst", dmg=(4, 8), radius=13,
                      aggro_range=250, leash_range=450),
    # biome-flavoured ecosystem mobs - one signature elite per zone besides the generic mix.
    # HP rehaul: base HP is now aligned to each biome's outer/inner difficulty tier (the
    # OLD numbers didn't - e.g. yeti, an OUTER/Tundra elite, used to be the 2nd-tankiest
    # elite in the whole game at 198 HP, tankier than several INNER-tier elites like harpy
    # at 106 - actively fighting the "easy at the edges, hard in the Godlands" gradient
    # instead of reinforcing it. Outer-tier signature elites now sit in a tighter 100-140
    # band; inner-tier ones in a wider 140-200 band - on TOP of (not instead of) the
    # existing distance-from-center difficulty_scale in _generate_lairs(), which still does
    # the actual per-lair scaling. Generic trash (goblin included - it's trash-ranked, not
    # an elite) and bosses are untouched, they were already correctly positioned.
    "goblin": dict(kind="goblin", rank="trash", hp=53, speed=95, pattern="aimed", dmg=(2, 6), radius=12,
                   aggro_range=220, leash_range=360),
    "scorpion": dict(kind="scorpion", rank="elite", hp=112, speed=65, pattern="burst", dmg=(4, 9), radius=13,
                      aggro_range=260, leash_range=420),
    "yeti": dict(kind="yeti", rank="elite", hp=138, speed=35, pattern="spread", dmg=(5, 10), radius=16,
                 aggro_range=280, leash_range=460),
    "troll": dict(kind="troll", rank="elite", hp=132, speed=45, pattern="aimed", dmg=(5, 11), radius=15,
                  aggro_range=250, leash_range=440),
    "harpy": dict(kind="harpy", rank="elite", hp=150, speed=120, pattern="erratic", dmg=(3, 8), radius=13,
                  aggro_range=290, leash_range=440),
    "salamander": dict(kind="salamander", rank="elite", hp=145, speed=55, pattern="spread", dmg=(4, 10), radius=14,
                        aggro_range=260, leash_range=430),
    # the four newest biomes (Jungle/Wasteland/Ice/Cave) each get their own signature mob too
    "panther": dict(kind="panther", rank="elite", hp=155, speed=130, pattern="erratic", dmg=(4, 9), radius=13,
                     aggro_range=300, leash_range=460),
    "ghoul": dict(kind="ghoul", rank="elite", hp=178, speed=35, pattern="aimed", dmg=(5, 10), radius=15,
                  aggro_range=240, leash_range=420),
    "frost_wraith": dict(kind="frost_wraith", rank="elite", hp=148, speed=50, pattern="spread", dmg=(4, 9),
                          radius=13, aggro_range=270, leash_range=440),
    "cave_lurker": dict(kind="cave_lurker", rank="elite", hp=142, speed=90, pattern="burst", dmg=(4, 10), radius=12,
                         aggro_range=340, leash_range=480),
    # a second signature mob per biome, each with one of the three newer bullet/
    # movement patterns (volley/spiral/charge) so every zone has real behavioural
    # variety, not just a recolored version of the same handful of patterns
    "thornling": dict(kind="thornling", rank="elite", hp=118, speed=50, pattern="spiral", dmg=(4, 9), radius=13,
                       aggro_range=260, leash_range=420),
    "dune_stalker": dict(kind="dune_stalker", rank="elite", hp=128, speed=70, pattern="charge", dmg=(5, 10), radius=13,
                          aggro_range=270, leash_range=440),
    "frost_sprite": dict(kind="frost_sprite", rank="elite", hp=102, speed=60, pattern="volley", dmg=(3, 8), radius=12,
                          aggro_range=270, leash_range=440),
    "bog_crawler": dict(kind="bog_crawler", rank="elite", hp=136, speed=40, pattern="spiral", dmg=(5, 10), radius=15,
                         aggro_range=250, leash_range=440),
    "cliff_strider": dict(kind="cliff_strider", rank="elite", hp=152, speed=90, pattern="charge", dmg=(4, 9),
                           radius=13, aggro_range=290, leash_range=440),
    "cinder_wisp": dict(kind="cinder_wisp", rank="elite", hp=145, speed=55, pattern="volley", dmg=(4, 9), radius=12,
                         aggro_range=260, leash_range=430),
    "vine_serpent": dict(kind="vine_serpent", rank="elite", hp=158, speed=75, pattern="spiral", dmg=(4, 9), radius=13,
                          aggro_range=300, leash_range=460),
    "husk_wanderer": dict(kind="husk_wanderer", rank="elite", hp=162, speed=45, pattern="charge", dmg=(5, 11),
                           radius=14, aggro_range=240, leash_range=420),
    "glacier_shard": dict(kind="glacier_shard", rank="elite", hp=148, speed=50, pattern="volley", dmg=(4, 9),
                           radius=12, aggro_range=270, leash_range=440),
    "deep_stalker": dict(kind="deep_stalker", rank="elite", hp=150, speed=85, pattern="spiral", dmg=(4, 10),
                          radius=12, aggro_range=340, leash_range=480),
    # dungeon bosses: a real roster instead of one reskin, each with its own feel
    "boss": dict(kind="boss", rank="boss", hp=1440, speed=50, pattern="boss", dmg=(6, 14), radius=26,
                 aggro_range=99999, leash_range=99999),
    "frost_monarch": dict(kind="frost_monarch", rank="boss", hp=1600, speed=42, pattern="boss", dmg=(7, 15),
                           radius=26, aggro_range=99999, leash_range=99999),
    "ash_behemoth": dict(kind="ash_behemoth", rank="boss", hp=1300, speed=55, pattern="boss", dmg=(8, 17),
                          radius=26, aggro_range=99999, leash_range=99999),
    "void_reaper": dict(kind="void_reaper", rank="boss", hp=1500, speed=60, pattern="boss", dmg=(6, 13),
                         radius=26, aggro_range=99999, leash_range=99999),
    # two genuinely different bosses, not palette reskins of the spinning-ring
    # "boss" pattern: the Thorn Warden periodically roots you in place with an
    # expanding thorn pulse, the Sand Wyrm spends most of the fight untouchable
    # underground and only takes damage during its brief, dangerous surface phase.
    "thorn_warden": dict(kind="thorn_warden", rank="boss", hp=1700, speed=38, pattern="boss_root", dmg=(6, 13),
                          radius=27, aggro_range=99999, leash_range=99999),
    "sand_wyrm": dict(kind="sand_wyrm", rank="boss", hp=1350, speed=65, pattern="boss_burrow", dmg=(8, 16),
                       radius=27, aggro_range=99999, leash_range=99999),
    # neutral (always-passive) ambient wildlife - never aggros, never deals contact
    # damage (dmg=(0,0) makes that harmless even though the generic contact-damage
    # check isn't itself aggro-gated). Kept on rank "trash" rather than a new rank
    # so RANK_XP/roll_loot need no new branches (irrelevant now anyway - see below) -
    # see the `neutral` flag check in Enemy.update() below.
    # unshootable=True (added alongside the 4 new wildlife kinds below, for
    # consistency - "peaceful animals you can't shoot" reads as one category, not
    # "some animals are shootable, some aren't") - bullets pass straight through
    # (RealmSim._resolve_bullet_hits), and they flee a nearby shot instead of just
    # standing there (RealmSim._trigger_wildlife_flee / Enemy.update's flee_time
    # branch) - real "run away if you shoot near them" behavior, not just passive.
    "forest_hare": dict(kind="forest_hare", rank="trash", hp=20, speed=100, pattern="aimed", dmg=(0, 0),
                         radius=9, aggro_range=0, leash_range=0, neutral=True, unshootable=True),
    "cave_moth": dict(kind="cave_moth", rank="trash", hp=18, speed=40, pattern="aimed", dmg=(0, 0),
                       radius=9, aggro_range=0, leash_range=0, neutral=True, unshootable=True),
    "songbird": dict(kind="songbird", rank="trash", hp=15, speed=130, pattern="aimed", dmg=(0, 0),
                      radius=8, aggro_range=0, leash_range=0, neutral=True, unshootable=True),
    "deer": dict(kind="deer", rank="trash", hp=30, speed=110, pattern="aimed", dmg=(0, 0),
                 radius=13, aggro_range=0, leash_range=0, neutral=True, unshootable=True),
    "desert_lizard": dict(kind="desert_lizard", rank="trash", hp=16, speed=90, pattern="aimed", dmg=(0, 0),
                           radius=8, aggro_range=0, leash_range=0, neutral=True, unshootable=True),
    "marsh_heron": dict(kind="marsh_heron", rank="trash", hp=22, speed=95, pattern="aimed", dmg=(0, 0),
                         radius=10, aggro_range=0, leash_range=0, neutral=True, unshootable=True),
    # "The Reforging" storyline - island flare/song guardians (see
    # realm_sim.ISLAND_THEMES/_tick_island_events). Deliberately NOT added to
    # any BIOME_LAIR_KIND_SETS roster - these only ever spawn via an island
    # event, never randomly in the wild. Shard pool (charged-rubble/echo-
    # construct, land-shattered theme) and choir pool (coral/pearl/drowned-
    # temple theme) each get 4 trash + 5 regular elites + 1 tougher "anchor"
    # elite guaranteed in every wave (cinder_warden/choir_warden).
    "ember_wisp": dict(kind="ember_wisp", rank="trash", hp=28, speed=110, pattern="erratic", dmg=(2, 5),
                        radius=9, aggro_range=220, leash_range=380),
    "fury_shard": dict(kind="fury_shard", rank="trash", hp=35, speed=60, pattern="burst", dmg=(3, 6),
                        radius=11, aggro_range=200, leash_range=360),
    "rubble_crawler": dict(kind="rubble_crawler", rank="trash", hp=45, speed=50, pattern="aimed", dmg=(2, 6),
                            radius=12, aggro_range=210, leash_range=370),
    "spite_spirit": dict(kind="spite_spirit", rank="trash", hp=32, speed=90, pattern="spread", dmg=(2, 5),
                          radius=10, aggro_range=230, leash_range=390),
    "shard_sentinel": dict(kind="shard_sentinel", rank="elite", hp=150, speed=45, pattern="burst", dmg=(5, 10),
                            radius=15, aggro_range=270, leash_range=440),
    "echo_knight": dict(kind="echo_knight", rank="elite", hp=165, speed=55, pattern="aimed", dmg=(5, 11),
                         radius=14, aggro_range=260, leash_range=430),
    "shattered_golem": dict(kind="shattered_golem", rank="elite", hp=185, speed=35, pattern="spread", dmg=(6, 12),
                             radius=16, aggro_range=250, leash_range=420),
    "fracture_hound": dict(kind="fracture_hound", rank="elite", hp=140, speed=100, pattern="charge", dmg=(4, 9),
                            radius=13, aggro_range=290, leash_range=460),
    "stone_revenant": dict(kind="stone_revenant", rank="elite", hp=158, speed=50, pattern="spiral", dmg=(5, 10),
                            radius=14, aggro_range=260, leash_range=430),
    "cinder_warden": dict(kind="cinder_warden", rank="elite", hp=210, speed=48, pattern="volley", dmg=(6, 13),
                           radius=16, aggro_range=280, leash_range=450),
    "tide_wisp": dict(kind="tide_wisp", rank="trash", hp=26, speed=100, pattern="erratic", dmg=(2, 5),
                       radius=9, aggro_range=220, leash_range=380),
    "pearl_acolyte": dict(kind="pearl_acolyte", rank="trash", hp=34, speed=65, pattern="spread", dmg=(2, 5),
                           radius=10, aggro_range=210, leash_range=370),
    "brine_crawler": dict(kind="brine_crawler", rank="trash", hp=42, speed=55, pattern="burst", dmg=(3, 6),
                           radius=12, aggro_range=200, leash_range=360),
    "abyssal_chorister": dict(kind="abyssal_chorister", rank="trash", hp=30, speed=85, pattern="aimed", dmg=(2, 5),
                               radius=10, aggro_range=230, leash_range=390),
    "coral_sentinel": dict(kind="coral_sentinel", rank="elite", hp=150, speed=42, pattern="spread", dmg=(5, 10),
                            radius=15, aggro_range=260, leash_range=430),
    "drowned_custodian": dict(kind="drowned_custodian", rank="elite", hp=170, speed=48, pattern="burst", dmg=(5, 11),
                               radius=15, aggro_range=270, leash_range=440),
    "kelp_stalker": dict(kind="kelp_stalker", rank="elite", hp=145, speed=75, pattern="spiral", dmg=(4, 9),
                          radius=13, aggro_range=280, leash_range=450),
    "shellback_guardian": dict(kind="shellback_guardian", rank="elite", hp=190, speed=32, pattern="aimed", dmg=(6, 12),
                                radius=17, aggro_range=240, leash_range=410),
    "siren_wraith": dict(kind="siren_wraith", rank="elite", hp=138, speed=90, pattern="volley", dmg=(4, 9),
                          radius=13, aggro_range=300, leash_range=460),
    "choir_warden": dict(kind="choir_warden", rank="elite", hp=215, speed=45, pattern="charge", dmg=(6, 13),
                          radius=16, aggro_range=270, leash_range=440),
    # a stationary, damageable dungeon decoration - see realm_sim.SECRET_QUEST_KINDS'
    # "kill_totems" quest. speed=0 is safe (movement code is pure multiplication,
    # nothing divides by speed); neutral=True reuses the existing never-aggroes/
    # harmless-contact behavior so it really is "just decoration you can damage."
    "totem": dict(kind="totem", rank="trash", hp=60, speed=0, pattern="aimed", dmg=(0, 0),
                  radius=14, aggro_range=0, leash_range=0, neutral=True),
}

# ---------------------------------------------------- difficulty rework --
# Moderate difficulty bump (2026-09-21): enemies previously had NO defense/
# mitigation at all against player damage (a raw dmg -= subtraction), while
# players already had a real deF-based mitigation formula (see
# constants.apply_defense). Mirrors that same formula onto enemies instead of
# inventing a second one - `deF` is derived deterministically from each
# kind's own `hp` (not randomly rolled, so the roster stays reproducible
# across runs/tests) via a per-rank ratio tuned so trash/elite/boss each land
# in a sensible absolute range (trash ~0-6, elite ~8-16, boss ~22-38,
# roughly mirroring the player CLASS_BASE.deF spread of 5-25 but topping out
# higher for bosses). ENEMY_DEFENSE_FLOOR is the per-rank floor_frac passed
# to apply_defense - "a hit can never be trivialized below this much of the
# raw roll," bigger for tougher ranks ("right for each mob and its
# difficulty"). ENEMY_DMG_MULT is a flat ~22% damage bump across the whole
# roster - same sizing/honesty caveat as this project's earlier ability-
# damage rebalance pass (no exact wiki numbers, grounded in "needs to feel
# harder" + internal consistency, not a wiki-verified pass).
ENEMY_DEFENSE_RATIO_BY_RANK = {"trash": 0.05, "elite": 0.07, "boss": 0.006}
ENEMY_DEFENSE_FLOOR = {"trash": 0.12, "elite": 0.15, "boss": 0.2}
ENEMY_DMG_MULT = 1.22
for _ek_kind, _ek_d in ENEMY_KINDS.items():
    _ek_lo, _ek_hi = _ek_d["dmg"]
    _ek_d["dmg"] = (max(0, round(_ek_lo * ENEMY_DMG_MULT)), max(0, round(_ek_hi * ENEMY_DMG_MULT)))
    _ek_d["deF"] = round(_ek_d["hp"] * ENEMY_DEFENSE_RATIO_BY_RANK.get(_ek_d["rank"], 0.05))

BOSS_KINDS = ["boss", "frost_monarch", "ash_behemoth", "void_reaper", "thorn_warden", "sand_wyrm"]

# reserved-pocket second-phase boss variants (see realm_sim.py's boss-death portal
# choreography) - deliberately NOT added to BOSS_KINDS' own random-selection pool
# (only ever constructed explicitly as f"{kind}_phase2"). Genuinely harder, not a
# reskin: more HP/damage AND a real mechanical wrinkle (fires noticeably faster -
# see Enemy.fire_rate_mult below), on top of a darker/redder look (sprites.py).
PHASE2_HP_MULT = 1.75  # bumped from 1.6 alongside the moderate difficulty rework above -
# "meaner and more dangerous" per the user's specific phase-2 ask
PHASE2_DMG_MULT = 1.4  # bumped from 1.3, same reasoning
PHASE2_FIRE_RATE_MULT = 0.6
for _boss_kind in list(BOSS_KINDS):
    _base = ENEMY_KINDS[_boss_kind]
    _lo, _hi = _base["dmg"]
    ENEMY_KINDS[f"{_boss_kind}_phase2"] = dict(
        _base, kind=f"{_boss_kind}_phase2", hp=int(_base["hp"] * PHASE2_HP_MULT),
        dmg=(int(_lo * PHASE2_DMG_MULT), int(_hi * PHASE2_DMG_MULT)), fire_rate_mult=PHASE2_FIRE_RATE_MULT,
        # tankier defense too, using the same HP multiplier as a reasonable proxy
        deF=round(_base.get("deF", 0) * PHASE2_HP_MULT),
    )

# Random flavor lines shown as a speech bubble above an aggro'd mob (same mechanism
# as NexusBot's speech/speech_age) - a small pool per sound family (see game.audio.
# sound_family) rather than per-kind, matching the same "manageable scope" call as
# the sound families themselves. Text only, no TTS/audio - this is the only existing
# analog for "mobs say things" in the codebase (NexusBot), just extended to Enemy.
MOB_FLAVOR_LINES = {
    "beast": ["Rrrgh!", "*snarls*", "You shouldn't be here.", "*bares teeth*"],
    "undead": ["...leave...", "*rattles*", "join us...", "*hollow moan*"],
    "elemental": ["Burn!", "*crackles*", "Feel the heat!", "*hisses*"],
    "construct": ["Who dares?!", "None shall pass!", "You will fall.", "*ancient rumbling*"],
}
# peaceful ambient wildlife (see ENEMY_KINDS' neutral+speed>0 mobs) gets its own
# genuinely non-threatening flavor lines instead of MOB_FLAVOR_LINES' combat-mob
# ones ("Rrrgh!"/"bares teeth" reads wrong coming from a fleeing deer) - see
# Enemy._say_flavor_line()
WILDLIFE_FLAVOR_LINES = ["*chirps*", "*rustles in the grass*", "*sniffs the air*",
                          "*flicks its tail*", "*a soft trill*"]


# ------------------------------------------------------- per-mob loot difficulty --
# How much tougher an individual mob is than others of the SAME rank - items.roll_loot()
# uses this to nudge which end of its rank's tier band a kill rolls toward, so e.g. the
# tanky troll (elite) noticeably out-drops the squishier frost_sprite (also elite)
# instead of both drawing from the identical range. Not meant to be a physically exact
# DPS model - just a simple, explainable composite of the three things that make a mob
# dangerous to fight: raw HP (how much punishment it takes to kill it), average per-hit
# damage MULTIPLIED by how aggressively its bullet pattern fires (a mob that both hits
# harder AND shoots more often is doubly dangerous, not just additively so - see
# PATTERN_DANGER, weighted by roughly how many bullets/sec each pattern in _shoot()
# actually puts out), and speed as a smaller factor (harder to kite away from, and
# "charge"/erratic mobs already get credit for their pattern instead).
PATTERN_DANGER = {
    "erratic": 0.75, "aimed": 1.0, "volley": 1.15, "spread": 1.3, "charge": 1.4,
    "spiral": 1.5, "burst": 1.6, "boss_burrow": 1.7, "boss": 2.2, "boss_root": 2.4,
}


def _mob_difficulty_score(d):
    avg_dmg = sum(d["dmg"]) / 2
    pattern_mult = PATTERN_DANGER.get(d["pattern"], 1.0)
    return d["hp"] * 0.5 + (avg_dmg * pattern_mult) * 6.0 + d["speed"] * 0.3


_DIFFICULTY_SCORE_BY_KIND = {k: _mob_difficulty_score(d) for k, d in ENEMY_KINDS.items()}
_DIFFICULTY_RANGE_BY_RANK = {}
for _kind, _d in ENEMY_KINDS.items():
    if _kind.endswith("_phase2"):
        continue  # excluded from ranking - see difficulty_fraction()'s early-return for these;
        # including them would inflate the "boss" rank's max score and silently nerf every
        # ORDINARY boss's difficulty_fraction (and therefore its loot-roll tier), which is
        # exactly the kind of side effect a rare, dungeon-only variant should never cause.
    _score = _DIFFICULTY_SCORE_BY_KIND[_kind]
    _lo, _hi = _DIFFICULTY_RANGE_BY_RANK.get(_d["rank"], (_score, _score))
    _DIFFICULTY_RANGE_BY_RANK[_d["rank"]] = (min(_lo, _score), max(_hi, _score))


def difficulty_fraction(kind):
    """0.0 (weakest of its rank) .. 1.0 (strongest of its rank), by raw difficulty
    score. A rank with every member tied (or a single member) returns 0.5 for all
    of them - a neutral midpoint, not an arbitrary top/bottom pick. A "_phase2"
    variant always returns 1.0 (top of its rank's loot band) rather than
    participating in the ranking itself - see the exclusion above."""
    if kind.endswith("_phase2"):
        return 1.0
    d = ENEMY_KINDS[kind]
    lo, hi = _DIFFICULTY_RANGE_BY_RANK[d["rank"]]
    if hi <= lo:
        return 0.5
    return (_DIFFICULTY_SCORE_BY_KIND[kind] - lo) / (hi - lo)


class Enemy:
    MIN_REBARK_INTERVAL = 20.0  # seconds - a hard per-mob floor between flavor lines/idle
                                 # barks, on top of the %/sec roll (see update())

    def __init__(self, kind, pos, level_scale=1.0, home_pos=None):
        d = ENEMY_KINDS[kind]
        self.kind = d["kind"]
        self.rank = d["rank"]
        self.difficulty_fraction = difficulty_fraction(kind)
        self.pos = pygame.Vector2(pos)
        self.home_pos = pygame.Vector2(home_pos) if home_pos is not None else pygame.Vector2(pos)
        self.hp_max = int(d["hp"] * level_scale)
        self.hp = self.hp_max
        self.speed = d["speed"]
        self.pattern = d["pattern"]
        self.dmg = d["dmg"]
        self.deF = d.get("deF", 0)
        self._last_hit_damage = 0  # real post-mitigation amount from the most recent take_damage() call
        self.radius = d["radius"]
        self.aggro_range = d["aggro_range"]
        self.leash_range = d["leash_range"]
        self.neutral = d.get("neutral", False)  # always-passive ambient wildlife - see update()
        self.fire_rate_mult = d.get("fire_rate_mult", 1.0)  # <1.0 fires faster - see PHASE2_FIRE_RATE_MULT
        self.aggro = self.rank == "boss"  # bosses are always aggro, everything else starts idle
        self._t = random.uniform(0, 10)
        self._fire_cd = random.uniform(0, 1.2)
        self._phase_cd = random.uniform(2, 4)
        self._wander = pygame.Vector2(random.uniform(-1, 1), random.uniform(-1, 1))
        self.alive = True
        self.contact_cd = 0.0
        self._hit_flash = 0.0
        self.frozen_time = 0.0  # set by a "freeze"-effect ability; roots + silences while > 0
        # bleed/burn/vulnerable status effects (see BLEED_UT_NAMES/BURN_UT_NAMES/
        # VULNERABLE_UT_NAMES in realm_sim.py) - same plain-float-countdown shape as
        # frozen_time above, applied/ticked in RealmSim.update() (needs access to
        # `players` for kill-credit attribution if a DoT tick is the killing blow)
        self.bleed_time = 0.0
        self.bleed_dps = 0.0
        self.burn_time = 0.0
        self.burn_dps = 0.0
        self.vulnerable_time = 0.0
        self.vulnerable_mult = 1.0
        self.status_source_pid = None  # who last applied a status effect - kill credit if a DoT tick finishes them off
        self.unshootable = d.get("unshootable", False)  # ambient wildlife - bullets pass through
        # entirely (see RealmSim._resolve_bullet_hits), never a valid combat target
        self.flee_time = 0.0  # >0 while fleeing a nearby threat (see RealmSim.update's proximity
        # check for unshootable wildlife) - same plain-float-countdown shape as frozen_time/bleed_time
        self._flee_from = None  # pygame.Vector2 position to flee AWAY from while flee_time > 0
        self.push_time = 0.0  # >0 while gliding from a physical bump (see RealmSim.update's player-
        # contact check for neutral mobs) - same plain-float-countdown shape as flee_time, but a much
        # shorter, decelerating shove rather than an intelligent flee-away
        self._push_vec = pygame.Vector2(0, 0)  # world-units/sec velocity at the MOMENT the bump
        # happened - decays toward zero as push_time counts down (see update())
        self._push_total = 0.0  # push_time's starting value, so the decay above has something to divide by
        self.moonlit = False  # a rare, tougher night-only variant (see realm_sim._spawn_enemy_lair) - silver glow + bonus loot
        self._strafe_dir = random.choice((-1, 1))  # which way it circles once in range - see update()
        self._strafe_flip_cd = random.uniform(2.0, 5.0)
        self._spiral_angle = random.uniform(0, 360)  # "spiral" pattern: increments each shot
        self._charge_state = "idle"  # "charge" pattern: idle -> charging -> recover
        self._charge_cd = random.uniform(2.0, 4.0)
        self._root_pulse = False  # "boss_root": set true for one tick when a root pulse fires
        self.invulnerable = False  # "boss_burrow": true while burrowed underground
        self._burrow_state = "surfaced"  # boss_burrow: surfaced -> burrowing -> burrowed -> surfacing
        self._burrow_cd = random.uniform(2.5, 4.0)
        self._burrow_target = pygame.Vector2(self.pos)
        self.speech = ""       # a random flavor line, same speech-bubble mechanism as NexusBot
        self.speech_age = 0.0
        self._bark_pending = False  # set true for one tick when an idle sound bark should play - realm_sim checks+clears it
        self._speech_pending = False  # set true for one tick whenever a new flavor line starts - realm_sim
        # checks+clears it and pushes the line into the persistent chat log, not just the in-world bubble
        self._said_first_line = False  # has this mob ever said its "guaranteed once" aggro line yet
        self._speech_startup_jitter = random.uniform(0.0, 10.0)  # spreads out that guaranteed line so a
        # whole batch of enemies waking from ACTIVE_SIM_RADIUS dormancy on the same tick (e.g. the player
        # just walked into a dense new area) doesn't all instantly bark in that same tick - previously
        # unconditional, which is exactly what produced "10 messages/sec" bursts on entering new territory.
        # 10s (not a smaller window) because walking into a lair can wake up dozens of enemies at once -
        # spreading their first lines across a full 10s keeps the peak simultaneous rate low even then.

    def _move(self, delta, tile_map):
        """Applies a movement delta, resolved per-axis against SOLID tiles (rock
        outcrops in the open Realm, dungeon walls) - same sliding-along-a-wall
        approach as Player.net_update. tile_map=None (e.g. old call sites/tests)
        skips collision entirely, same as before this was added."""
        if tile_map is None:
            self.pos += delta
            return
        new_x = self.pos.x + delta.x
        if not tile_map.is_solid(new_x, self.pos.y):
            self.pos.x = new_x
        new_y = self.pos.y + delta.y
        if not tile_map.is_solid(self.pos.x, new_y):
            self.pos.y = new_y

    def update(self, dt, player_pos, bullets_out, tile_map=None):
        self._t += dt
        self.contact_cd = max(0.0, self.contact_cd - dt)
        self._hit_flash = max(0.0, self._hit_flash - dt)
        # status-effect timers tick regardless of frozen/aggro state - a DoT or a
        # vulnerable mark keeps counting down even through a stun, same as most
        # games' status effects (actual damage application is in RealmSim.update())
        self.bleed_time = max(0.0, self.bleed_time - dt)
        self.burn_time = max(0.0, self.burn_time - dt)
        self.vulnerable_time = max(0.0, self.vulnerable_time - dt)
        if self.frozen_time > 0:
            self.frozen_time = max(0.0, self.frozen_time - dt)
            return
        self._fire_cd -= dt
        to_player = player_pos - self.pos
        dist = to_player.length()
        to_player_n = to_player / dist if dist > 1 else pygame.Vector2(0, 1)

        # aggro state machine: idle enemies notice a nearby player IN LINE OF SIGHT
        # and lock on (a wall or rock outcrop between you is real cover, not just
        # decoration); aggro'd enemies that chase too far from home give up.
        # Neutral (always-passive) mobs skip this entirely and permanently - dmg=(0,0)
        # in their ENEMY_KINDS entry already makes contact harmless even though the
        # contact-damage check elsewhere isn't itself aggro-gated, but this is what
        # actually keeps them from ever chasing/firing in the first place.
        if self.rank != "boss" and not self.neutral:
            if (not self.aggro and dist <= self.aggro_range
                    and (tile_map is None or tile_map.has_line_of_sight(self.pos.x, self.pos.y,
                                                                          player_pos.x, player_pos.y))):
                self.aggro = True  # the flavor line itself is handled below, gated by
                # _speech_startup_jitter - NOT said instantly here anymore (see that
                # field's comment for why: a burst of simultaneously-waking mobs
                # from ACTIVE_SIM_RADIUS dormancy all firing on the same tick).
            elif self.aggro and self.pos.distance_to(self.home_pos) > self.leash_range:
                self.aggro = False

        self.speech_age += dt
        # MIN_REBARK_INTERVAL gates re-triggers so ONE mob can't chatter every few
        # seconds by chance - with many aggro'd mobs nearby, a %/sec-only roll made
        # it feel like something was always talking even though each individual mob
        # rarely re-spoke; the real fix is a hard per-mob cooldown, not a lower %.
        # Neutral mobs never aggro (self.aggro stays False forever for them), so they
        # naturally only ever take the idle-ambience branch below - never the combat
        # aggro one - which is exactly right for "always passive" flavor lines.
        if self.aggro and not self._said_first_line:
            if self.speech_age > self._speech_startup_jitter:
                self._say_flavor_line()
                self._said_first_line = True
        elif self.aggro and self.speech_age > self.MIN_REBARK_INTERVAL:
            if random.random() < dt * 0.02:
                self._say_flavor_line()
        elif (not self.aggro and self.speech_age > self.MIN_REBARK_INTERVAL
              and not (self.neutral and self.speed == 0)):
            # the speed==0 exclusion is the stationary totem decoration (also neutral,
            # per the secret-quest kill_totems mechanic) - it shouldn't "talk" at all,
            # unlike real neutral wildlife (speed>0), which is what this branch is for
            if random.random() < dt * 0.008:  # idle ambience - a sound AND a flavor line/bubble,
                self._bark_pending = True       # so neutral mobs (which only ever reach this branch)
                self._say_flavor_line()         # actually have "words," not just an audio cue

        self._wander += pygame.Vector2(random.uniform(-1, 1), random.uniform(-1, 1)) * dt * 3
        if self._wander.length_squared() > 1:
            self._wander.scale_to_length(1)

        self._strafe_flip_cd -= dt
        if self._strafe_flip_cd <= 0:
            self._strafe_dir = random.choice((-1, 1))
            self._strafe_flip_cd = random.uniform(2.0, 5.0)

        if self.push_time > 0:
            # a physical bump (see RealmSim.update's player-contact check) - a brief,
            # decelerating shove, checked even before flee_time so a startled bump
            # always reads as an immediate physical reaction, not queued behind
            # anything else. Decays LINEARLY to zero over push_total seconds rather
            # than holding a constant speed, so it reads as a glide-to-a-stop, not a
            # moving platform that snaps off.
            self.push_time = max(0.0, self.push_time - dt)
            frac = (self.push_time / self._push_total) if self._push_total > 0 else 0.0
            self._move(self._push_vec * frac * dt, tile_map)
        elif self.flee_time > 0:
            self.flee_time = max(0.0, self.flee_time - dt)
            away = self.pos - self._flee_from if self._flee_from is not None else pygame.Vector2(0, 0)
            heading = (away.normalize() if away.length_squared() > 1 else pygame.Vector2(0, 0)) * 0.85 \
                + self._wander * 0.4
            if heading.length_squared() > 0:
                self._move(heading.normalize() * self.speed * dt, tile_map)
        elif self.aggro:
            if self.pattern == "erratic":
                # swoop at the player, blended with jitter so it's not a beeline
                heading = to_player_n * 0.7 + self._wander * 0.6
                if heading.length_squared() > 0:
                    self._move(heading.normalize() * self.speed * dt, tile_map)
            elif self.pattern == "charge":
                self._update_charge(dt, to_player_n, dist, bullets_out, tile_map)
            elif self.pattern == "boss_burrow":
                self._update_burrow(dt, to_player_n, dist, bullets_out, tile_map)
            elif dist > 90:
                self._move(to_player_n * self.speed * dt * 0.6, tile_map)
            else:
                # in range - circle-strafe instead of standing dead still while it
                # shoots: a perpendicular orbit blended with wander jitter, backing
                # off a bit if the player closes to melee range. RotMG's own bullet-
                # pattern mobs don't just stop and turn into a stationary turret.
                strafe = to_player_n.rotate(90 * self._strafe_dir)
                heading = strafe * 0.8 + self._wander * 0.5
                if dist < 50:
                    heading -= to_player_n * 0.6
                if heading.length_squared() > 0:
                    self._move(heading.normalize() * self.speed * dt * 0.55, tile_map)
        else:
            # idle: wander gently near home instead of standing frozen or beelining -
            # this is the "liveness" behaviour, and it naturally walks a leashed
            # enemy back toward home since the pull strengthens with distance
            home_vec = self.home_pos - self.pos
            home_dist = home_vec.length()
            pull = (home_vec / home_dist) * min(1.0, home_dist / 120) if home_dist > 1 else pygame.Vector2(0, 0)
            heading = self._wander * 0.5 + pull
            if heading.length_squared() > 0:
                self._move(heading.normalize() * self.speed * 0.3 * dt, tile_map)

        if (self.aggro and self.pattern not in ("charge", "boss_burrow") and self._fire_cd <= 0
                and (tile_map is None or tile_map.has_line_of_sight(self.pos.x, self.pos.y,
                                                                      player_pos.x, player_pos.y))):
            self._fire_cd = self._pattern_interval() * self.fire_rate_mult
            self._shoot(to_player_n, bullets_out)

    def _update_charge(self, dt, to_player_n, dist, bullets_out, tile_map=None):
        """A dash-in melee-burst mob: sits back strafing like the others, then
        periodically dashes at ~2.4x speed straight at the player and unloads a
        close-range spread on arrival, before recovering and doing it again -
        real movement-pattern variety, not just a different bullet shape."""
        self._charge_cd -= dt
        if self._charge_state == "idle":
            if self._charge_cd <= 0 and dist > 45:
                self._charge_state = "charging"
                self._charge_cd = 0.6
            elif dist > 90:
                self._move(to_player_n * self.speed * dt * 0.6, tile_map)
            else:
                strafe = to_player_n.rotate(90 * self._strafe_dir)
                heading = strafe * 0.8 + self._wander * 0.5
                if heading.length_squared() > 0:
                    self._move(heading.normalize() * self.speed * dt * 0.55, tile_map)
        elif self._charge_state == "charging":
            self._move(to_player_n * self.speed * 2.4 * dt, tile_map)
            if self._charge_cd <= 0 or dist < 40:
                self._charge_state = "recover"
                self._charge_cd = random.uniform(2.5, 4.0)
                dmg = random.randint(*self.dmg)
                for off in (-0.3, 0, 0.3):
                    bullets_out.append(_mk_bullet(self.pos, to_player_n.rotate(math.degrees(off)), 260, dmg,
                                                   (255, 120, 60), radius=self._bullet_radius()))
        elif self._charge_state == "recover":
            if self._charge_cd <= 1.5:
                self._charge_state = "idle"

    def _update_burrow(self, dt, to_player_n, dist, bullets_out, tile_map=None):
        """The Sand Wyrm's whole gimmick: it's untouchable and repositioning most
        of the time (burrowed, fast, erratic - see draw()'s dust-ring), then
        surfaces right next to you for a brief, dangerous, fully-vulnerable
        window before diving again. A real phase cycle, not just a bullet shape."""
        self._burrow_cd -= dt
        if self._burrow_state == "surfaced":
            self.invulnerable = False
            if self._burrow_cd <= 0:
                self._burrow_state = "burrowing"
                self._burrow_cd = 0.4
        elif self._burrow_state == "burrowing":
            if self._burrow_cd <= 0:
                self.invulnerable = True
                self._burrow_state = "burrowed"
                self._burrow_cd = random.uniform(2.5, 4.0)
                ang = random.uniform(0, 360)
                self._burrow_target = self.pos + pygame.Vector2(1, 0).rotate(ang) * random.uniform(80, 220)
        elif self._burrow_state == "burrowed":
            to_target = self._burrow_target - self.pos
            if to_target.length() > 10:
                self._move(to_target.normalize() * self.speed * 2.6 * dt, tile_map)
            if self._burrow_cd <= 0:
                self._burrow_state = "surfacing"
                self._burrow_cd = 0.5
        elif self._burrow_state == "surfacing":
            if self._burrow_cd <= 0:
                self.invulnerable = False
                self._burrow_state = "surfaced"
                self._burrow_cd = random.uniform(2.0, 3.0)
                dmg = random.randint(*self.dmg)
                for i in range(10):
                    ang = (360 / 10) * i
                    bullets_out.append(_mk_bullet(self.pos, pygame.Vector2(1, 0).rotate(ang), 200, dmg,
                                                   (230, 190, 90), radius=self._bullet_radius()))

    def _pattern_interval(self):
        return {"aimed": 1.4, "erratic": 2.0, "spread": 1.6, "burst": 2.2, "boss": 0.35,
                "volley": 1.7, "spiral": 0.35, "charge": 1.0, "boss_root": 1.9}[self.pattern]

    def _bullet_radius(self):
        # visual-punch pass: a boss/elite's shots read as more threatening at a
        # glance, not just via color/pattern - reuses the richer glow/core shading
        # already in sprites.bullet_surface, just at a bigger base size
        return {"trash": 5, "elite": 6, "boss": 8}.get(self.rank, 5)

    def _shoot(self, aim_dir, out):
        dmg = random.randint(*self.dmg)
        speed = 220
        r = self._bullet_radius()
        if self.pattern == "aimed":
            out.append(_mk_bullet(self.pos, aim_dir, speed, dmg, (230, 60, 40), radius=r))
        elif self.pattern == "erratic":
            if random.random() < 0.6:
                out.append(_mk_bullet(self.pos, aim_dir, speed, dmg, (180, 60, 200), radius=r))
        elif self.pattern == "spread":
            for off in (-0.35, 0, 0.35):
                out.append(_mk_bullet(self.pos, aim_dir.rotate(math.degrees(off)), speed, dmg, (150, 220, 255),
                                       radius=r))
        elif self.pattern == "burst":
            for i in range(8):
                ang = (360 / 8) * i
                out.append(_mk_bullet(self.pos, pygame.Vector2(1, 0).rotate(ang), speed * 0.8, dmg, (255, 210, 90),
                                       radius=r))
        elif self.pattern == "volley":
            # a quick double-tap rather than one shot - a different speed on the
            # second bullet keeps them from perfectly overlapping in flight
            out.append(_mk_bullet(self.pos, aim_dir, speed, dmg, (255, 180, 60), radius=r))
            out.append(_mk_bullet(self.pos, aim_dir, speed * 1.2, dmg, (255, 180, 60), lifetime=2.5, radius=r))
        elif self.pattern == "spiral":
            # one bullet per shot, but the angle keeps advancing - traces a slow
            # rotating single-arm spiral over several shots instead of a fixed ring
            self._spiral_angle = (self._spiral_angle + 35) % 360
            d = pygame.Vector2(1, 0).rotate(self._spiral_angle)
            out.append(_mk_bullet(self.pos, d, speed * 0.85, dmg, (170, 220, 90), radius=r))
        elif self.pattern == "boss":
            self._phase_cd -= self._pattern_interval()
            spin = (self._t * 90) % 360
            for i in range(6):
                ang = spin + (360 / 6) * i
                out.append(_mk_bullet(self.pos, pygame.Vector2(1, 0).rotate(ang), speed, dmg, (255, 140, 0),
                                       radius=r))
            if self._phase_cd <= 0:
                self._phase_cd = random.uniform(3, 5)
                for i in range(16):
                    ang = (360 / 16) * i
                    out.append(_mk_bullet(self.pos, pygame.Vector2(1, 0).rotate(ang), speed * 1.3, dmg + 4,
                                           (255, 40, 40), radius=r + 1))
        elif self.pattern == "boss_root":
            # the Thorn Warden: a steady ring of thorns, plus every few shots a
            # slow double-ring "root pulse" - realm_sim.py checks _phase_cd<=0
            # right after this to actually root any player caught in it
            for i in range(10):
                ang = (360 / 10) * i + self._t * 20
                out.append(_mk_bullet(self.pos, pygame.Vector2(1, 0).rotate(ang), speed * 0.7, dmg, (90, 200, 70),
                                       radius=r))
            self._phase_cd -= self._pattern_interval()
            if self._phase_cd <= 0:
                self._phase_cd = random.uniform(4.5, 6.5)
                self._root_pulse = True  # realm_sim.py checks and clears this to actually root the player
                for i in range(20):
                    ang = (360 / 20) * i
                    out.append(_mk_bullet(self.pos, pygame.Vector2(1, 0).rotate(ang), speed * 0.55, dmg,
                                           (150, 90, 60), radius=r + 1))

    def take_damage(self, dmg, whole=True):
        """`whole=False` (bleed/burn DoT ticks only, see realm_sim.py) keeps the
        mitigated result as a smooth float instead of rounding up to a minimum
        of 1 whole point every tick - see constants.apply_defense's own
        `whole` doc for why that matters for a per-frame dps*dt fraction."""
        if self.invulnerable:
            self._last_hit_damage = 0
            return False
        if self.vulnerable_time > 0:
            dmg *= self.vulnerable_mult
        # mirrors Player.take_damage()'s own deF-based mitigation (constants.
        # apply_defense) instead of the old raw subtraction - see
        # ENEMY_DEFENSE_FLOOR/self.deF above. Stored on self so callers that
        # also show a damage popup for this same hit can display the real
        # post-mitigation amount instead of the raw pre-mitigation one.
        real = C.apply_defense(dmg, self.deF, ENEMY_DEFENSE_FLOOR.get(self.rank, 0.1), whole=whole)
        self._last_hit_damage = real
        self.hp -= real
        self._hit_flash = 0.12
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            return True
        return False

    def _say_flavor_line(self):
        if self.neutral and self.speed > 0:
            self.speech = random.choice(WILDLIFE_FLAVOR_LINES)
        else:
            self.speech = random.choice(MOB_FLAVOR_LINES[sound_family(self.kind)])
        self.speech_age = 0.0
        self._speech_pending = True

    def draw(self, surf, cam):
        img = sprites.enemy_sprite(self.kind)
        r = img.get_rect(center=cam(self.pos))
        if self.moonlit:
            pulse = 1.0 + 0.12 * math.sin(pygame.time.get_ticks() / 200.0)
            pygame.draw.circle(surf, (220, 225, 255), r.center, int(r.width * 0.7 * pulse), 2)
        if self.invulnerable:
            # burrowed - a faint dust-ring at its feet instead of the full sprite,
            # so it clearly reads as "underground and untouchable" not just dim
            pygame.draw.ellipse(surf, (120, 100, 70), (r.centerx - 16, r.bottom - 8, 32, 12))
            faint = img.copy()
            faint.set_alpha(70)
            surf.blit(faint, r)
            return
        surf.blit(img, r)
        if self._hit_flash > 0:
            flash = img.copy()
            flash.fill((255, 255, 255, 140), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(flash, r)
        if self.frozen_time > 0:
            frost = img.copy()
            frost.fill((150, 210, 255, 130), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(frost, r)
        if self.hp < self.hp_max:
            w = 26 if self.rank != "boss" else 60
            x, y = r.centerx - w // 2, r.top - 8
            pygame.draw.rect(surf, C.COL_HP_BG, (x, y, w, 4))
            pygame.draw.rect(surf, C.COL_HP, (x, y, int(w * self.hp / self.hp_max), 4))

    def net_state(self):
        return dict(kind=self.kind, x=round(self.pos.x, 1), y=round(self.pos.y, 1),
                    hp=self.hp, hp_max=self.hp_max, rank=self.rank, aggro=self.aggro,
                    frozen=self.frozen_time > 0, moonlit=self.moonlit, invulnerable=self.invulnerable,
                    speech=self.speech, speech_age=round(self.speech_age, 2), neutral=self.neutral)


def _mk_bullet(pos, direction, speed, dmg, color, owner="enemy", pierce=0, radius=5, lifetime=2.4,
               motion="straight", status_effect=None, shape="bolt"):
    # lifetime default was 3.0 (e.g. an archer bolt at speed 420 traveled 1260px,
    # well past the visible screen even at the bigger 1366x820 resolution) - trimmed
    # ~20% so ranged attacks (players and mobs alike, since most don't override this)
    # reach a bit past screen edge rather than far beyond it. A small change on
    # purpose - melee classes already pass their own much shorter explicit lifetimes,
    # unaffected either way.
    if direction.length_squared() == 0:
        direction = pygame.Vector2(0, 1)
    else:
        direction = direction.normalize()
    return Bullet(pos, direction * speed, dmg, owner, color, pierce, radius, lifetime, motion, status_effect, shape)


# a real new projectile TYPE, not just a new look: travels outward for the
# first BOOMERANG_TURN_FRAC of its lifetime, then smoothly curves back toward
# where it was fired from - it can still hit something on the way back since
# nothing about pierce/collision changes, only its own velocity over time
BOOMERANG_TURN_FRAC = 0.4
BOOMERANG_TURN_RATE = 6.0  # how fast the velocity vector reorients once turning starts


class Bullet:
    # `owner` is "enemy" for enemy bullets, or the firing player's pid for
    # player bullets - that pid is how co-op attributes kill credit/XP/loot.
    # `prev_pos` supports swept (segment) collision - see hit_test() below.
    __slots__ = ("pos", "prev_pos", "vel", "dmg", "owner", "color", "pierce", "radius", "life",
                 "motion", "origin", "total_life", "speed", "status_effect", "shape")

    def __init__(self, pos, vel, dmg, owner, color, pierce, radius, life, motion="straight", status_effect=None,
                 shape="bolt"):
        self.pos = pygame.Vector2(pos)
        self.prev_pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.dmg = dmg
        self.owner = owner
        self.color = color
        self.status_effect = status_effect  # "bleed" | "burn" | "vulnerable" | None - applied on a
        # successful player-bullet hit (see BLEED_UT_NAMES etc. in realm_sim.py, _resolve_bullet_hits)
        self.shape = shape  # "arrow"/"blade"/"bone"/"holy"/"star"/"orb"/"bolt" - see sprites.bullet_surface
        self.pierce = pierce
        self.radius = radius
        self.life = life
        self.motion = motion
        self.origin = pygame.Vector2(pos)
        self.total_life = life
        # fixed at the muzzle speed - recomputing this from the live (already-
        # decaying, mid-turn) self.vel each frame would make the "desired"
        # return-vector shrink toward zero right along with it, so the bullet
        # would stall out near the turn point instead of actually reversing
        self.speed = self.vel.length()

    def update(self, dt):
        self.prev_pos = pygame.Vector2(self.pos)
        if self.motion == "boomerang" and self.total_life > 0:
            elapsed_frac = 1.0 - (self.life / self.total_life)
            if elapsed_frac >= BOOMERANG_TURN_FRAC:
                to_origin = self.origin - self.pos
                if to_origin.length_squared() > 1:
                    desired = to_origin.normalize() * self.speed
                    self.vel = self.vel.lerp(desired, min(1.0, dt * BOOMERANG_TURN_RATE))
        self.pos += self.vel * dt
        self.life -= dt
        return self.life > 0

    def hit_test(self, target_pos, target_radius):
        """
        Swept collision: did the bullet's travel THIS TICK pass within
        (radius + target_radius) of target_pos, not just its end point?
        Needed because at low tick rates (the co-op server runs at 20Hz)
        a fast bullet's per-tick displacement can exceed the hit radius,
        letting it tunnel straight through a close target if only the
        end-of-step position were checked.
        """
        seg = self.pos - self.prev_pos
        seg_len_sq = seg.length_squared()
        reach = self.radius + target_radius
        if seg_len_sq < 1e-9:
            return self.pos.distance_to(target_pos) < reach
        t = max(0.0, min(1.0, (target_pos - self.prev_pos).dot(seg) / seg_len_sq))
        closest = self.prev_pos + seg * t
        return closest.distance_to(target_pos) < reach

    # shapes with a real "front" that should visibly point the way the bullet is
    # actually traveling - the others (orb/bone/holy/star/bolt) are symmetric
    # enough that rotating them would be wasted work for no visible difference
    _DIRECTIONAL_SHAPES = {"arrow", "blade"}

    def draw(self, surf, cam):
        # Bullet._DIRECTIONAL_SHAPES (not self._DIRECTIONAL_SHAPES) - this method is
        # reused directly as coop_client.GhostBullet.draw (`draw = Bullet.draw`),
        # which has no class attributes of its own, only the plain per-instance
        # fields set in its __init__
        if self.vel.length_squared() > 1:
            # a short fading trail behind the bullet, computed purely from its own
            # pos/vel each frame (no stored history, no network field needed) -
            # GhostBullet reuses this same draw() and already has both fields
            back = -self.vel.normalize()
            for i in range(1, 4):
                trail_pos = self.pos + back * (i * self.radius * 1.6)
                t = 1.0 - i / 4.0
                r = max(1, int(self.radius * 0.5 * t))
                d = r * 2 + 2
                layer = pygame.Surface((d, d), pygame.SRCALPHA)
                pygame.draw.circle(layer, (*self.color, int(140 * t)), (d // 2, d // 2), r)
                tx, ty = cam(trail_pos)
                surf.blit(layer, (tx - d // 2, ty - d // 2))
        img = sprites.bullet_surface(self.color, self.radius, self.shape)
        if self.shape in Bullet._DIRECTIONAL_SHAPES and self.vel.length_squared() > 0:
            img = pygame.transform.rotate(img, -self.vel.angle_to(pygame.Vector2(1, 0)))
        surf.blit(img, img.get_rect(center=cam(self.pos)))

    def net_state(self):
        return dict(x=round(self.pos.x, 1), y=round(self.pos.y, 1), owner=self.owner,
                    color=list(self.color), radius=self.radius, shape=self.shape,
                    vel=[round(self.vel.x, 1), round(self.vel.y, 1)])


_id_counter = itertools.count(1)


BAG_CAPACITY = 8
BAG_LIFETIME = 120.0  # 2 minutes - RotMG-style loot bag despawn (up from the old 45s single-item timer)
BAG_MERGE_RADIUS = 50.0   # nearby, still-open bags within this range absorb new drops instead of spawning new ones
BAG_MERGE_WINDOW = 3.0    # ...but only while they're still this "fresh" (age), so an old half-looted bag
                           # across the room doesn't keep vacuuming up unrelated later kills


class Bag:
    """A RotMG-style loot bag: up to BAG_CAPACITY items dropped together (one
    kill's loot, or several drops pooled within BAG_MERGE_WINDOW/RADIUS of each
    other - see RealmSim._reward()) rather than one ground item per drop. Picked
    up via drag-and-drop from a small floating window (see ui.draw_bag_window),
    not an instant right-click grab."""

    _RARITY_RANK = {"brown": 0, "purple": 1, "white": 2}

    def __init__(self, items, pos, dropped_by=None, rarity_key=None):
        self.id = next(_id_counter)
        self.items = list(items)
        self.pos = pygame.Vector2(pos)
        self.life = BAG_LIFETIME
        self.age = 0.0
        # a manually-dropped item lands exactly on the dropper's feet, so without this
        # they'd auto-pickup their own drop again on the very next tick; other players
        # can still grab it instantly - only the owner has to step away first
        self.dropped_by = dropped_by
        self.self_pickup_immune = 1.0 if dropped_by is not None else 0.0
        # RotMG's real signal: a bag's OWN color reflects the rarest thing inside it
        # (brown/purple/white), independent of any one item's own tier-color gradient
        self.rarity_key = rarity_key or "brown"

    @property
    def bag_color(self):
        from game.constants import BAG_COLORS
        return BAG_COLORS.get(self.rarity_key, BAG_COLORS["brown"])

    def is_full(self):
        return len(self.items) >= BAG_CAPACITY

    def add_item(self, item, rarity_key=None):
        if self.is_full():
            return False
        self.items.append(item)
        if rarity_key and self._RARITY_RANK.get(rarity_key, 0) > self._RARITY_RANK.get(self.rarity_key, 0):
            self.rarity_key = rarity_key
        return True

    def remove_item(self, idx):
        if 0 <= idx < len(self.items):
            return self.items.pop(idx)
        return None

    def update(self, dt):
        self.life -= dt
        self.age += dt
        self.self_pickup_immune = max(0.0, self.self_pickup_immune - dt)
        return self.life > 0 and len(self.items) > 0

    def can_be_taken_by(self, pid):
        return not (self.self_pickup_immune > 0 and pid == self.dropped_by)

    def draw(self, surf, cam):
        p = cam(self.pos)
        fill_frac = len(self.items) / BAG_CAPACITY
        img = sprites.bag_sprite(fill_frac > 0.5, self.bag_color)
        surf.blit(img, (p[0] - img.get_width() // 2, p[1] - img.get_height() // 2 + 3))

    def net_state(self):
        # lightweight "ghost" representation for everyone who hasn't opened this
        # bag - full item data (for the drag window) rides a dedicated bag_state
        # message sent only to whoever actually opens it, same pattern as the Vault
        first = self.items[0] if self.items else None
        return dict(id=self.id, x=round(self.pos.x, 1), y=round(self.pos.y, 1),
                    bag_color=list(self.bag_color), count=len(self.items),
                    name=first.display_name if first else "",
                    tier_color=list(first.color) if first else [150, 150, 150])


BAG_LOOT_RADIUS = 45  # matches RealmSim.LOOT_RADIUS - also used by the Bazaar's bare bag list,
                       # which has no RealmSim wrapper to hang a matching constant off of


def find_nearby_bag(bags, pos, pid, radius=BAG_LOOT_RADIUS):
    """The closest bag in `bags` that `pid` is allowed to open (right-click) - shared
    by RealmSim.find_nearby_bag() and the Bazaar's plain ground_items list, which has
    no RealmSim wrapper of its own."""
    candidates = [g for g in bags if g.pos.distance_to(pos) <= radius and g.can_be_taken_by(pid)]
    if not candidates:
        return None
    return min(candidates, key=lambda g: g.pos.distance_to(pos))


def bag_by_id(bags, bag_id):
    return next((g for g in bags if g.id == bag_id), None)


def withdraw_from_bag(bags, bag_id, idx, player, target_idx=None):
    """Drags/clicks one item out of an open bag into the player's backpack.
    If `target_idx` names a SPECIFIC, OCCUPIED backpack slot (dragged there
    with a full backpack, rather than a plain click), the two items SWAP
    instead of the withdrawal simply failing - the displaced backpack item
    takes the bag's now-empty slot, matching RotMG's own "drag onto a full
    slot to swap" convention. Returns the withdrawn Item, or None if the
    bag/index isn't valid or there's genuinely no room."""
    bag = bag_by_id(bags, bag_id)
    if bag is None or not bag.can_be_taken_by(player.pid):
        return None
    if idx < 0 or idx >= len(bag.items):
        return None
    item = bag.items[idx]
    if target_idx is not None and 0 <= target_idx < len(player.backpack):
        displaced = player.backpack[target_idx]
        player.backpack[target_idx] = item
        bag.items[idx] = displaced
        return item
    if not player.try_pickup(item):
        return None
    bag.remove_item(idx)
    return item


NEXUS_BOT_LINES_AMBIENT = [
    "Welcome to the Nexus, traveler.",
    "The Bazaar's got good deals today, or so I hear.",
    "Careful out there - the Godlands don't forgive mistakes.",
    "I've seen a Blood Moon rise over the Realm once. Never again.",
    "Try the fountain if you're feeling lucky.",
    "Your Vault's always here, whenever you need it.",
    "Fish are biting near the shorelines, I hear.",
    "A dungeon's only as dangerous as who dropped the portal to it.",
]
NEXUS_BOT_LINES_GREETING = [
    "Oh, hello there!",
    "Good to see a fresh face.",
    "Off to the Realm already?",
    "Need directions? Portal, Vault, and Bazaar are all right here.",
]


class NexusBot:
    """A wandering NPC that lives only in the Nexus - RotMG's Nexus has always
    felt more like a real place with other characters standing/moving around
    in it than an empty lobby. Purely decorative/flavor (no shop, no quests
    yet) but genuinely animated: picks a random walkable point, walks there,
    pauses, and periodically says something - a greeting line if a player is
    nearby, an ambient one otherwise."""
    GREET_RADIUS = 140
    SPEECH_LIFETIME = 4.0

    def __init__(self, pos):
        self.pos = pygame.Vector2(pos)
        self.target = pygame.Vector2(pos)
        self.speed = 45
        self.pause_time = random.uniform(1.0, 3.0)
        self.speech_cd = random.uniform(3.0, 6.0)
        self.speech = ""
        self.speech_age = 0.0
        self.name = "Father Given"  # sounds like "forgiven" - a goofy priest-pun name, per user request
        self._speech_pending = False  # set true for one tick whenever a new line starts -
        # main.py/coop_client.py check+clear it and push the line into the persistent chat log

    def _pick_new_target(self, nexus_map):
        for _ in range(20):
            tx = random.randint(3, nexus_map.w - 4)
            ty = random.randint(3, nexus_map.h - 4)
            wx, wy = tx * C.TILE + C.TILE / 2, ty * C.TILE + C.TILE / 2
            if not nexus_map.is_solid(wx, wy):
                self.target = pygame.Vector2(wx, wy)
                return

    def update(self, dt, nexus_map, nearby_player_dist):
        self.speech_age += dt
        if self.pause_time > 0:
            self.pause_time -= dt
            if self.pause_time <= 0:
                self._pick_new_target(nexus_map)
        else:
            to_target = self.target - self.pos
            if to_target.length() < 4:
                self.pause_time = random.uniform(2.0, 5.0)
            else:
                self.pos += to_target.normalize() * self.speed * dt

        self.speech_cd -= dt
        if self.speech_cd <= 0:
            near = nearby_player_dist is not None and nearby_player_dist <= self.GREET_RADIUS
            pool = NEXUS_BOT_LINES_GREETING if near else NEXUS_BOT_LINES_AMBIENT
            self.speech = random.choice(pool)
            self.speech_age = 0.0
            self._speech_pending = True
            self.speech_cd = random.uniform(5.0, 9.0) if near else random.uniform(8.0, 14.0)

    def draw(self, surf, cam):
        img = sprites.player_sprite("priest")
        tinted = img.copy()
        tinted.fill((235, 215, 140, 255), special_flags=pygame.BLEND_RGBA_MULT)
        r = tinted.get_rect(center=cam(self.pos))
        surf.blit(tinted, r)

    def net_state(self):
        return dict(x=round(self.pos.x, 1), y=round(self.pos.y, 1), name=self.name,
                    speech=self.speech if self.speech_age < self.SPEECH_LIFETIME else "",
                    speech_age=round(self.speech_age, 2))


class Portal:
    """
    A mob-death portal into a small, denser bonus dungeon instance - RotMG's
    "event portal" concept (a Godlands enemy has a chance to drop a portal
    to a bonus room on death) at v0 scale.
    """
    # per-kind ring colors (outer glow, main ring, inner core) PLUS a distinct
    # per-kind SHAPE (see draw()) - each kind now reads as a genuinely different
    # portal at a glance, not just a recolored copy of the same three circles.
    KIND_COLORS = {
        "entrance": ((40, 20, 60), (150, 70, 220), (220, 170, 255)),
        "realm_exit": ((25, 55, 30), (110, 210, 100), (210, 250, 190)),
        "phase2": ((60, 10, 10), (230, 60, 40), (255, 170, 110)),
        "dungeon_shard": ((45, 15, 55), (200, 90, 210), (250, 200, 255)),
        "ambient": ((40, 20, 60), (150, 70, 220), (220, 170, 255)),
        # "The Reforging" hub portals (see RealmSim._stamp_islands) - a same-map
        # teleport to an island, not a dungeon-instance swap, so it gets its own
        # distinct amber look rather than reusing any dungeon-transition color
        "island_link": ((60, 45, 10), (230, 180, 70), (255, 235, 190)),
    }

    def __init__(self, pos, life=60.0, theme=None, kind="ambient", difficulty=None, target_pos=None, label=None):
        self.id = next(_id_counter)
        self.pos = pygame.Vector2(pos)
        self.life = life
        self.t = 0.0
        self.theme = theme  # which dungeon theme this portal leads to, if any (see realm_sim.DUNGEON_THEMES)
        self.kind = kind    # "entrance" | "realm_exit" | "phase2" | "dungeon_shard" | "ambient" | "island_link"
        self.difficulty = difficulty  # "Easy"/"Medium"/"Hard" (see realm_sim.BONUS_DIFFICULTIES), rolled at the
        # moment a Dungeon Shard is used - shown as a label on the portal (ui.draw_portal_label) so the
        # player knows what they're stepping into BEFORE entering, instead of a hidden roll on arrival
        self.target_pos = target_pos  # island_link only: the (x, y) world position on THIS SAME map to
        # teleport to - every other kind swaps to/from a separate RealmSim instance instead (see
        # main.py._trigger_portal_prompt / server.py's enter_portal action), so this is None for them
        self.label = label  # island_link only: the island's display name (e.g. "Emberfall Shard"),
        # shown above the portal by ui.draw_portal_label the same way a dungeon-shard portal shows
        # its rolled difficulty

    def update(self, dt):
        self.life -= dt
        self.t += dt
        return self.life > 0

    def draw(self, surf, cam):
        p = cam(self.pos)
        pulse = 1.0 + 0.15 * math.sin(self.t * 4)
        r = int(14 * pulse)
        glow, ring, core = self.KIND_COLORS.get(self.kind, self.KIND_COLORS["ambient"])
        if self.kind == "realm_exit":
            self._draw_beacon(surf, p, r, glow, ring, core)
        elif self.kind == "phase2":
            self._draw_rift_spikes(surf, p, r, glow, ring, core)
        elif self.kind == "dungeon_shard":
            self._draw_torn_rift(surf, p, r, glow, ring, core)
        elif self.kind == "entrance":
            self._draw_vortex(surf, p, r, glow, ring, core)
        else:
            pygame.draw.circle(surf, glow, p, r + 3)
            pygame.draw.circle(surf, ring, p, r)
            pygame.draw.circle(surf, core, p, max(2, r - 6))

    def _draw_vortex(self, surf, p, r, glow, ring, core):
        """entrance - a slowly rotating double-arc swirl on top of the base ring,
        reads as an active portal actively drawing you in."""
        pygame.draw.circle(surf, glow, p, r + 3)
        pygame.draw.circle(surf, ring, p, r, width=3)
        pygame.draw.circle(surf, core, p, max(2, r - 7))
        rect = (p[0] - r, p[1] - r, r * 2, r * 2)
        for off in (0, math.pi):
            ang = self.t * 2.2 + off
            pygame.draw.arc(surf, core, rect, ang, ang + math.pi * 0.7, 2)

    def _draw_beacon(self, surf, p, r, glow, ring, core):
        """realm_exit - a calm upward light beam + a ground ring instead of a
        closed circle, reads as "safe way out" rather than "into danger"."""
        beam_h = int(r * 3.2)
        beam_w = max(3, int(r * 0.55))
        beam_surf = pygame.Surface((beam_w, beam_h), pygame.SRCALPHA)
        for i in range(beam_h):
            a = int(150 * (1 - i / beam_h))
            pygame.draw.line(beam_surf, (*core, a), (0, beam_h - i), (beam_w, beam_h - i))
        beam_rect = beam_surf.get_rect(midbottom=(p[0], p[1] + r * 0.4))
        surf.blit(beam_surf, beam_rect)
        pygame.draw.ellipse(surf, glow, (p[0] - r - 3, p[1] + r * 0.15, (r + 3) * 2, int(r * 0.9)))
        pygame.draw.ellipse(surf, ring, (p[0] - r, p[1] + r * 0.25, r * 2, int(r * 0.6)), width=2)

    def _draw_rift_spikes(self, surf, p, r, glow, ring, core):
        """phase2 - a jagged, spiked rift instead of a clean ring, reads as
        aggressive/dangerous for the boss-phase escalation moment."""
        pygame.draw.circle(surf, glow, p, r + 4)
        n = 8
        pts = []
        for i in range(n * 2):
            ang = (i / (n * 2)) * math.tau + self.t * 3
            rad = (r + 5) if i % 2 == 0 else max(2, r - 5)
            pts.append((p[0] + math.cos(ang) * rad, p[1] + math.sin(ang) * rad))
        pygame.draw.polygon(surf, ring, pts)
        pygame.draw.circle(surf, core, p, max(2, r - 8))

    def _draw_torn_rift(self, surf, p, r, glow, ring, core):
        """dungeon_shard - a torn crack in reality (two crossing jagged lines)
        instead of a smooth ring, distinct from entrance's swirl even though
        they share a similar purple palette."""
        pygame.draw.circle(surf, glow, p, r + 2)
        for base_ang in (0.7, -0.7):
            ang = base_ang + math.sin(self.t * 1.5) * 0.1
            x0, y0 = p[0] - math.cos(ang) * r, p[1] - math.sin(ang) * r
            x1, y1 = p[0] + math.cos(ang) * r, p[1] + math.sin(ang) * r
            pygame.draw.line(surf, ring, (x0, y0), (x1, y1), 3)
        pygame.draw.circle(surf, core, p, max(2, r - 9))

    def net_state(self):
        return dict(id=self.id, x=round(self.pos.x, 1), y=round(self.pos.y, 1), kind=self.kind,
                    difficulty=self.difficulty, label=self.label)


class Obstacle:
    """A destructible one-shot wall prop placed inside some dungeon rooms at
    generation time (see world.make_bonus_room's "obstacle_spots") - not a
    full Enemy (no AI, no aggro, never fires or damages anyone). Blocks
    PLAYER movement while alive and is cleared by exactly one player hit
    (melee or ranged - both resolve as Bullet objects in this engine, so
    reusing _resolve_bullet_hits' existing pipeline covers both for free).
    Never blocks or damages enemies - purely a player-facing obstacle/
    shortcut-or-loot-teaser element, per the dungeon-rework plan."""

    def __init__(self, pos, hp=1, kind="crate"):
        self.id = next(_id_counter)
        self.pos = pygame.Vector2(pos)
        self.radius = C.TILE * 0.42
        self.hp = hp
        self.kind = kind  # "crate" (original loot-teaser prop) | "rubble_wall" (see
        # world.make_bonus_room's wall_obstacle_spots - a tougher, wider blocker
        # placed IN a corridor rather than scattered inside a room)
        self.alive = True

    def take_damage(self, amount):
        self.hp -= amount
        if self.hp <= 0:
            self.alive = False
        return not self.alive

    def draw(self, surf, cam):
        p = cam(self.pos)
        r = int(self.radius)
        if self.kind == "rubble_wall":
            # no hand-painted art yet for this kind (see obstacle_sprite(), which is
            # crate-only) - a distinct chunky stone-rubble look, gray rather than the
            # crate's wood-brown, so it reads as "a wall", not "a container", at a glance
            rect = (p[0] - r, p[1] - r, r * 2, r * 2)
            pygame.draw.rect(surf, (110, 106, 112), rect, border_radius=2)
            pygame.draw.rect(surf, (60, 58, 64), rect, width=2, border_radius=2)
            pygame.draw.line(surf, (48, 46, 52), (p[0] - r * 0.7, p[1] - r * 0.2), (p[0] + r * 0.5, p[1] - r * 0.5), 2)
            pygame.draw.line(surf, (48, 46, 52), (p[0] - r * 0.3, p[1] + r * 0.1), (p[0] + r * 0.7, p[1] + r * 0.6), 2)
            pygame.draw.line(surf, (48, 46, 52), (p[0] - r * 0.6, p[1] + r * 0.5), (p[0] + r * 0.1, p[1] - r * 0.6), 2)
            return
        art = sprites.obstacle_sprite()
        if art is not None:
            surf.blit(art, (p[0] - art.get_width() / 2, p[1] - art.get_height() / 2))
            return
        rect = (p[0] - r, p[1] - r, r * 2, r * 2)
        pygame.draw.rect(surf, (96, 80, 62), rect, border_radius=3)
        pygame.draw.rect(surf, (58, 47, 36), rect, width=2, border_radius=3)
        pygame.draw.line(surf, (40, 32, 25), (p[0] - r * 0.6, p[1] - r * 0.5), (p[0] + r * 0.2, p[1] + r * 0.6), 2)
        pygame.draw.line(surf, (40, 32, 25), (p[0] + r * 0.5, p[1] - r * 0.6), (p[0] - r * 0.1, p[1] + r * 0.3), 2)

    def net_state(self):
        return dict(id=self.id, x=round(self.pos.x, 1), y=round(self.pos.y, 1), kind=self.kind)


PET_ATTACK_RANGE = 220


class Pet:
    """A hatched companion (see items.PET_KINDS) that follows its owner and
    independently runs all 3 ability slots - heal / mp-restore / a weak
    attack on the nearest enemy - each on its own cooldown, so all 3 can fire
    within the same tick instead of only ever one fixed behavior. Each
    ability levels up on its own via feeding (Player.feed_pet), capped by the
    pet's rarity. Simulated server-side like everything else; clients only
    ever see its net_state() and draw it."""

    def __init__(self, kind, owner_pos):
        self.kind = kind
        d = PET_KINDS[kind]
        self.rarity = d["rarity"]
        specialty = d["family"]
        start_lvl = PET_RARITY_START_LEVEL[self.rarity]
        self.abilities = {
            ab: dict(level=(start_lvl if ab == specialty else 1), xp=0.0, cd=random.uniform(0, 2.0))
            for ab in PET_ABILITY_KEYS
        }
        self.pos = pygame.Vector2(owner_pos) + pygame.Vector2(-22, 18)
        self._t = random.uniform(0, 10)

    def update(self, dt, owner, enemies, bullets_out):
        self._t += dt
        target = owner.pos + pygame.Vector2(-22, 18)
        to_target = target - self.pos
        if to_target.length_squared() > 4:
            self.pos += to_target * min(1.0, dt * 4.0)
        for st in self.abilities.values():
            st["cd"] = max(0.0, st["cd"] - dt)
        if not owner.alive:
            return []
        events = []
        heal_st = self.abilities["heal"]
        if heal_st["cd"] <= 0 and owner.hp < owner.hp_max:
            magnitude, cooldown = pet_ability_stats("heal", heal_st["level"])
            healed = min(owner.hp_max, owner.hp + magnitude) - owner.hp
            owner.hp += healed
            heal_st["cd"] = cooldown
            events.append(("heal", owner.pos.x, owner.pos.y, (110, 230, 140), healed))
        magic_st = self.abilities["magic"]
        if magic_st["cd"] <= 0 and owner.mp < owner.mp_max:
            magnitude, cooldown = pet_ability_stats("magic", magic_st["level"])
            restored = min(owner.mp_max, owner.mp + magnitude) - owner.mp
            owner.mp += restored
            magic_st["cd"] = cooldown
            events.append(("mana", owner.pos.x, owner.pos.y, (120, 170, 255), restored))
        attack_st = self.abilities["attack"]
        if attack_st["cd"] <= 0:
            nearest, best = None, PET_ATTACK_RANGE
            for e in enemies:
                dist = e.pos.distance_to(owner.pos)
                if dist < best:
                    nearest, best = e, dist
            if nearest is not None:
                magnitude, cooldown = pet_ability_stats("attack", attack_st["level"])
                aim = nearest.pos - self.pos
                bullets_out.append(_mk_bullet(self.pos, aim, 260, magnitude, (255, 170, 90),
                                               owner=owner.pid))
                attack_st["cd"] = cooldown
        return events

    def draw(self, surf, cam):
        img = sprites.enemy_sprite(PET_KINDS[self.kind]["base"])
        small = pygame.transform.smoothscale(img, (int(img.get_width() * 0.55), int(img.get_height() * 0.55)))
        tinted = small.copy()
        tinted.fill((*PET_KINDS[self.kind]["tint"], 255), special_flags=pygame.BLEND_RGBA_MULT)
        bob = math.sin(self._t * 3) * 3
        r = tinted.get_rect(center=(cam(self.pos)[0], cam(self.pos)[1] + bob))
        surf.blit(tinted, r)

    def net_state(self):
        return dict(kind=self.kind, x=round(self.pos.x, 1), y=round(self.pos.y, 1),
                    levels={k: v["level"] for k, v in self.abilities.items()},
                    xp={k: round(v["xp"], 1) for k, v in self.abilities.items()})

    @staticmethod
    def from_net_state(d):
        p = Pet(d["kind"], (d["x"], d["y"]))
        p.pos = pygame.Vector2(d["x"], d["y"])
        for k, lvl in d.get("levels", {}).items():
            if k in p.abilities:
                p.abilities[k]["level"] = lvl
        for k, xp in d.get("xp", {}).items():
            if k in p.abilities:
                p.abilities[k]["xp"] = xp
        return p

"""
Gemstones: stones you forge INTO a weapon at Brother Hammerstein's Anvil.

Unlike Weapon Shards (game/runes.py - swappable, live in the Shards tab and follow
whatever weapon you hold), a stone is set into ONE weapon for good: it travels with
that weapon (trading, vault, co-op) and only comes out by prying, which shatters it.

  Sockets  - a weapon has 1 / 2 / 3 sockets by tier (T0-4 / T5-9 / T10+; UT and Divine
             weapons have 2).
  Stones   - 7 kinds, each an element with its own effect and colour (STONES), in 5
             grades (Chipped .. Perfect) that scale it (GRADE_MULT).
  Stacking - same stones add up (Diablo-style); 2 of one kind = "Attuned" (x1.15),
             3 = "Resonant" (x1.3 plus a bonus effect, RESONANT).
  Anvil    - "Set stone" into the equipped weapon, "Combine" 3 same stones -> next
             grade, "Pry out" (the stone shatters). See stonework_options/apply_stonework.
  Visuals  - the bullet takes the first stone's colour + an element trail
             (entities.Bullet.draw), the weapon icon gets pips + a glow
             (sprites.icon_of), the player an element aura (Player.draw), and every
             element has its own on-hit / on-kill burst (vfx "gem_hit" / "gem_burst").

Pure logic + data (no pygame).
"""
import random

GRADES = ("chipped", "flawed", "regular", "flawless", "perfect")
GRADE_MULT = {"chipped": 0.55, "flawed": 0.75, "regular": 1.0, "flawless": 1.35, "perfect": 1.8}
GRADE_TIER = {"chipped": 2, "flawed": 4, "regular": 7, "flawless": 10, "perfect": 13}
GRADE_WEIGHT = {"chipped": 46, "flawed": 30, "regular": 16, "flawless": 6, "perfect": 2}
GRADE_FACETS = {"chipped": 5, "flawed": 6, "regular": 6, "flawless": 7, "perfect": 8}  # icon detail

# kind -> (name, element, colour, the effect key it adds to a shot, what it does)
STONES = {
    "ruby": ("Ruby", "fire", (235, 60, 55), "burn", "shots set foes ablaze"),
    "sapphire": ("Sapphire", "frost", (80, 150, 255), "frostbite", "shots chill and slow"),
    "topaz": ("Topaz", "lightning", (255, 210, 70), "chain", "shots arc lightning to nearby foes"),
    "emerald": ("Emerald", "venom", (60, 215, 110), "venom", "shots poison; the poison spreads when a foe dies"),
    "amethyst": ("Amethyst", "arcane", (175, 95, 255), "seeker", "shots curve toward foes and pierce"),
    "onyx": ("Onyx", "shadow", (120, 70, 150), "leech", "hits drain life back to you"),
    "diamond": ("Diamond", "radiant", (235, 245, 255), "keen", "a chance to crit for double damage"),
}
KINDS = tuple(STONES)

ATTUNED_MULT = 1.15
RESONANT_MULT = 1.3
# kind -> what 3 of it in one weapon adds
RESONANT = {
    "ruby": "kills explode in fire",
    "sapphire": "kills shatter, freezing and hurting foes nearby",
    "topaz": "kills discharge lightning into the 2 nearest foes",
    "emerald": "the poison spreads twice as far at full strength",
    "amethyst": "+2 pierce",
    "onyx": "kills heal you for 6% of your max HP",
    "diamond": "crits hit for x2.5 instead of x2",
}
# Attuned (2+) sapphires already shatter (slow only) on a kill
SHATTER_RADIUS = 100
FIRE_BURST_RADIUS = 90
VENOM_SPREAD_RADIUS = (90, 160)  # normal, Resonant
VENOM_DPS_FRACTION = 0.16        # x hit damage per second, x stone strength
ONYX_FEAST_FRAC = 0.06
DIAMOND_RESONANT_CRIT = 2.5

# Anvil costs (Forge Ingots) by the stone's grade
SET_INGOTS = {"chipped": 0, "flawed": 0, "regular": 0, "flawless": 1, "perfect": 2}
COMBINE_INGOTS = {"chipped": 0, "flawed": 0, "regular": 0, "flawless": 1}  # -> the next grade

# drops (on top of normal loot): elites ~6%, bosses ~30%; better sources roll better grades
GEM_DROP_CHANCE = {"elite": 0.06, "boss": 0.30}
# stone drops roll on their OWN random stream, so adding them never shifts the rest of the
# loot / combat RNG (seeded tests and replays keep their exact sequences)
_DROP_RNG = random.Random()
SOURCE_GRADE_BOOST = {"island": 1, "heroic": 1, "blood_moon": 1, "mg_room_1": 2, "mg_room_2": 2, "mg_room_3": 2}
SOURCE_CHANCE_MULT = {"night": 1.5, "blood_moon": 2.0}


def stone_name(kind, grade):
    n = STONES[kind][0]
    return n if grade == "regular" else f"{grade.title()} {n}"


def color_of(kind):
    return STONES.get(kind, ("", "", (210, 210, 220)))[2]


def make_gem(kind=None, grade=None, rng=random):
    from game.items import Item
    if kind is None:
        kind = rng.choice(KINDS)
    if grade is None:
        grade = rng.choices(GRADES, weights=[GRADE_WEIGHT[g] for g in GRADES])[0]
    name, _el, _col, _eff, what = STONES[kind]
    return Item(stone_name(kind, grade), "gem", GRADE_TIER[grade], f"gem_{kind}_{grade}", gem_kind=kind,
                gem_grade=grade,
                description=f"Gemstone - Brother Hammerstein can set it into your weapon at the Anvil: {what}.")


def is_gem(item):
    return item is not None and getattr(item, "slot", None) == "gem" and bool(getattr(item, "gem_kind", ""))


def socket_count(weapon):
    if weapon is None or weapon.slot != "weapon":
        return 0
    if weapon.is_ut or getattr(weapon, "divine", False):
        return 2
    return 1 if weapon.tier <= 4 else (2 if weapon.tier <= 9 else 3)


def stones_in(weapon):
    """[(kind, grade)] set into this weapon (oldest first)."""
    return [tuple(g) for g in (getattr(weapon, "gems", None) or []) if g and g[0] in STONES]


def free_sockets(weapon):
    return socket_count(weapon) - len(stones_in(weapon))


def lead_kind(weapon):
    """The first stone's kind - it colours the weapon and its shots (like Diablo II)."""
    s = stones_in(weapon)
    return s[0][0] if s else None


def counts(weapon):
    out = {}
    for k, _g in stones_in(weapon):
        out[k] = out.get(k, 0) + 1
    return out


def bond(n):
    return "Resonant" if n >= 3 else ("Attuned" if n == 2 else "")


def weapon_fx(weapon):
    """{effect: strength} this weapon's stones add to a shot (the same keys Weapon Shards
    use where they overlap - burn / frostbite / chain / seeker / leech / keen - plus the
    stone-only ones: venom, gem_pierce, and res_<kind> for a Resonant set)."""
    fx = {}
    by = {}
    for k, g in stones_in(weapon):
        by.setdefault(k, []).append(GRADE_MULT[g])
    for k, ms in by.items():
        s = sum(ms) * (RESONANT_MULT if len(ms) >= 3 else ATTUNED_MULT if len(ms) == 2 else 1.0)
        fx[STONES[k][3]] = fx.get(STONES[k][3], 0.0) + s
        if k == "amethyst":
            fx["gem_pierce"] = len(ms) + (2 if len(ms) >= 3 else 0)
        if k == "sapphire" and len(ms) >= 2:
            fx["gem_shatter"] = s
        if len(ms) >= 3:
            fx[f"res_{k}"] = s
    return fx


def merge_fx(rune_fx, gem_fx):
    """A weapon's stones on top of the Shards tab: an effect both give counts the stronger
    in full plus half the weaker; everything else is just added."""
    out = dict(rune_fx or {})
    for k, v in (gem_fx or {}).items():
        if k in out and not k.startswith(("res_", "gem_")):
            a, b = out[k], v
            out[k] = max(a, b) + 0.5 * min(a, b)
        else:
            out[k] = v
    return out


def describe_weapon(weapon):
    """Tooltip lines for a weapon's sockets."""
    n = socket_count(weapon)
    if n <= 0:
        return []
    stones = stones_in(weapon)
    lines = []
    for k, g in stones:
        lines.append(f"<> {stone_name(k, g)} ({STONES[k][1]})")
    for _ in range(n - len(stones)):
        lines.append("<> (empty socket)")
    for k, c in counts(weapon).items():
        if c >= 2:
            lines.append(f"{bond(c)} {STONES[k][0]} x{RESONANT_MULT if c >= 3 else ATTUNED_MULT}")
            if c >= 3:
                lines.append(f"  {RESONANT[k]}")
            elif k == "sapphire":
                lines.append("  kills shatter into frost")
    return lines


# --- drops ----------------------------------------------------------------------------
def maybe_drop(rank, source=None, rng=None):
    rng = rng or _DROP_RNG
    ch = GEM_DROP_CHANCE.get(rank, 0.0) * SOURCE_CHANCE_MULT.get(source, 1.0)
    if ch <= 0 or rng.random() >= ch:
        return None
    grade = rng.choices(GRADES, weights=[GRADE_WEIGHT[g] for g in GRADES])[0]
    boost = SOURCE_GRADE_BOOST.get(source, 0) + (1 if rank == "boss" else 0)
    grade = GRADES[min(len(GRADES) - 1, GRADES.index(grade) + boost)]
    return make_gem(grade=grade, rng=rng)


# --- gem veins (glittering rocks in the Realm you mine with F) ------------------------
VEIN_BIOMES = {"highlands": ("topaz", "diamond", "sapphire"), "desert": ("topaz", "ruby", "amethyst"),
               "tundra": ("sapphire", "diamond"), "cave": ("amethyst", "onyx", "emerald"),
               "ashlands": ("ruby", "onyx"), "jungle": ("emerald", "amethyst")}
VEINS_PER_BIOME = 7
VEIN_CHARGES = 2
VEIN_MINE_TIME = 1.4     # seconds of channelling (stay close)
VEIN_RADIUS = 64         # px from the vein to start / keep mining
VEIN_GRADES = (("chipped", 62), ("flawed", 32), ("regular", 6))


def vein_stone(vein, rng=None):
    rng = rng or _DROP_RNG
    kind = rng.choice(vein["kinds"])
    grade = rng.choices([g for g, _w in VEIN_GRADES], weights=[w for _g, w in VEIN_GRADES])[0]
    return make_gem(kind, grade, rng=rng)


# --- the Anvil -------------------------------------------------------------------------
def _ingots(bag):
    return [it for it in bag if it is not None and it.slot == "material" and it.shape == "ingot"]


def stonework_options(player, limit=4):
    """The Anvil's stonework the player can do right now: set a backpack stone into the
    EQUIPPED weapon, combine 3 same stones into the next grade, pry a stone out.
    Each: {kind, label, ...} - apply with apply_stonework()."""
    bag = list(player.backpack)
    ingots = _ingots(bag)
    w = getattr(player, "weapon", None)
    out = []
    seen = set()
    if w is not None and free_sockets(w) > 0:
        for it in sorted((i for i in bag if is_gem(i)), key=lambda i: -GRADES.index(i.gem_grade)):
            key = (it.gem_kind, it.gem_grade)
            if key in seen:
                continue
            seen.add(key)
            cost = SET_INGOTS[it.gem_grade]
            if len(ingots) < cost:
                continue
            extra = f" ({cost} Ingot{'s' if cost > 1 else ''})" if cost else ""
            out.append(dict(kind="set", gem=it, ingots=ingots[:cost],
                            label=f"Set {it.name} into {w.name}{extra}"))
    groups = {}
    for it in bag:
        if is_gem(it) and it.gem_grade != GRADES[-1]:
            groups.setdefault((it.gem_kind, it.gem_grade), []).append(it)
    for (k, g), its in sorted(groups.items(), key=lambda kv: -GRADES.index(kv[0][1])):
        if len(its) < 3:
            continue
        cost = COMBINE_INGOTS.get(g, 0)
        if len(ingots) < cost:
            continue
        nxt = GRADES[GRADES.index(g) + 1]
        extra = f" + {cost} Ingot" if cost else ""
        out.append(dict(kind="combine", use=its[:3], ingots=ingots[:cost], grade=nxt, gem_kind=k,
                        label=f"Combine 3 {stone_name(k, g)}{'' if k == 'topaz' else 's'}{extra} -> "
                              f"{stone_name(k, nxt)}"))
    if w is not None and stones_in(w):
        k, g = stones_in(w)[-1]
        out.append(dict(kind="pry", label=f"Pry the {stone_name(k, g)} out of {w.name} (it shatters)"))
    return out[:limit]


def _take(bag, it):
    for i, b in enumerate(bag):
        if b is it:
            bag.pop(i)
            return True
    return False


def apply_stonework(player, opt):
    """Returns (ok, message, colour). The weapon keeps its stones in Item.gems."""
    bag = player.backpack
    w = player.weapon
    kind = opt["kind"]
    if kind == "set":
        it = opt["gem"]
        if w is None or free_sockets(w) <= 0:
            return False, "No free socket on that weapon.", (220, 150, 90)
        if not any(b is it for b in bag) or not all(any(b is x for b in bag) for x in opt["ingots"]):
            return False, "That stone isn't in your backpack any more.", (220, 150, 90)
        _take(bag, it)
        for x in opt["ingots"]:
            _take(bag, x)
        w.gems = list(stones_in(w)) + [(it.gem_kind, it.gem_grade)]
        w.gems = [list(g) for g in w.gems]
        n = counts(w)[it.gem_kind]
        tag = f" {bond(n)}!" if n >= 2 else ""
        return True, f"CLANG! The {it.name} sits snug in {w.name}.{tag}", color_of(it.gem_kind)
    if kind == "combine":
        use = opt["use"]
        if not all(any(b is x for b in bag) for x in list(use) + list(opt["ingots"])):
            return False, "Those stones aren't in your backpack any more.", (220, 150, 90)
        for x in list(use) + list(opt["ingots"]):
            _take(bag, x)
        res = make_gem(opt["gem_kind"], opt["grade"])
        bag.append(res)
        return True, f"Three stones, one hammer, one {res.name}.", color_of(res.gem_kind)
    if kind == "pry":
        stones = stones_in(w) if w is not None else []
        if not stones:
            return False, "Nothing to pry out.", (220, 150, 90)
        k, g = stones[-1]
        w.gems = [list(s) for s in stones[:-1]]
        return True, f"Crack! The {stone_name(k, g)} shatters as it comes free.", (200, 200, 210)
    return False, "...", (220, 150, 90)

# 02 — Classes, Stats, Combat, and Leveling

Scope: the 8 playable classes and their stat identity, the combat resolution model (bullets, status effects, telegraphed abilities), and per-class level-up growth. This is the player-facing "how does it feel to play each class" layer, built directly on top of `01-core-architecture.md`'s formulas.

---

## 1. Eight classes, real stat profiles

### What it is

8 playable classes (Wizard, Archer, Warrior, Priest, Rogue, Necromancer, Paladin, Assassin), each with a distinct base ATT/DEF/SPD/DEX/VIT/WIS profile, a starter weapon + starter ability, and (per file `04`) a distinct fire-pattern/projectile shape. Classes are also grouped into 3 armor archetypes — Heavy (Warrior/Paladin), Light (Archer/Assassin/Rogue), Robe (Wizard/Necromancer/Priest) — which drives both which armor pool a class's drops come from and (later) how HP/MP scale on level-up.

### Why/how it was chosen

This is the project's foundation — present since the very first working version (the README's own "v0.1 — first working pass" credits "8 classes, each with a real RotMG stat profile and distinct weapon behaviour" as one of the original five bullet points). No single memory quote records the class list being *chosen* over some other set — it's a direct, acknowledged homage to RotMG's own 8-class roster, stated as the project's premise from the start.

### Implementation detail (verified against current `game/entities.py:28-56`)

```python
CLASS_BASE = {
    "wizard":      hp=100, mp=100, att=10, deF=5,  spd=25, dex=15, vit=10, wis=30, growth=["wis","att","vit","wis","dex"]
    "archer":      hp=90,  mp=70,  att=15, deF=10, spd=35, dex=25, vit=15, wis=10, growth=["dex","att","spd","vit","dex"]
    "warrior":     hp=130, mp=50,  att=15, deF=25, spd=20, dex=15, vit=25, wis=5,  growth=["deF","vit","att","deF","spd"]
    "priest":      hp=100, mp=120, att=5,  deF=10, spd=25, dex=10, vit=15, wis=35, growth=["wis","vit","wis","deF","dex"]
    "rogue":       hp=85,  mp=60,  att=12, deF=8,  spd=40, dex=30, vit=12, wis=8,  growth=["dex","spd","att","dex","vit"]
    "necromancer": hp=95,  mp=110, att=8,  deF=6,  spd=22, dex=12, vit=12, wis=32, growth=["wis","att","wis","vit","dex"]
    "paladin":     hp=140, mp=80,  att=10, deF=22, spd=18, dex=12, vit=22, wis=18, growth=["deF","vit","wis","deF","vit"]
    "assassin":    hp=80,  mp=65,  att=14, deF=6,  spd=38, dex=32, vit=10, wis=8,  growth=["dex","att","dex","spd","vit"]
}
```
Each class's flavor text (`CLASS_DESC`) states its identity directly, e.g. Wizard: *"Glass cannon. High WIS -> fast MP regen for spammable magic missiles."*; Paladin: *"Tanky support. High DEF/VIT, mace hits heal on contact."*

`CLASS_ARMOR_ARCHETYPE` (`game/items.py:353`) maps each class name to `"heavy" | "light" | "robe"` — this single mapping is reused, unmodified, by THREE independent systems built at different times: which armor table a class's drops pull from (Batch 1, item drops), per-class HP/MP level-up growth (Batch 1 Section L, see below), and cross-class armor drop resolution (a class can drop another class's gear ~40% of the time, resolved to the *dropped* class's own archetype, not the killer's).

The `growth` list per class is a 5-entry (with intentional repeats) list of "signature stats" — originally just a rotation (one stat per level-up, cycling), later reinterpreted (Section L, see part 3 below) as a *de-duplicated set* of "this class's emphasized stats," which grow faster on every level rather than one at a time.

### Unity rebuild prompt

> Define an 8-entry data table (ScriptableObject or plain data class) for the classes Wizard/Archer/Warrior/Priest/Rogue/Necromancer/Paladin/Assassin, each with: base HP, base MP, base ATT/DEF/SPD/DEX/VIT/WIS (reproduce the exact numbers above to preserve the same relative class balance), an armor archetype tag (Heavy/Light/Robe — Warrior+Paladin heavy, Archer+Assassin+Rogue light, Wizard+Necromancer+Priest robe), and a small ordered list of that class's "signature" stats. Preserve the intent that this archetype tag is reused verbatim by the loot system, the armor-drop pool, and the per-level stat-growth system — one source of truth, not three separate class-identity tables that could drift out of sync.

---

## 2. Combat resolution: bullets, hits, and per-class fire patterns

### What it is

All damage in the game — player weapon fire, enemy fire, melee "swings," ability impacts — resolves through one shared `Bullet` object type and a single `hit_test()` swept-collision check, even for classes whose real-world equivalent (a sword swing) isn't literally a projectile. Melee classes fire a very-short-lived, very-short-range `Bullet` instead of running separate melee-hitbox code.

### Why/how it was chosen

Not attributed to an explicit standalone user request in memory — it reads as an original engineering decision (unifying melee and ranged onto one collision pipeline) that later features explicitly leaned on and benefited from: the destructible dungeon Obstacle's hit-resolution is described in memory as "reusing the exact same `Bullet.hit_test` pipeline that already resolves melee-vs-ranged uniformly — covers both attack types for free, exactly as the plan intended," i.e. the unification was already in place and a later feature (Batch 1 Section C) explicitly relied on it rather than writing separate logic.

### Implementation detail (verified against current `game/entities.py`)

`class Bullet` (`game/entities.py:1176`), constructed via `_mk_bullet(pos, direction, speed, dmg, color, owner, pierce, radius, lifetime, motion, status_effect, shape)` (`entities.py:1153`):
- `owner`: `"enemy"` for enemy-fired bullets, or the firing player's network `pid` for player-fired bullets — this single field is how co-op correctly attributes kill credit/XP/loot to whichever player actually landed the shot.
- `hit_test(target_pos, target_radius)` (`entities.py:1219`): **swept** (segment-based) collision — checks whether the bullet's travel *this tick* (from `prev_pos` to `pos`) passed within `(bullet.radius + target.radius)` of the target, not just an end-of-tick point check. This specifically fixes bullet-tunneling at the server's lower (30Hz) tick rate, where a fast bullet's per-tick movement could otherwise exceed its own hit radius and pass clean through a point-blank target before ever being checked (documented as a real, found-and-fixed bug in the project's history).
- `motion` field: `"straight"` (default) or `"boomerang"`. A boomerang bullet flies outward normally until `elapsed_frac >= BOOMERANG_TURN_FRAC` of its total lifetime has passed, then smoothly lerps its velocity toward "back to the origin point" over a `BOOMERANG_TURN_RATE`-controlled blend (`entities.py:1206-1217`) — a genuinely different projectile *behavior*, not a different sprite on the same straight-line motion. Exactly one existing UT weapon per class is tagged with this motion.
- `status_effect` field: `None | "bleed" | "burn" | "vulnerable"` — applied to whatever the bullet hits, on a successful PLAYER-bullet hit only (see part 3 below).
- `shape` field: a pure *rendering* hint (`"bolt"/"arrow"/"blade"/"bone"/"holy"/"star"/"orb"`, see `05-art-vfx-pipeline.md`) with zero effect on collision/damage — purely cosmetic per-class identity.

**Per-class fire pattern** (`RealmSim.player_fire(p, direction)`, `game/realm_sim.py:1433`) — this is where each class's *feel* actually lives:
- **Archer**: fires **3 simultaneous bullets** in a fan (`direction.rotate(-6/0/+6)` degrees), each doing `dmg / ARCHER_MULTISHOT_DMG_DIVISOR` (currently `3.0`). This divisor exists specifically to correct a real balance bug: without it, 3 simultaneous full-damage bullets is a flat 3x DPS multiplier no other class gets — measured at ~88 DPS vs. 17-38 DPS for everyone else at matching gear. The divisor was tuned to land Archer's *realized* DPS at ~29, matching real RotMG where Archer is mid-pack (tied 5th of 8), not top — the spread itself (the actual gameplay identity) is untouched; only the compensating per-bullet damage was changed.
- **Warrior/Paladin** (melee): a single short-range, short-lifetime bullet (`lifetime=0.4s` normally, extended to `0.9s` if it's a boomerang UT — otherwise there'd be no time left in its short life to ever curve back) at `dmg * 1.4` (melee classes hit harder per-swing to compensate for needing to be in contact range). Also fires a `"melee_swing"` VFX event for a visible swing effect.
- **Rogue/Assassin** (melee): similar short-range/short-lifetime pattern, `lifetime=0.22s` normally.
- **Priest**: fires a piercing bolt (`pierce=PRIEST_PIERCE` = 2), **always** — in real RotMG, Priest's wands innately pierce; this project makes that always-on rather than gating it behind a rare UT (as Wizard/Necromancer do), giving Priest a real mechanical distinction from the Wizard/Necromancer fallback branch rather than behaving identically to them.
- **Wizard/Necromancer** (fallback branch): a single bolt, `pierce=2` only if the equipped weapon `is_ut`, otherwise `pierce=0`.

### Unity rebuild prompt

> Build one unified `Projectile` class used for every attack in the game, including melee — a "sword swing" is just a very-short-range, very-short-lifetime projectile with a large hit radius, not a separate hitbox system. Give it: an owner id (for kill-credit attribution in multiplayer), a swept/segment-based hit test (check the full line the projectile traveled this physics step against each potential target's collision radius, not just its end-of-step position — this matters at any fixed server tick rate lower than your render rate), a motion mode (straight, or "boomerang": travel outward, then past some fraction of its lifetime smoothly steer back toward its origin point), an optional status-effect tag, and a purely cosmetic shape/visual tag with zero gameplay effect. Then implement each class's fire pattern as a small, explicit per-class function (not one generic formula) so each class's identity is hand-authored: Archer fires 3 simultaneous projectiles in a narrow fan at reduced per-shot damage (tune the divisor so total sustained DPS lands mid-pack among your 8 classes, not top); Warrior/Paladin and Rogue/Assassin fire short-range/short-lifetime melee "swings" at a damage bonus to compensate for needing to be close; a support class (your Priest analog) innately pierces multiple targets per shot as a baseline mechanical identity, not a rare unlock.

---

## 3. Status effects: bleed, burn, vulnerable (Batch 1 Section H)

### What it is

3 of each class's 4 untiered (UT) weapons apply a persistent effect on hit, applied via the `status_effect` field above, on top of the 4th UT already having the boomerang motion — meaning **every one of a class's 4 UTs is mechanically distinct**, not "one special UT and three reskinned tiered weapons with a rare name."
- **Bleed**: a damage-over-time tick, `BLEED_DURATION=4.0s`, ticking at `BLEED_DPS_FRACTION=0.35` of the triggering hit's own damage, per second.
- **Burn**: a shorter, harder-hitting DoT — `BURN_DURATION=3.0s` at `BURN_DPS_FRACTION=0.45` — deliberately a different *feel* (shorter/punchier) from bleed despite sharing the identical underlying timer mechanism.
- **Vulnerable**: `VULNERABLE_DURATION=5.0s`, multiplies ALL incoming damage to the target by `VULNERABLE_MULT=1.3` while active — a reinterpretation of "armor pierce" for a target type (enemies) that has no DEF stat to actually reduce.

### Why/how it was chosen

Framed in the master plan as "bleed/burn/vulnerable status effects on UTs" — a planned section (H) of the original multi-part feature plan, not a spontaneous mid-session user ask; the specific numeric tuning (duration/DPS-fraction/multiplier) is presented in memory as implementation judgment, not wiki-sourced, and is documented as such rather than misattributed.

### Implementation detail

- `game/realm_sim.py`: `BLEED_UT_NAMES`/`BURN_UT_NAMES`/`VULNERABLE_UT_NAMES` are built once at module load by pattern-matching each class's UT-weapon list by index (`uts[0]`→bleed, `uts[2]`→burn, `uts[3]`→vulnerable; index 1 is separately claimed by the boomerang mapping) — the same "match a UT's fixed table position, not by hardcoded name" pattern is reused across 3 different UT-based systems (boomerang motion, projectile shape flavor is separate, status effects), keeping all class-specific special-casing in small declarative dicts built once, rather than scattered `if name == "..."` checks.
- `Enemy` (`game/entities.py`) carries `bleed_time/bleed_dps`, `burn_time/burn_dps`, `vulnerable_time/vulnerable_mult`, and `status_source_pid` (who applied it, for DoT kill-credit). All three timers tick down **unconditionally** in `Enemy.update()` — even while frozen — matching the convention that a DoT/debuff keeps counting through a stun rather than being paused by it.
- **Damage application happens in `RealmSim.update()`'s enemy loop, not inside `Enemy.update()` itself** — this is a deliberate architectural split: `Enemy.update()` has no access to the `players` dict needed to correctly attribute a DoT kill, so the tick-damage application (`e.take_damage(dps*dt)`) and the resulting `self._reward(e, players.get(e.status_source_pid))` kill-credit call both live one level up, in the sim's own tick loop, right after each enemy's own `update()` call — with an added `if not e.alive: continue` guard immediately after, since a mid-loop DoT kill is a new code path bullet-kills (resolved in a separate pass) never had to handle.
- `Enemy.take_damage()` multiplies incoming damage by `vulnerable_mult` while `vulnerable_time > 0`, verified numerically: 10 base damage becomes 13 while vulnerable (`10 * 1.3` exactly).

### Unity rebuild prompt

> Give your enemy/monster base class three independent timed-effect fields — a damage-over-time state (duration + damage-per-second), a second, shorter/harder DoT variant (different pacing, same underlying mechanism), and a temporary incoming-damage multiplier. All three timers count down every frame regardless of any other stun/freeze state the entity is in. Apply the periodic DoT damage from your top-level simulation loop (which has access to full player/attribution context), not from the enemy's own per-entity update method, and store which attacker applied the effect so a kill from a DoT tick correctly credits that attacker's XP/loot — including a guard so an enemy that dies mid-tick-loop from a DoT doesn't also fall through whatever separate "resolve this frame's direct hits" logic runs afterward. Reserve 3 of your rare/named "unique" weapon variants per class for these three effects respectively, so a full unique-weapon set for one class always covers 3 distinct status effects plus one distinct projectile-motion variant (see Boomerang above) — never more than one unique weapon that's mechanically just a bigger number.

---

## 4. Abilities: 7 effect kinds, 4 of them telegraphed (Batch 1 Section J)

### What it is

Each class has one equippable ability (Space bar to cast, on a global cooldown + its own MP cost). 7 distinct `effect` kinds exist: `nova`, `chain`, `drain`, `freeze` (all damage-dealing, AoE-ish, and — critically — **telegraphed**, not instant), plus `heal`, `haste`, `shield` (instant support effects on allies, since an ally can't "dodge" being helped).

### Why/how it was chosen

The original plan explicitly offered two resolution styles for the 4 damage abilities: full traveling, aimable, wall-colliding skillshot projectiles, or a telegraphed point-detonation (a visible warning marker, then an unavoidable-if-you-stand-still impact after a short delay). The project chose telegraphing, documented explicitly as a scope/engineering-cost decision: *"a much smaller/safer engineering lift than reworking these into aimed, dodgeable, wall-colliding projectiles. If the user specifically wants true projectile travel later, that's a bigger follow-up, not a small tweak."* This is a good example of the project's general pattern of choosing the simpler mechanism that still satisfies the actual design goal (giving the player *some* real counterplay window against these abilities) rather than the maximal version.

### Implementation detail (verified against current `game/realm_sim.py:1501-1621`)

- `TELEGRAPH_DELAY = 0.45` seconds between cast and impact.
- Casting one of the 4 damage effects does NOT resolve anything immediately: it deducts MP, sets the ability's cooldown, immediately fires a `f"{effect}_warning"` VFX event at the target point (a visibly growing ring, over the same `TELEGRAPH_DELAY` window, showing roughly the real impact radius), and appends a dict to `self.pending_ability_effects` — a list that (deliberately) is **not** cleared every tick like the game's other per-tick event lists, since a pending effect must survive across multiple ticks until its timer expires.
- `_resolve_pending_ability_effects(dt)` runs once per `update()` tick (before bullet resolution), ticking every pending effect's stored timer and calling `_impact_ability_effect(pe)` — which holds the actual damage/freeze/chain/lifesteal logic — the instant a timer expires.
- Effect specifics:
  - **Nova**: flat AoE damage to every enemy within `NOVA_RADIUS` (110) of the target point.
  - **Chain**: hops between up to `CHAIN_HOPS` (4) enemies, each within `CHAIN_RANGE` (150) of the previous hit, always picking the nearest un-hit candidate — a literal "lightning chain," not a flat-radius AoE.
  - **Drain**: AoE damage like nova, but the caster is healed for 50% of the total *real* (post-mitigation) damage dealt across every enemy hit — lifesteal scales off what the ability actually dealt, not its raw configured magnitude.
  - **Freeze**: AoE damage plus sets `frozen_time` on every enemy hit (a genuine crowd-control root, not just cosmetic).
  - **Heal/Haste/Shield**: fully instant, radius-checked against `allies` (self in single-player, every co-op teammate in the same zone) within `SUPPORT_RADIUS` (130).
- **Damage magnitude rebalance**: nova/chain/drain/freeze magnitudes were bumped ~25% across the 3 classes that actually have damage abilities (Wizard/Necromancer/Archer), justified explicitly as compensation for the telegraph making these dodgeable now (a landed cast needed a corresponding damage increase to still feel like a real payoff) — again documented honestly as feel-based tuning, not a wiki-verified pass.

### Unity rebuild prompt

> Implement damage-dealing abilities as telegraphed point-detonations, not instant AoEs and not traveling skillshots: on cast, immediately deduct the resource cost, start the cooldown, spawn a visible warning indicator at the target point that visibly grows toward the real impact area over a short fixed delay (roughly half a second), and queue the actual effect to resolve after that same delay — store the queued effect in a persistent list that survives across multiple simulation ticks (not one that's cleared every tick), and resolve+remove each entry the instant its timer expires. Implement at least 4 distinct AoE-flavor variants sharing this same telegraph mechanism (a flat-radius nova, a bounces-between-nearest-targets chain, an AoE-plus-self-heal drain, and an AoE-plus-crowd-control freeze) so telegraphing feels like a shared *resolution style* across a whole family of abilities, not a one-off special case. Keep pure support effects (heal/haste/a damage shield) fully instant with no telegraph, since an ally being helped has no reason to need a dodge window.

---

## 5. Per-class level-up growth (Batch 1 Section L)

### What it is

Leveling up no longer gives every class an identical, generic stat bump. HP/MP growth is keyed off the class's armor archetype (Heavy/Light/Robe — the *same* mapping used for armor drops, see part 1); every one of the 6 core stats rolls a small random amount on every level, with a class's own "signature" stats rolling a bigger range than the rest.

### Why/how it was chosen

Explicitly requested together with the potion system ("K + L") because the user judged them "related and not complicated" and wanted both done in the same pass — one of the few places in the project's memory where a *combination/scoping* decision, not just a feature ask, is directly attributed to the user. The growth design itself is a deliberate reuse of already-established project data (the archetype grouping, the `growth` signature-stat list) rather than inventing a new taxonomy — an explicit design principle the memory calls out: *"grounded the design in this project's OWN already-verified, internally-consistent class-identity data... rather than inventing arbitrary numbers."*

### Implementation detail (verified against current `game/entities.py:58-66, 146-174`)

```python
HP_GROWTH_BY_ARCHETYPE = {"heavy": (16, 22), "light": (12, 17), "robe": (9, 13)}
MP_GROWTH_BY_ARCHETYPE = {"heavy": (4, 7),  "light": (5, 8),   "robe": (7, 11)}   # inverse of HP
SIGNATURE_STAT_GROWTH = (1, 3)   # a class's own emphasized stats
OTHER_STAT_GROWTH     = (0, 1)   # every other stat, still ticks up a little
```
On every level-up (`Player.gain_xp()`): roll a fresh `HP_GROWTH_BY_ARCHETYPE`/`MP_GROWTH_BY_ARCHETYPE` amount (fully heal to the new max), then for each of the 6 stats, roll `SIGNATURE_STAT_GROWTH` if that stat is in the class's (de-duplicated) `growth` set, else `OTHER_STAT_GROWTH`. Verified end-to-end to level 20: a Warrior ends at 489 HP / 158 MP vs. a Wizard's 314 HP / 279 MP (a ~175 HP gap — genuine tank-vs-glass-cannon differentiation, not cosmetic), and each class's own signature stats clearly outgrow its non-signature ones by the level cap (e.g. Assassin's DEX 75 + SPD 86 vs. its own WIS 21).

### Unity rebuild prompt

> Drive HP/MP growth-per-level off the same Heavy/Light/Robe (or equivalent) archetype tag your armor-drop system already uses, with distinct (min,max) random-roll ranges per archetype for HP and a roughly *inverse* set of ranges for MP (tanky archetypes get more HP growth but less MP growth per level, and vice versa) — reroll and fully restore to the new max on every level-up rather than a flat fixed increment. Also roll a small random amount for EVERY core stat on every level (not just one rotating stat per level), with each class's own small set of "signature" stats (whichever 2-3 stats its starting profile already emphasizes) rolling a meaningfully bigger range than its other stats — verify by simulating to your level cap that two classes end up visibly, numerically differentiated (a tank ending up with dramatically more HP than a glass-cannon class, and each class's own signature stats visibly outpacing its weak stats), not just cosmetically different starting numbers that converge over time.

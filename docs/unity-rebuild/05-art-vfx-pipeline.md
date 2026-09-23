# 05 — The Hand-Painted Art & VFX Production Pipeline

Scope: not a catalog of every individual sprite/tile/decoration ever painted (later batches added many more assets using this same pipeline — that's out of scope here) — this file documents the **technique itself**: how "hand-painted-looking" 2D art is actually produced in this from-scratch-code, no-external-assets project, why the technique changed once mid-project, and the production conventions that were established and then followed for every asset afterward. This groundwork is foundational even though many of the individual assets it produced came later chronologically.

---

## 1. The starting point: procedural ASCII-grid sprites with auto-shading

### What it is

Every sprite in the game — player classes, enemies, bosses, tiles, decorations, item icons — is fundamentally described as a small ASCII "pixel grid" (a list of equal-length strings, one character per logical pixel) plus a flat palette dict mapping each character to a base RGB color. A single shared rendering function, `sprites._autline_and_render(grid, palette, scale, shaded=True)`, turns that flat description into a shaded, outlined sprite — automatically. No sprite's *base* authoring step ever needs to hand-place a highlight or shadow pixel.

### Why/how it was chosen

This was the ORIGINAL procedural-sprite system, present before any hand-painting effort began — the project's "no external assets, everything is code-generated" premise required it. The critical discovery (documented in project memory as a genuine "aha" moment mid-project, detailed in part 2 below) was realizing this same function was quietly *already* the actual source of the best-looking hand-authored sprite's quality — meaning the "procedural fallback" and "the good art" were never two different things, just two different inputs to the same renderer.

### Implementation detail (verified against current `game/sprites.py:110-151`)

```python
def _autline_and_render(grid, palette, scale, shaded=True):
    # pass 1: black outline wherever a filled cell touches an empty/out-of-bounds cell
    #   (a 4-directional neighbor check per filled cell — this produces a full,
    #    continuous 1px silhouette outline automatically, from the grid shape alone)
    # pass 2: colored pixels, lightly shaded for a sense of volume:
    #   - a soft vertical gradient (top of the sprite ~14% brighter, bottom ~10%
    #     darker than the palette's flat base color — "lit from above")
    #   - an additional rim-light boost (~16% brighter) on any pixel whose
    #     left or top neighbor is empty (the silhouette's top/left-facing edges)
```
- The outline pass needs no hand-drawn border in the grid at all — a filled character adjacent to a blank one automatically becomes a black-outlined edge. This is what makes every sprite's silhouette read cleanly against any background, with zero authoring effort per-asset.
- The shading pass is a *pure function of vertical position within the grid* plus *whether this pixel sits on the silhouette's own top/left edge* — never a function of hand-chosen "this part is in shadow" authoring. One flat color per material region in the grid is all an author ever specifies; the gradient and rim-light are entirely automatic.
- `_upscale(surf, passes, final_size)` (`sprites.py:102`) runs the base render through `passes` rounds of Scale2x/AdvMAME2x smart pixel-art upscaling (`_scale2x`, `sprites.py:71` — extends diagonal edges based on neighboring pixels, rather than naive nearest-neighbor block replication) before a final `smoothscale` down to the exact target on-screen size. This is a real *quality* pass, not just a resize: supersampling at a higher logical resolution then smart-downscaling produces meaningfully smoother diagonal edges than rendering directly at final size.

### Unity rebuild prompt

> Build your base 2D sprite-authoring format as small ASCII/character grids (a list of equal-length strings) paired with a flat character→color palette dictionary — never a raw pixel-painted source image as the *authored* format. Write one shared renderer that takes a grid+palette and produces the final sprite in two automatic passes: first, outline every filled cell that borders an empty cell or the grid edge (a simple 4-neighbor check, giving every silhouette a continuous border with zero manual outline-drawing); second, shade every filled pixel by a smooth function of its vertical position (brighter near the top, darker near the bottom — "lit from above") plus an extra rim-light boost specifically on pixels bordering an empty top or left neighbor (the silhouette's lit-facing edges). An asset's author should only ever need to specify ONE flat base color per distinct material/object in the grid — never a separate "highlight" or "shadow" variant character for the same material; the renderer supplies all of the sense-of-volume automatically. Render at a supersampled base resolution, run it through a smart pixel-art upscaling pass (an edge-aware algorithm like Scale2x/AdvMAME2x, not naive nearest-neighbor scaling) one or more times, then downscale smoothly to the final on-screen size — this two-step supersample-then-smart-downscale produces noticeably cleaner diagonal edges than rendering directly at the target size.

---

## 2. The mid-project technique correction: hand-authored assets were flat, not shaded

### What it is

A real, documented mid-project quality regression and its root-cause fix: an initial batch of hand-authored replacement sprites (painted directly, pixel-by-pixel, via an external drawing tool) used **flat, hand-picked colors only** — no gradient, no rim-light — and looked visibly worse than the ORIGINAL procedural fallback sprites, which had always rendered through `_autline_and_render`'s automatic shading. The fix was not "paint more carefully" — it was realizing hand-painting should never have bypassed the shader in the first place.

### Why/how it was chosen

The user's own words, as recorded in memory, are what triggered the investigation: one class's redo still looked "trash" even after several manual iteration rounds, and separately the user asked for the standard the ONE genuinely good-looking asset (the first-painted class) had set — "great detail as wizard is" — to be applied to everything else. Investigating *why* that one asset looked distinctly better (by sampling its actual pixel data) found it had never been flat-painted at all; its quality came entirely from the shared shading function, which every OTHER hand-painted asset up to that point had accidentally bypassed by painting flat colors directly instead of routing through it.

### Implementation detail: the corrected production method

Author a grid+palette exactly as in part 1 (in a small standalone Python script, not inside the game's own source files), then render it through the *same* `_autline_and_render`+`_upscale` pipeline the procedural fallback already uses, and save the result as a PNG:
```python
base = sprites._autline_and_render(GRID, pal_rgb, scale=4, shaded=True)
out  = sprites._upscale(base, passes=1, final_size=(128, 128))   # or the asset's real target size
pygame.image.save(out, out_path)
```
This is dramatically faster than manual pixel-by-pixel painting AND higher quality (automatic gradient+rim-light instead of hand-picked flat regions) — it became the standing production method for every asset painted from that point forward, fully replacing the earlier pixel-by-pixel tool workflow.

**Two "clean style" rules were established alongside this correction**, both directly traced to specific real defects the user flagged:
1. **One flat color per material, never a manual shade-variant character.** Hand-adding a second, slightly-lighter or slightly-darker character for the "same" material (to fake a highlight or shadow blip) *double-shades* on top of the auto-shader's own gradient, producing a visibly busier, more cluttered result than a clean asset with fewer, purely-flat material regions. Rule going forward: skin, hair, main garment, weapon, at most one accent/glow color, at most one signature trim/stripe/gem — never a second variant of an already-used material color.
2. **No near-black fill color for a large region.** A fill color too close to the automatic outline color makes the outline effectively invisible against it, so the shape reads as an undifferentiated black blob with no visible edge — the specific, recurring real symptom was boots/dark-region colors that "looked unfinished" because the boundary between "boot" and "outline" simply wasn't visible. Rule: keep every fill color's total RGB sum meaningfully above the outline color's own (in practice, a floor helper function pushes any too-dark palette color up to a minimum brightness before rendering, rather than requiring every author to hand-check this per palette).

A third, unrelated real bug was caught in the same pass: a hand-authored grid's left/right side column ranges weren't true mirror images of each other, producing a visibly asymmetric silhouette — a reminder that hand-authored grids need an explicit mirror-symmetry check when there's no automated mirroring helper generating both sides.

### Unity rebuild prompt

> If your project supports BOTH a procedural/generated art path and hand-authored replacement art for the same sprites, make sure hand-authored art is produced by feeding the SAME shading/rendering pipeline your procedural path already uses — never let "hand-authored" quietly come to mean "flat colors with no automatic shading applied," or your hand-authored assets will look worse than your procedural fallback despite far more manual effort. When you discover one asset in a set looks meaningfully better than its siblings for reasons you can't immediately explain, actually inspect its underlying data (sample its real pixel/color values) rather than guessing — the actual cause may be a pipeline difference, not an authoring-skill difference. Establish and enforce two concrete style rules for any hand-authored flat-color-region art under an auto-shader: never add a second, slightly-different-shade variant color for the same material (it double-shades against the automatic gradient and reads as visual clutter), and never let a large fill region's color sit close enough to your automatic outline color that the outline becomes invisible against it (enforce a minimum-brightness floor on dark fill colors programmatically, rather than relying on each author to eyeball it).

---

## 3. Per-character face convention and asset-identity rules

### What it is

Two standing rules governing how individual characters/creatures are made to feel distinct from one another, established directly from user feedback and then applied consistently to every subsequent character asset:
1. **Same eye-drawing shape/position, different iris + brow color per character.** Every character's eyes are drawn at the same relative position/shape in its grid, but each gets its own unique iris color (and brow-mark color, where headwear allows brows to show) — faces are recognizably differentiated without needing an entirely bespoke facial structure per character.
2. **No silhouette reuse without a real, distinct twist.** An asset that's just an existing character/creature's shape re-rendered with a different palette (a "reskin") was called out as insufficient — every character needs its own genuinely distinct silhouette, or (for weapons/accessories specifically) at minimum its own distinct held-item shape layered onto a shared base pose, not merely a different color of an already-used shape.

### Why/how it was chosen

Directly attributed to explicit user feedback recorded in memory: a request that future classes each get a genuine "twist" to their weapon specifically (not just recolored), plus a broader later correction that flagged silhouette reuse as a real quality problem across an entire batch of enemy redesigns, which triggered a project-wide policy (not a one-off fix) against it. The face/eye convention is presented as the answer to a real, practical tension this created: full bespoke facial structure per character is expensive, but faces being *recognizably* different from each other still matters — the fixed-shape/varied-color compromise was the resolution.

### Implementation detail

- Character face convention: a single shared "eye slot" position and shape per character archetype (e.g. one position for humanoid classes), with the palette dict supplying a different iris color (and brow-mark color if the headwear/hood design allows brows to be visible) per individual character — reused across all 8 player classes and then again across enemy/boss redesigns.
- "Every asset gets a unique twist": weapon shapes specifically were called out as needing individual attention even when a character's overall silhouette shares a family resemblance with another (e.g. two heavy-armor classes) — e.g. distinct weapon *and* distinct held-shield-vs-no-shield as the differentiator between two otherwise-similar armored classes, not just a different tint of the same sword shape.
- A face-visibility rule that persisted across multiple hood/mask designs: even a character with a lower-face mask/wrap must keep eyes+brows+forehead visible above it — "face visible" was treated as a hard constraint independent of how much of the rest of the face a given costume design covers.

### Unity rebuild prompt

> When authoring a roster of characters/creatures that need to read as visually distinct at a glance (a class roster, a monster bestiary), never ship a "new" entry that's just an existing entry's exact silhouette with a new color palette — give every entry at least one genuinely distinct shape element (its held weapon, its headwear, a body-shape detail), not only a recolor. To keep this tractable at scale, standardize a shared facial convention across your whole roster: the same eye position and shape for every character, but a unique iris color (and, where the design allows, a brow-mark color) per character — this gives cheap, systematic face differentiation without requiring a bespoke facial structure for every single entry. Treat "the eyes, brows, and forehead must stay visible" as a hard constraint on any headwear/mask design, independent of how much of the rest of the face that design otherwise covers.

---

## 4. Decoration props and the tile-id allocation pattern (foundational technique, used across every later decoration batch)

### What it is

Ambient decoration objects (rocks/bushes/trees scattered across the open world, torches/crates/idols inside dungeons, banners/statues inside the Nexus, gold/pillars/bookshelves inside the Vault) are painted with the exact same grid+`_autline_and_render`+`_upscale` pipeline as characters, then wired into the tile system as new tile-type integers — and specifically allocated with **deliberately large, unused numeric gaps** between each new decoration category's id block, rather than packed tightly after the last-used id.

### Why/how it was chosen

This project has no git repository and, for extended periods, ran two independent Claude Code sessions editing the same shared files concurrently (one on gameplay, one on art) — a real, load-bearing environmental constraint, not a hypothetical. Tile-id collisions between the two sessions' concurrent work were a genuine, anticipated risk: if the art session's new decoration ids picked up immediately after the last gameplay-defined id, any gameplay-side addition of a new tile type in the interim would silently collide with (or be silently pre-empted by) the art session's own allocation. Spacing allocations out with a wide unused buffer between blocks was a deliberate, explicit hedge against exactly this — documented directly in code comments at each allocation site (e.g. "starts at 500, NOT right after the last shared-enum value — deliberately leaves a large gap for the shared tile-enum block to keep growing... without colliding with these").

### Implementation detail (a repeated, verified pattern across every decoration batch built this way)

```python
# 1. A plain list of "kind" names for this decoration category (e.g. 10 per-biome
#    ambient prop kinds: rock/bush/flowers/boulder/puddle/skull/stump/grasstuft/debris/tree)
# 2. A dict-based allocation, keyed by (category_name, kind) -> a running integer counter,
#    NOT hand-typed named constants (would be pure, unmaintainable repetition at this scale)
_next_id = 500   # a large, deliberately-chosen gap after the last shared/gameplay tile id
for category_name in categories:
    for kind in KIND_LIST:
        PROP_TILE[(category_name, kind)] = _next_id
        _next_id += 1
# 3. Flat-color fallback registered for every new id (usually derived from the tile's
#    OWN surrounding ground/floor color) in case the real art PNG ever fails to load
# 4. Real per-id PNG texture registered via the same variant-loading helper every other
#    tile type already uses, falling back gracefully to the flat color above if missing
```
Each subsequent decoration category (a second batch of world-decoration ids, a batch of dungeon-decoration ids, etc.) started its own block at the NEXT large round-number gap (e.g. +200 from the previous block's start), explicitly leaving the intervening range as that PREVIOUS category's own future-growth buffer — a documented, repeatable convention, not a one-off choice.

**A real, twice-repeated bug this pipeline surfaced**: the shared tile-variant loading helper always expects an index suffix on every art filename (e.g. `tile_something_0.png`), even for a decoration kind that only ever has exactly one variant — but two different batch-render scripts saved their output files WITHOUT that suffix. The result was a *silent* fallback to the flat placeholder color for every single asset in both batches — no crash, no error, and (critically) no visually *obvious* failure either, since a flat ground-toned color square is still a plausible-looking placeholder at a glance. This was only caught by explicitly checking a loaded texture's number of *unique colors* (a flat fallback has exactly 1; real painted art has dozens) — a verification technique worth reusing any time an art pipeline has a silent, plausible-looking failure mode: don't just eyeball the render, programmatically check that something with real internal variation actually loaded.

### Unity rebuild prompt

> When adding a large batch of similar decoration/prop types to a tile or object-id system (dozens to hundreds of similar-but-distinct entries), allocate their ids programmatically from a dict keyed by (category, kind) and a running counter — never hand-type a named constant per entry once you're past a handful. If your project has ANY risk of two independent people/processes adding new ids to the same shared id-space without perfect coordination (a genuine risk in an environment without strict, atomic version control merging, or with multiple parallel automated agents/contributors), deliberately start each new batch's id block at a large, round-number gap past the previous batch's end — leaving the intervening range as that previous batch's own reserved growth buffer — rather than packing new allocations immediately after the last-used id. Give every new tile/prop type both a flat-color programmatic fallback AND a real texture-file lookup with graceful fallback if the file is missing, and when batch-generating many similar art files at once, verify the RESULT actually loaded (e.g. by counting unique colors in the loaded texture and confirming it's not suspiciously flat) rather than assuming a script that ran without errors also produced correctly-wired output — a silent fallback to a plausible-looking placeholder is a real failure mode that visual eyeballing alone can miss.

---

## 5. Scaling art work down to fit the canvas: procedural detail vs. painted detail

### What it is

A deliberate, explicit decision point reached repeatedly across this project: NOT every visual element benefits from the "hand-paint a grid" technique above — at sufficiently small on-screen sizes (a fired projectile rendered at roughly a dozen screen pixels across, for instance), individually painted pixel detail reads as visual noise rather than legible detail, and the better investment is a richer *procedural* shading treatment (radial gradients, layered translucent glow rings, small geometric embellishments computed at draw time) applied directly to simple primitive shapes, rather than switching that asset category to painted PNGs just for consistency with everything else.

### Why/how it was chosen

This is a judgment call made explicit and justified rather than applied silently — the reasoning each time was to check the ACTUAL final on-screen pixel footprint of the asset category in question before deciding, rather than assuming "painted PNG is strictly better" as a blanket rule. A first attempt at a *different* small-scale visual upgrade (adding thin, single-pixel-wide detail lines to a small sprite) was explicitly caught looking great at a large, zoomed-in preview size but nearly vanishing once actually rendered at its true small in-game size — corrected by re-designing around broad-area effects (a bloomed highlight color, a soft glow extending past the silhouette) that survive being shrunk, rather than thin lines that don't. The general lesson --- always verify a small-scale visual change at its ACTUAL final rendered size, not just at a convenient, larger preview size --- is the transferable insight here, independent of which specific asset it was first caught on.

### Unity rebuild prompt

> Before deciding whether a given category of visual asset (projectiles, small status-effect icons, tiny UI glyphs) deserves individually hand-authored/painted detail versus a purely procedural shader/particle treatment, check its actual final on-screen pixel size first. Below roughly 20-30 pixels across, prefer procedural techniques that read well at small scale — radial gradients, soft glow/bloom, simple geometric silhouette variation — over trying to paint fine per-pixel detail that will simply blur or vanish once rendered at true size. Whenever you add fine detail (thin lines, small individual highlight pixels, subtle multi-step gradients) to any asset meant to render small, explicitly render and inspect it at its REAL final on-screen size before considering it finished — a preview at 4x-8x zoom can look meaningfully better than the same asset actually looks in-game, and only checking the zoomed preview is a real, recurring failure mode worth guarding against with a deliberate final-size check every time.

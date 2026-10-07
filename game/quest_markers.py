"""
Quest markers: pick a quest in the Quest Log, press "Show marker" (or T) and its current
objective gets a pin on the minimap, on the full map (M) and in the world - or, when it's
off-screen, an arrow at the screen edge with the distance in tiles.

Shared by main.py and coop_client.py (client-side: the tracked ids live on the player's
save - Player.tracked_quests - and co-op sends them to the server with "track_quests").

A tracked id is "story" (the current act's next objective) or "side:<quest id>".
Each client builds a small `world` dict every frame:

    zone:        "realm" | "nexus" | "dungeon" | "hub"   (hub = Bazaar / Vault room)
    player:      (x, y) world px
    areas:       codex.realm_areas(...) (or None if no Realm map is known)
    grid:        the CURRENT zone's tile grid (water / portal lookups)
    live_npcs:   {npc_id: (x, y)} realm NPCs currently in view (optional, overrides homes)
    nexus_npcs:  {npc_id: (x, y)} Nexus NPCs incl. "father_given" (only needed in the Nexus)

resolve() turns a tracked id into a marker {pos, color, label, note, dist_tiles}: pos is a
world position in the current zone (or None, with a `note` like "in the Nexus - press R").
"""
import math

import pygame

from game import constants as C

MAX_TRACKED = 3
COLORS = [(255, 214, 70), (90, 220, 255), (255, 110, 210)]

# story / side-quest target -> where it actually is, beyond what codex.markers_for knows
NEXUS_TARGETS = {("npc", "father_given"): "father_given", ("area", "anvil"): "hammerstein",
                 ("boss", "mad_god"): "father_given", ("npc", "bitterwick"): "bitterwick",
                 ("npc", "hammerstein"): "hammerstein"}
AREA_ALIASES = {"areas": "places", "island_chests": "islands"}
NO_LOCATION = {"gear", "pets", "world_boss", "dungeons", "heroic_dungeons"}
WATER_SEARCH_TILES = 60


# ------------------------------------------------------------- quest list --
def quest_entries(story_log, side_log):
    """[(qid, title, target)] for every trackable quest right now."""
    out = []
    if story_log and story_log.get("objectives"):
        obj = _story_objective(story_log)
        if obj is not None:
            out.append(("story", obj["text"], obj.get("target")))
    for q in side_log or []:
        out.append((f"side:{q['id']}", q["title"], side_target(q)))
    return out


def _story_objective(story_log):
    """The first unfinished objective that has a target (else the first unfinished one)."""
    todo = [o for o in story_log.get("objectives", []) if o.get("have", 0) < o.get("need", 1)]
    for o in todo:
        if o.get("target") and _locatable_target(o["target"]):
            return o
    return todo[0] if todo else None


def side_target(q):
    """A side quest's marker target: its turn-in NPC once it's ready, else its target."""
    if q.get("ready") and q.get("turn_in"):
        return {"kind": "npc", "key": q["turn_in"], "label": _npc_name(q["turn_in"])}
    if q.get("id", "").startswith("trial_") and q.get("giver"):
        # Heroic trials: the relics drop in that dungeon (no fixed spot) - show the giver
        return {"kind": "npc", "key": q["giver"], "label": _npc_name(q["giver"])}
    return q.get("target")


def _npc_name(npc_id):
    from game import npcs
    return npcs.NPCS.get(npc_id, {}).get("name", npc_id)


def _locatable_target(target):
    if not target:
        return False
    k = (target.get("kind"), target.get("key"))
    if k in NEXUS_TARGETS:
        return True
    return target.get("key") not in NO_LOCATION and not str(target.get("key", "")).startswith("dungeon:")


def toggle(tracked, qid):
    """Add / remove qid from the tracked list (oldest dropped past MAX_TRACKED). Returns the new list."""
    tracked = [q for q in tracked if q != qid] if qid in tracked else (list(tracked) + [qid])[-MAX_TRACKED:]
    return tracked


def color_for(tracked, qid):
    return COLORS[tracked.index(qid) % len(COLORS)] if qid in tracked else (200, 200, 200)


def prune(tracked, story_log, side_log):
    """Drop tracked ids whose quest is gone (handed in / act finished with nothing left)."""
    alive = {qid for qid, _t, _tg in quest_entries(story_log, side_log)}
    return [q for q in tracked if q in alive]


# --------------------------------------------------------------- resolve --
def candidates(target, world):
    """[(zone, x, y, label)] for every place this target can be - zone is "realm" or "nexus"."""
    if not target:
        return []
    from game import codex, sidequests
    kind, key = target.get("kind"), target.get("key")
    nexus_id = NEXUS_TARGETS.get((kind, key))
    if nexus_id is None and kind == "npc":
        from game import npcs
        if npcs.NPCS.get(key, {}).get("zone") == "nexus":
            nexus_id = key
    if nexus_id is not None:
        pos = (world.get("nexus_npcs") or {}).get(nexus_id)
        return [("nexus", pos[0], pos[1], target.get("label") or _npc_name(nexus_id))] if pos else \
            [("nexus", None, None, target.get("label") or _npc_name(nexus_id))]
    if key in NO_LOCATION or str(key).startswith("dungeon:"):
        return []
    areas = world.get("areas")
    t = C.TILE
    if kind == "npc":
        live = (world.get("live_npcs") or {}).get(key)
        if live is not None:
            return [("realm", live[0], live[1], target.get("label") or _npc_name(key))]
        if areas:
            return [("realm", n["x"] * t, n["y"] * t, n["name"]) for n in areas.get("npcs", []) if n["id"] == key]
        return [("realm", None, None, target.get("label", key))]
    if key == "locals" and areas:
        from game import npcs
        return [("realm", n["x"] * t, n["y"] * t, n["name"]) for n in areas.get("npcs", [])
                if npcs.NPCS.get(n["id"], {}).get("zone") == "realm"]
    if key == "heroic_trials":
        out = [("nexus", None, None, "Bitterwick")]
        pos = (world.get("nexus_npcs") or {}).get("bitterwick")
        if pos:
            out = [("nexus", pos[0], pos[1], "Bitterwick")]
        givers = {g for (_q, g, _r, _l) in sidequests.HEROIC_TRIALS.values()}
        if areas:
            out += [("realm", n["x"] * t, n["y"] * t, n["name"]) for n in areas.get("npcs", []) if n["id"] in givers]
        return out
    if key == "water":
        return [("realm", None, None, "any shoreline")]  # resolved against the live grid in resolve()
    if not areas:
        return [("realm", None, None, target.get("label", "the Realm"))]
    where = codex.where_for_target(target)
    where = {"biomes": list(where.get("biomes", [])),
             "areas": [AREA_ALIASES.get(a, a) for a in where.get("areas", [])]}
    if key in AREA_ALIASES and not where["areas"]:
        where["areas"] = [AREA_ALIASES[key]]
    if key == "areas":
        where["areas"] = ["places"]
    return [("realm", x * t, y * t, label) for (x, y, label) in codex.markers_for(where, areas)]


def _nearest_tile(grid, px, py, tiles, radius):
    if not grid:
        return None
    tx, ty = int(px // C.TILE), int(py // C.TILE)
    h, w = len(grid), len(grid[0])
    for r in range(0, radius + 1):
        best = None
        for dy in range(-r, r + 1):
            for dx in (-r, r) if abs(dy) != r else range(-r, r + 1):
                x, y = tx + dx, ty + dy
                if 0 <= x < w and 0 <= y < h and grid[y][x] in tiles:
                    d = dx * dx + dy * dy
                    if best is None or d < best[0]:
                        best = (d, x, y)
        if best is not None:
            return ((best[1] + 0.5) * C.TILE, (best[2] + 0.5) * C.TILE)
    return None


def _exit_portal(world):
    """Where the current zone's way out is (Nexus -> the Realm portal, hubs -> back to the Nexus)."""
    from game import world as W
    grid = world.get("grid")
    p = world.get("player") or (0, 0)
    if not grid:
        return None
    cache = world.setdefault("_portal_cache", {})
    key = id(grid)
    if key not in cache:
        cache[key] = [((x + 0.5) * C.TILE, (y + 0.5) * C.TILE)
                      for y, row in enumerate(grid) for x, t in enumerate(row) if t == W.PORTAL]
    pts = cache[key]
    return min(pts, key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) if pts else None


def resolve(qid, title, target, world, color):
    """One marker for one tracked quest in the player's current zone."""
    zone = world.get("zone")
    px, py = world.get("player") or (0, 0)
    out = {"qid": qid, "title": title, "color": color, "pos": None, "note": "", "label": "",
           "dist_tiles": None}
    cands = candidates(target, world)
    if not cands:
        out["note"] = "no fixed location"
        return out
    if target and target.get("key") == "water" and zone == "realm":
        from game import world as W
        p = _nearest_tile(world.get("grid"), px, py, {W.WATER}, WATER_SEARCH_TILES)
        cands = [("realm", p[0], p[1], "the shoreline")] if p else [("realm", None, None, "any shoreline")]
    here = [c for c in cands if c[0] == ("nexus" if zone == "nexus" else "realm") and c[1] is not None]
    if zone in ("realm", "nexus") and here:
        z, x, y, label = min(here, key=lambda c: (c[1] - px) ** 2 + (c[2] - py) ** 2)
        out.update(pos=(x, y), label=label)
    elif zone == "nexus" and any(c[0] == "realm" for c in cands):
        p = _exit_portal(world)
        out.update(pos=p, label="the Realm portal", note="in the Realm - take the portal")
    elif zone == "realm" and any(c[0] == "nexus" for c in cands):
        out["note"] = "in the Nexus - press R"
    elif zone == "dungeon":
        out["note"] = "outside - leave the dungeon (R)"
    elif zone == "hub":
        p = _exit_portal(world)
        out.update(pos=p, label="the Nexus portal", note="back through the Nexus")
    else:
        out["note"] = "location unknown yet - enter the Realm once"
    if out["pos"] is not None:
        out["dist_tiles"] = int(math.hypot(out["pos"][0] - px, out["pos"][1] - py) / C.TILE)
    return out


def markers(tracked, story_log, side_log, world):
    """Resolved markers for every tracked quest (in tracked order)."""
    by_id = {qid: (title, target) for qid, title, target in quest_entries(story_log, side_log)}
    out = []
    for qid in tracked:
        if qid in by_id:
            title, target = by_id[qid]
            out.append(resolve(qid, title, target, world, color_for(tracked, qid)))
    return out


def can_locate(qid, story_log, side_log):
    for q, _title, target in quest_entries(story_log, side_log):
        if q == qid:
            return _locatable_target(target) or (target or {}).get("key") in ("water", "locals", "heroic_trials")
    return False


# ------------------------------------------------------------------ draw --
def _diamond(surf, color, x, y, r, outline=(0, 0, 0)):
    pts = [(x, y - r), (x + r, y), (x, y + r), (x - r, y)]
    pygame.draw.polygon(surf, color, pts)
    pygame.draw.polygon(surf, outline, pts, width=1)


def _arrow(surf, color, x, y, ang, size=9):
    d = pygame.Vector2(1, 0).rotate_rad(ang)
    n = pygame.Vector2(-d.y, d.x)
    tip = pygame.Vector2(x, y) + d * size
    a = pygame.Vector2(x, y) - d * size * 0.6 + n * size * 0.8
    b = pygame.Vector2(x, y) - d * size * 0.6 - n * size * 0.8
    pygame.draw.polygon(surf, color, [tip, a, b])
    pygame.draw.polygon(surf, (0, 0, 0), [tip, a, b], width=1)


def _pulse(t, base, amp):
    return base + amp * (0.5 + 0.5 * math.sin(t * 5.0))


def draw_on_map(surf, marks, rect, to_screen, t=0.0, small=False):
    """Pins for a map view: `rect` is its on-screen rect, `to_screen(wx, wy)` maps world px
    to screen px. Off-map markers are clamped to the rect's edge as an arrow."""
    for m in marks:
        if m["pos"] is None:
            continue
        sx, sy = to_screen(*m["pos"])
        inner = rect.inflate(-14, -14) if small else rect.inflate(-24, -24)
        if inner.collidepoint(sx, sy):
            r = int(_pulse(t, 6 if small else 9, 3 if small else 5))
            pygame.draw.circle(surf, m["color"], (int(sx), int(sy)), r, width=2)
            _diamond(surf, m["color"], int(sx), int(sy), 4 if small else 6)
        else:
            cx, cy = rect.center
            ang = math.atan2(sy - cy, sx - cx)
            ex = max(inner.left, min(inner.right, sx))
            ey = max(inner.top, min(inner.bottom, sy))
            # project along the ray from the centre so the arrow sits where the line exits
            dx, dy = sx - cx, sy - cy
            if dx or dy:
                k = min(abs((inner.w / 2) / dx) if dx else 1e9, abs((inner.h / 2) / dy) if dy else 1e9)
                ex, ey = cx + dx * k, cy + dy * k
            _arrow(surf, m["color"], int(ex), int(ey), ang, 6 if small else 10)


def draw_world(surf, marks, cam, player_pos, view_rect, font, t=0.0):
    """In-world pins (drawn after the night darkness so they read at night): a bobbing pin
    over the target when it's on screen, else an edge arrow with the distance in tiles."""
    placed = []
    labels = []
    for m in marks:
        if m["pos"] is None:
            continue
        sx, sy = cam(pygame.Vector2(m["pos"]))
        inner = view_rect.inflate(-60, -60)
        dist = f"{m['dist_tiles']}t" if m.get("dist_tiles") is not None else ""
        if inner.collidepoint(sx, sy):
            bob = 4 * math.sin(t * 3.0)
            top = int(sy - 46 + bob)
            pygame.draw.line(surf, m["color"], (sx, top + 10), (sx, sy - 6), 2)
            pygame.draw.circle(surf, m["color"], (int(sx), int(sy)), int(_pulse(t, 10, 6)), width=2)
            _diamond(surf, m["color"], int(sx), top, 9)
            placed.append(pygame.Rect(int(sx) - 10, top - 10, 20, 20))
            labels.append((m, sx, top))
        else:
            ps = cam(pygame.Vector2(player_pos))
            cx, cy = view_rect.center if not view_rect.collidepoint(ps) else ps
            dx, dy = sx - cx, sy - cy
            if not (dx or dy):
                continue
            k = min(abs((inner.right - cx if dx > 0 else cx - inner.left) / dx) if dx else 1e9,
                    abs((inner.bottom - cy if dy > 0 else cy - inner.top) / dy) if dy else 1e9)
            ex, ey = cx + dx * k, cy + dy * k
            ang = math.atan2(dy, dx)
            _arrow(surf, m["color"], int(ex), int(ey), ang, 13)
            lab = font.render(dist, True, m["color"])
            sh = font.render(dist, True, (0, 0, 0))
            off = pygame.Vector2(1, 0).rotate_rad(ang) * -26
            lx, ly = int(ex + off.x - lab.get_width() / 2), int(ey + off.y - lab.get_height() / 2)
            surf.blit(sh, (lx + 1, ly + 1))
            surf.blit(lab, (lx, ly))
    # the quest names go on after every pin, stacked upward so none covers a pin or another name
    for m, sx, top in labels:
        name = m["title"] if len(m["title"]) <= 30 else m["title"][:29].rstrip() + "."
        lab = font.render(name, True, m["color"])
        sh = font.render(name, True, (0, 0, 0))
        r = pygame.Rect(int(sx) - lab.get_width() // 2, top - 14 - lab.get_height(), lab.get_width(), lab.get_height())
        while any(r.colliderect(q) for q in placed):
            r.y -= 4
        placed.append(r)
        surf.blit(sh, (r.x + 1, r.y + 1))
        surf.blit(lab, r.topleft)


def draw_tracker(surf, marks, font, x, y):
    """A compact list of tracked quests (colour, title, distance or where-to-go note)."""
    for m in marks:
        if m["pos"] is not None and m.get("dist_tiles") is not None:
            d = m["dist_tiles"]
            extra = f"{d} tile{'' if d == 1 else 's'}" + (f" - {m['note']}" if m["note"] else "")
        else:
            extra = m["note"]
        text = f"{m['title']}  ({extra})" if extra else m["title"]
        img = font.render(text, True, (235, 232, 240))
        bg = pygame.Surface((img.get_width() + 26, img.get_height() + 6), pygame.SRCALPHA)
        bg.fill((10, 10, 16, 170))
        surf.blit(bg, (x, y))
        _diamond(surf, m["color"], x + 10, y + bg.get_height() // 2, 5)
        surf.blit(img, (x + 20, y + 3))
        y += bg.get_height() + 2
    return y

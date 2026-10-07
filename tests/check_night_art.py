"""
Night art (night-horror update, Step 4d): the hand-painted, animated night mobs and
their emissive glow layers.

- every night mob (and the Ghost Merchant) has a still PNG, a move strip (>= 4 frames),
  an attack strip (>= 2 frames) and a glow layer, all frames the same size as the still
  sprite and cached
- Enemy.draw really animates (different frames over time) and switches to the attack
  strip while winding up, remembering which frame it drew
- the emissive pass draws the CURRENT frame's glow over the darkness (the eyes / lure /
  iris / scythe edge show up in a fully dark spot)
- the painted sprites are distinct from each other

Run with: .venv\\Scripts\\python.exe tests\\check_night_art.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((400, 300))

from game import sprites, ui
from game.entities import Enemy, ENEMY_KINDS, NIGHT_MOB_KINDS

KINDS = list(NIGHT_MOB_KINDS) + ["fireflies"]
ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sprites", "v0.2", "enemies")


def check_every_night_mob_is_hand_painted_and_animated():
    for kind in KINDS + ["npc_ghost_merchant"]:
        for suffix in ("", "_anim", "_attack", "_glow", "_glow_attack"):
            assert os.path.isfile(os.path.join(ART, f"enemy_{kind}{suffix}.png")), (kind, suffix)
    for kind in KINDS:
        scale = ENEMY_KINDS[kind].get("scale", 1.0)
        still = sprites.enemy_sprite(kind, scale)
        moves = sprites.enemy_frames(kind, scale, "move")
        attacks = sprites.enemy_frames(kind, scale, "attack")
        glows = sprites.enemy_frames(kind, scale, "glow")
        assert len(moves) >= 4 and len(attacks) >= 2 and len(glows) == len(moves), (kind, len(moves), len(attacks))
        assert all(f.get_size() == still.get_size() for f in moves + attacks + glows), kind
        assert sprites.enemy_frames(kind, scale, "move") is moves, "frames are cached"
        assert len({pygame.image.tobytes(f, "RGBA") for f in moves}) >= 3, f"{kind}: the frames really differ"
        assert any(f.get_bounding_rect().w > 0 for f in glows), f"{kind}: has something that glows"
    assert sprites.enemy_frames("goblin", 1.0, "move") == [], "kinds without a strip keep their still sprite"
    stills = {pygame.image.tobytes(sprites.enemy_sprite(k, 1.0), "RGBA") for k in KINDS}
    assert len(stills) == len(KINDS), "every night mob looks different"
    print("check_every_night_mob_is_hand_painted_and_animated: PASSED")


def check_draw_animates_and_uses_attack_frames():
    cam = lambda p: (int(p[0]), int(p[1]))
    e = Enemy("hollow_watcher", pygame.Vector2(200, 150))
    seen = set()
    real = pygame.time.get_ticks
    try:
        for ms in range(0, 2000, 70):
            pygame.time.get_ticks = lambda ms=ms: ms
            screen.fill((0, 0, 0))
            e.draw(screen, cam)
            seen.add(e._anim_frame)
        assert len({f for f in seen if f[0] == "move"}) >= 4, seen
        e._windup_frac = 0.5
        e.draw(screen, cam)
        assert e._anim_frame[0] == "attack"
    finally:
        pygame.time.get_ticks = real
    print("check_draw_animates_and_uses_attack_frames: PASSED")


def check_emissive_layer_shows_in_the_dark():
    cam = lambda p: (int(p[0]), int(p[1]))
    for kind in ("red_harvester", "hollow_watcher", "lantern_eater"):
        e = Enemy(kind, pygame.Vector2(200, 150))
        e._anim_frame = ("move", 0)
        surf = pygame.Surface((400, 300)).convert_alpha()
        surf.fill((0, 0, 0, 255))
        ui.draw_night_emissives(surf, cam, [e], 0.0)
        lit = sum(1 for x in range(100, 300, 2) for y in range(40, 260, 2) if sum(surf.get_at((x, y))[:3]) > 60)
        assert lit > 3, f"{kind}: its glow shows in total darkness ({lit})"
        # daylight: nothing is drawn
        surf.fill((0, 0, 0, 255))
        ui.draw_night_emissives(surf, cam, [e], 1.0)
        assert surf.get_at((200, 150))[:3] == (0, 0, 0)
    print("check_emissive_layer_shows_in_the_dark: PASSED")


if __name__ == "__main__":
    check_every_night_mob_is_hand_painted_and_animated()
    check_draw_animates_and_uses_attack_frames()
    check_emissive_layer_shows_in_the_dark()
    print("PASSED: night art checks all green.")

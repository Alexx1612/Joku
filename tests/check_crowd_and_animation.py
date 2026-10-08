"""
Doc 43: the crowd limit (at most CROWD_BASE hostiles around a player, +25% per extra player
standing with them - lair refills, night spawns, Blood Moon hordes and island escorts all ask) and
the players' frame animations (idle / walk / shoot, facing left or right, in co-op too).

Run with: python tests/check_crowd_and_animation.py
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((1366, 820))

from game import accounts, characters, achievements
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_cr_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_cr_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_cr_ach_")

from game import realm_sim as rs, sprites, night as nm
from game.realm_sim import RealmSim
from game.entities import Player, Enemy

random.seed(4)
SIM = RealmSim()


def _players(n, spread=60):
    base = SIM.spawn_point()
    out = []
    for i in range(n):
        p = Player("warrior", f"P{i}", pid=f"p{i}")
        p.pos = pygame.Vector2(base.x + i * spread, base.y)
        p.hp = p.hp_max = 10 ** 6
        out.append(p)
    SIM._crowd_alive = out
    return out


def _fill(p, n, kind="goblin"):
    for i in range(n):
        SIM.enemies.append(Enemy(kind, p.pos + pygame.Vector2(200 + i, 100)))


def check_group_multiplier():
    assert [rs.group_mult(k) for k in (1, 2, 3, 4, 5)] == [1.0, 1.25, 1.5, 1.75, 2.0]
    for n in (1, 2, 3, 5):
        ps = _players(n)
        assert SIM.crowd_cap(ps[0]) == int(round(rs.CROWD_BASE * rs.group_mult(n))), n
    # players far apart don't add up
    ps = _players(2, spread=5000)
    assert SIM.crowd_cap(ps[0]) == rs.CROWD_BASE
    print("check_group_multiplier: PASSED")


def check_crowd_ok_blocks_spawns():
    SIM.enemies = []
    p = _players(1)[0]
    assert SIM.crowd_ok(p.pos)
    _fill(p, rs.CROWD_BASE)
    assert not SIM.crowd_ok(p.pos + pygame.Vector2(300, 0)), "a full view takes no more"
    assert SIM.crowd_ok(p.pos + pygame.Vector2(5000, 0)), "far from every player: fine"
    # two players together get 25% more room
    SIM.enemies = []
    a, b = _players(2)
    _fill(a, rs.CROWD_BASE)
    assert SIM.crowd_ok(a.pos)
    _fill(a, SIM.crowd_cap(a) - rs.CROWD_BASE)
    assert not SIM.crowd_ok(a.pos)
    # bosses never count
    SIM.enemies = [Enemy("red_harvester", a.pos) for _ in range(40)]
    assert SIM.crowd_ok(a.pos)
    # the lair refill obeys it
    SIM.enemies = []
    p = _players(1)[0]
    _fill(p, rs.CROWD_BASE)
    for lair in SIM.lairs:
        lair["respawn_cd"] = 0.0
    before = len(SIM.enemies)
    for _ in range(50):
        SIM._spawn_enemy_lair([p])
    near = SIM.crowd_count(p)
    assert near <= SIM.crowd_cap(p), near
    assert len(SIM.enemies) >= before  # far lairs still refill
    print("check_crowd_ok_blocks_spawns: PASSED")


def check_hordes_and_night_spawns_respect_groups():
    SIM.enemies = []
    ps = _players(3)  # three friends together
    SIM.blood_moon_active = True
    SIM.night._horde_cd = 0
    SIM.night._tick_blood_moon(0.05, ps, ps)
    horde = [e for e in SIM.enemies if getattr(e, "blood_horde", False)]
    cap3 = SIM.crowd_cap(ps[0])
    assert horde and len(horde) <= cap3, (len(horde), cap3)
    assert len(horde) <= int(round(nm.BLOOD_HORDE_SIZE[1] * rs.group_mult(3))), "ONE horde for the group"
    # night spawns: the group shares one (bigger) allowance and the crowd limit holds
    SIM.enemies = []
    SIM.blood_moon_active = False
    for _ in range(80):
        SIM.night._spawn_cd = 0
        SIM.night._tick_spawns(1.0, ps)
    from game.entities import NIGHT_MOB_KINDS
    night = [e for e in SIM.enemies if e.kind in NIGHT_MOB_KINDS]
    assert len(night) <= int(round(nm.NIGHT_MOB_CAP * rs.group_mult(3))) + 1, len(night)
    print(f"check_hordes_and_night_spawns_respect_groups: PASSED (horde {len(horde)}, night mobs {len(night)})")


def check_player_frames_and_states():
    for cls in ("wizard", "warrior", "archer"):
        for which, n in sprites.PLAYER_ANIMS.items():
            fr = sprites.player_frames(cls, which)
            assert len(fr) == n and all(f.get_size() == (sprites.FINAL_SIZE, sprites.FINAL_SIZE) for f in fr), \
                (cls, which, len(fr))
            flipped = sprites.player_frames(cls, which, flip=True)
            assert pygame.image.tostring(flipped[0], "RGBA") == pygame.image.tostring(
                pygame.transform.flip(fr[0], True, False), "RGBA")
    p = Player("wizard", "Anim", pid="a")
    cam = lambda pos: (int(pos[0]) + 300, int(pos[1]) + 300)
    p.draw(screen, cam)  # idle
    p.note_shot((-1.0, 0.0))
    assert p._shoot_anim_t > 0 and p._face_x == -1.0, "shooting left faces left"
    p.draw(screen, cam)
    p._shoot_anim_t = 0
    p._is_moving = True
    p.draw(screen, cam)
    # co-op: walking / facing worked out from snapshots
    import coop_client
    client = coop_client.CoopClient("127.0.0.1", 0, "AnimCoop")
    peer = Player("rogue", "Peer", pid="peer")
    peer.pos = pygame.Vector2(100, 100)
    client._animate_players([peer])
    assert not peer._is_moving
    moved = Player("rogue", "Peer", pid="peer")
    moved.pos = pygame.Vector2(80, 100)
    client._animate_players([moved])
    assert moved._is_moving and moved._face_x == -1.0
    print("check_player_frames_and_states: PASSED")


if __name__ == "__main__":
    check_group_multiplier()
    check_crowd_ok_blocks_spawns()
    check_hordes_and_night_spawns_respect_groups()
    check_player_frames_and_states()
    print("\nPASSED: crowd limit + player animation checks all green.")

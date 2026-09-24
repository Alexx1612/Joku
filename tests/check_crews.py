"""
Quick regression check for the lightweight co-op Crew system
(game/crews.py) - a client-local, atomic-tmp+replace JSON persistence
layer mirroring game/friends.py, plus a reverse-index for "which crew is
this player in" lookups.

Not a real test suite (see README's v0.3 roadmap - that hasn't been built
yet), just a standalone script with real assertions against the actual
files written to disk.

Run with: .venv\\Scripts\\python.exe tests\\check_crews.py
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import crews

# Isolate this run from any real crews/ data on disk.
crews.CREWS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "crews_test_tmp")
crews._MEMBERS_PATH = os.path.join(crews.CREWS_DIR, "_members.json")
if os.path.exists(crews.CREWS_DIR):
    shutil.rmtree(crews.CREWS_DIR)


def check_create_and_join():
    crew = crews.create_crew("Nightfall", "Alice")
    assert crew["members"] == ["Alice"], crew
    assert crew["boss_kills"] == 0
    joined = crews.join_crew("Nightfall", "Bob")
    assert set(joined["members"]) == {"Alice", "Bob"}, joined
    print("check_create_and_join: OK")


def check_member_lookup():
    assert crews.get_crew_for_player("Alice") == "Nightfall"
    assert crews.get_crew_for_player("Bob") == "Nightfall"
    assert crews.get_crew_for_player("Nobody") == ""
    print("check_member_lookup: OK")


def check_boss_kills_persist():
    total = crews.increment_boss_kills("Nightfall", 3)
    assert total == 3, total
    reloaded = crews.load_crew("Nightfall")
    assert reloaded["boss_kills"] == 3, reloaded
    total2 = crews.increment_boss_kills("Nightfall")
    assert total2 == 4
    print("check_boss_kills_persist: OK")


def check_leave_removes_from_crew_and_index():
    crews.leave_crew("Nightfall", "Bob")
    remaining = crews.load_crew("Nightfall")
    assert remaining["members"] == ["Alice"], remaining
    assert crews.get_crew_for_player("Bob") == ""
    # Crew file must survive since Alice is still in it.
    assert os.path.exists(crews._path("Nightfall"))
    # Leaving the last member deletes the crew file entirely.
    crews.leave_crew("Nightfall", "Alice")
    assert not os.path.exists(crews._path("Nightfall"))
    assert crews.get_crew_for_player("Alice") == ""
    print("check_leave_removes_from_crew_and_index: OK")


def check_switching_crews_leaves_old_one():
    crews.create_crew("Alpha", "Carl")
    crews.create_crew("Beta", "Dana")
    crews.join_crew("Beta", "Carl")
    assert crews.get_crew_for_player("Carl") == "Beta"
    # Carl was Alpha's only member, so leaving it implicitly deletes Alpha's file.
    alpha = crews.load_crew("Alpha")
    assert alpha == {}, alpha
    print("check_switching_crews_leaves_old_one: OK")


if __name__ == "__main__":
    try:
        check_create_and_join()
        check_member_lookup()
        check_boss_kills_persist()
        check_leave_removes_from_crew_and_index()
        check_switching_crews_leaves_old_one()
        print("ALL CREW CHECKS PASSED")
    finally:
        if os.path.exists(crews.CREWS_DIR):
            shutil.rmtree(crews.CREWS_DIR)

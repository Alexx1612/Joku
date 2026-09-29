"""
Saves/settings must live next to the executable in a PyInstaller build (not in
the one-file build's per-launch temporary unpack folder, which silently reset
every character/vault/account/setting on each start) and in the project folder
when run from source.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PROBE = r"""
import os, sys
sys.path.insert(0, %r)
if %r:
    sys.frozen = True
    sys.executable = os.path.join(%r, "RealmReforged.exe")
from game import paths, accounts, characters, achievements, items, friends, crews, settings, music
print(repr((accounts.ACCOUNTS_DIR, characters.CHAR_DIR, achievements._DIR, items.VAULT_DIR,
            friends.FRIENDS_DIR, crews.CREWS_DIR, settings.SETTINGS_PATH, music.cache_dir())))
"""


def _probe(frozen, exe_dir):
    env = {k: v for k, v in os.environ.items() if k not in ("RR_SETTINGS_PATH", "RR_MUSIC_CACHE", "RR_DATA_DIR")}
    env["SDL_VIDEODRIVER"] = env["SDL_AUDIODRIVER"] = "dummy"
    out = subprocess.run([sys.executable, "-c", PROBE % (ROOT, frozen, exe_dir)], capture_output=True, text=True,
                         env=env, cwd=tempfile.gettempdir())
    assert out.returncode == 0, out.stderr
    return eval(out.stdout.strip().splitlines()[-1])


def check_frozen_build_saves_next_to_exe():
    exe_dir = tempfile.mkdtemp(prefix="rr_exe_dir_")
    for p in _probe(True, exe_dir):
        assert os.path.normcase(os.path.abspath(p)).startswith(os.path.normcase(os.path.abspath(exe_dir))), p
    print("check_frozen_build_saves_next_to_exe: PASSED")


def check_source_run_saves_in_project():
    for p in _probe(False, ""):
        assert os.path.normcase(os.path.abspath(p)).startswith(os.path.normcase(ROOT)), p
    print("check_source_run_saves_in_project: PASSED")


if __name__ == "__main__":
    check_frozen_build_saves_next_to_exe()
    check_source_run_saves_in_project()
    print("PASSED: data path checks all green.")

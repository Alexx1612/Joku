"""
Where saves/settings live. Running from source: the project folder (as always).
Running a PyInstaller build: the folder the executable sits in - NOT
os.path.dirname(__file__), which for a one-file build is a fresh temporary
unpack folder on every launch (so characters, vaults, accounts and settings
silently reset each start). RR_DATA_DIR overrides both.
"""
import os
import sys


def data_dir():
    override = os.environ.get("RR_DATA_DIR")
    if override:
        return override
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_path(*parts):
    return os.path.join(data_dir(), *parts)

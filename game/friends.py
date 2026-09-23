"""
Per-account friends list - a client-local convenience list of names, not a
server-verified relationship (there's no auth to verify against, same as
accounts.py). One small JSON file per name, atomic tmp+os.replace writes,
same persistence pattern as accounts/vault/achievements.
"""
import json
import os

from game.accounts import sanitize_name

FRIENDS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "friends")


def _path(name: str) -> str:
    return os.path.join(FRIENDS_DIR, f"{sanitize_name(name)}.json")


def load_friends(name: str) -> list:
    path = _path(name)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [n for n in data if isinstance(n, str)] if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError, TypeError):
        return []


def _save_friends(name: str, friend_names: list) -> None:
    os.makedirs(FRIENDS_DIR, exist_ok=True)
    path = _path(name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(friend_names, f)
    os.replace(tmp, path)


def add_friend(owner_name: str, friend_name: str) -> list:
    friends = load_friends(owner_name)
    if friend_name not in friends and friend_name != owner_name:
        friends.append(friend_name)
        _save_friends(owner_name, friends)
    return friends


def remove_friend(owner_name: str, friend_name: str) -> list:
    friends = load_friends(owner_name)
    if friend_name in friends:
        friends.remove(friend_name)
        _save_friends(owner_name, friends)
    return friends

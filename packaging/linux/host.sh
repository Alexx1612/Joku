#!/usr/bin/env sh
# Host a co-op game (TCP port 50777 by default; pass --port N to change).
# Saves (characters/accounts/vaults) are written next to this script.
cd "$(dirname "$0")" && exec ./RealmReforged-Server "$@"

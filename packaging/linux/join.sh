#!/usr/bin/env sh
# Join a co-op game:   ./join.sh <host-address> <YourName>
# Host on this same PC: ./join.sh 127.0.0.1 <YourName>
HOST="${1:-127.0.0.1}"
NAME="${2:-Player}"
cd "$(dirname "$0")" && exec ./RealmReforged-CoopClient --host "$HOST" --name "$NAME"

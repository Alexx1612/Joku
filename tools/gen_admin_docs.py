"""Regenerates the admin-command tables in docs/unity-rebuild/38-admin-commands.md and README.md
from the registry in game/admin.py (between the <!-- admin-table --> markers)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from game import admin

START, END = "<!-- admin-table:start -->", "<!-- admin-table:end -->"


def table():
    by = {}
    for c in admin.COMMANDS.values():
        by.setdefault(c.category, []).append(c)
    out = []
    for key, label in admin.CATEGORIES:
        cmds = sorted(by.get(key, []), key=lambda c: c.name)
        if not cmds:
            continue
        out.append(f"#### {label}\n\n| Command | Also | What it does | In co-op |\n|---|---|---|---|")
        for c in cmds:
            usage = c.usage.replace("|", "\\|")
            also = ", ".join("/" + a for a in c.aliases) or "-"
            where = "everyone" if not c.admin else ("your client" if c.side == "client" else "server, --admin")
            out.append(f"| `{usage}` | {also} | {c.desc.replace('|', '/')} | {where} |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def fill(path):
    s = open(path, encoding="utf-8").read()
    a, b = s.index(START) + len(START), s.index(END)
    s = s[:a] + "\n" + table() + s[b:]
    open(path, "w", encoding="utf-8").write(s)


if __name__ == "__main__":
    for rel in ("docs/unity-rebuild/38-admin-commands.md", "README.md"):
        fill(os.path.join(ROOT, rel))
    print("tables filled")

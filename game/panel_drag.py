"""
Mouse-dragging for movable HUD panels (chat log, story quest log / dungeon
quest panel) - shared by main.py and coop_client.py. Press on a panel and move
more than THRESHOLD px to drag it; a press that doesn't move stays a plain
click (e.g. clicking the chat log still opens chat). Positions persist in
settings.json.
"""
import math

from game import settings, ui


class PanelDrag:
    THRESHOLD = 5

    def __init__(self):
        self.name = None
        self.moved = False

    def down(self, name, pos):
        self.name, self.start, self.moved = name, pos, False
        self.orig = ui.PANEL_OFFSETS.get(name, (0, 0))

    def motion(self, pos):
        if self.name is None:
            return
        dx, dy = pos[0] - self.start[0], pos[1] - self.start[1]
        if not self.moved and math.hypot(dx, dy) < self.THRESHOLD:
            return
        self.moved = True
        ui.set_panel_offset(self.name, (self.orig[0] + dx, self.orig[1] + dy))

    def up(self):
        """Ends the press - returns (panel_name_or_None, was_dragged)."""
        name, moved = self.name, self.moved
        self.name, self.moved = None, False
        if moved:
            settings.change("panel_offsets", {k: list(v) for k, v in ui.PANEL_OFFSETS.items()})
        return name, moved

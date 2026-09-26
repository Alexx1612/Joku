"""
The chat input line (Batch 15): a real text field instead of an append-only
buffer - a movable cursor, partial selection (Shift+arrows / Shift+Home/End /
mouse drag), Ctrl+A/C/X/V, and Up/Down recall of what you sent before. Shared by
main.py and coop_client.py; each keeps its own ChatInput and mirrors `.text` into
its old `chat_buffer` attribute so every existing caller keeps working.

Plus the chat LOG's own line selection (click-drag over the log, Ctrl+C copies)
which works WITHOUT entering chat mode - see LogSelection.
"""
import pygame

from game import clipboard

MAX_LEN = 1000
HISTORY_CAP = 50


class ChatInput:
    def __init__(self):
        self.text = ""
        self.cursor = 0
        self.anchor = None  # selection anchor index, or None = no selection
        self.history = []   # sent lines, oldest first
        self._hist_i = None  # index into history while browsing it with Up/Down
        self._draft = ""

    # ------------------------------------------------------------ state
    def set_text(self, text):
        self.text = text[:MAX_LEN]
        self.cursor = len(self.text)
        self.anchor = None
        self._hist_i = None

    def sync_from(self, buffer):
        """Adopt text written into the owner's chat_buffer from elsewhere
        (e.g. the right-click menu pre-filling "/w Bob ")."""
        if buffer != self.text:
            self.set_text(buffer)

    def selection(self):
        """(start, end) of the selected span, or None."""
        if self.anchor is None or self.anchor == self.cursor:
            return None
        return min(self.anchor, self.cursor), max(self.anchor, self.cursor)

    def all_selected(self):
        sel = self.selection()
        return bool(self.text) and sel == (0, len(self.text))

    def selected_text(self):
        sel = self.selection()
        return self.text[sel[0]:sel[1]] if sel else ""

    # ------------------------------------------------------------ edits
    def _delete_selection(self):
        sel = self.selection()
        if not sel:
            return False
        a, b = sel
        self.text = self.text[:a] + self.text[b:]
        self.cursor, self.anchor = a, None
        return True

    def insert(self, s):
        self._delete_selection()
        s = s.replace("\r", " ").replace("\n", " ")
        room = MAX_LEN - len(self.text)
        s = s[:max(0, room)]
        self.text = self.text[:self.cursor] + s + self.text[self.cursor:]
        self.cursor += len(s)
        self.anchor = None

    def _move(self, new_pos, shift):
        new_pos = max(0, min(len(self.text), new_pos))
        if shift:
            if self.anchor is None:
                self.anchor = self.cursor
        else:
            self.anchor = None
        self.cursor = new_pos

    def _word_left(self):
        i = self.cursor
        while i > 0 and self.text[i - 1] == " ":
            i -= 1
        while i > 0 and self.text[i - 1] != " ":
            i -= 1
        return i

    def _word_right(self):
        i, n = self.cursor, len(self.text)
        while i < n and self.text[i] != " ":
            i += 1
        while i < n and self.text[i] == " ":
            i += 1
        return i

    def remember(self, line):
        if line and (not self.history or self.history[-1] != line):
            self.history.append(line)
            del self.history[:-HISTORY_CAP]
        self._hist_i = None

    def _recall(self, step):
        if not self.history:
            return
        if self._hist_i is None:
            if step > 0:
                return
            self._draft = self.text
            self._hist_i = len(self.history)
        self._hist_i = max(0, min(len(self.history), self._hist_i + step))
        text = self._draft if self._hist_i == len(self.history) else self.history[self._hist_i]
        hist_i = self._hist_i
        self.set_text(text)
        self._hist_i = None if hist_i == len(self.history) else hist_i

    # ------------------------------------------------------------ input
    def handle_key(self, event):
        """Returns "submit", "cancel" or None."""
        ctrl = bool(event.mod & pygame.KMOD_CTRL)
        shift = bool(event.mod & pygame.KMOD_SHIFT)
        k = event.key
        if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return "submit"
        if k == pygame.K_ESCAPE:
            return "cancel"
        if ctrl and k == pygame.K_a:
            self.anchor, self.cursor = 0, len(self.text)
        elif ctrl and k == pygame.K_c:
            clipboard.set_text(self.selected_text() or self.text)
        elif ctrl and k == pygame.K_x:
            if self.selection():
                clipboard.set_text(self.selected_text())
                self._delete_selection()
            else:
                clipboard.set_text(self.text)
                self.set_text("")
        elif ctrl and k == pygame.K_v:
            self.insert(clipboard.get_text())
        elif k == pygame.K_BACKSPACE:
            if not self._delete_selection() and self.cursor > 0:
                cut = self._word_left() if ctrl else self.cursor - 1
                self.text = self.text[:cut] + self.text[self.cursor:]
                self.cursor = cut
        elif k == pygame.K_DELETE:
            if not self._delete_selection() and self.cursor < len(self.text):
                end = self._word_right() if ctrl else self.cursor + 1
                self.text = self.text[:self.cursor] + self.text[end:]
        elif k == pygame.K_LEFT:
            if self.selection() and not shift:
                self._move(self.selection()[0], False)
            else:
                self._move(self._word_left() if ctrl else self.cursor - 1, shift)
        elif k == pygame.K_RIGHT:
            if self.selection() and not shift:
                self._move(self.selection()[1], False)
            else:
                self._move(self._word_right() if ctrl else self.cursor + 1, shift)
        elif k == pygame.K_HOME:
            self._move(0, shift)
        elif k == pygame.K_END:
            self._move(len(self.text), shift)
        elif k == pygame.K_UP:
            self._recall(-1)
        elif k == pygame.K_DOWN:
            self._recall(1)
        elif event.unicode and event.unicode.isprintable():
            self.insert(event.unicode)
        return None

    # mouse: click places the cursor, drag selects
    def index_at(self, font, text_x, mouse_x, first_visible=0):
        x = mouse_x - text_x
        shown = self.text[first_visible:]
        for i in range(len(shown) + 1):
            if font.size(shown[:i])[0] >= x:
                if i > 0 and font.size(shown[:i])[0] - x > x - font.size(shown[:i - 1])[0]:
                    return first_visible + i - 1
                return first_visible + i
        return len(self.text)

    def mouse_down(self, idx):
        self.cursor, self.anchor = idx, idx

    def mouse_drag(self, idx):
        if self.anchor is None:
            self.anchor = self.cursor
        self.cursor = idx


class LogSelection:
    """A click-drag selection of whole lines in the chat log (wrapped-line indices
    into ui._chat_log_flatten) - lets you copy chat without opening the input."""

    def __init__(self):
        self.start = None
        self.end = None
        self.dragging = False

    def clear(self):
        self.start = self.end = None
        self.dragging = False

    def begin(self, line_idx):
        self.start = self.end = line_idx
        self.dragging = True

    def extend(self, line_idx):
        if self.dragging and line_idx is not None:
            self.end = line_idx

    def finish(self):
        self.dragging = False

    def span(self):
        if self.start is None:
            return None
        return min(self.start, self.end), max(self.start, self.end)

    def copy(self, messages):
        """Copies the selected messages as "name: text" lines. True if anything was copied."""
        from game import ui
        span = self.span()
        if span is None:
            return False
        flat = ui._chat_log_flatten(messages)
        idxs = sorted({flat[i][2] for i in range(span[0], min(span[1], len(flat) - 1) + 1)})
        if not idxs:
            return False
        clipboard.set_text("\n".join(f"{messages[i]['name']}: {messages[i]['text']}" for i in idxs))
        return True

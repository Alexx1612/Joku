"""
Cross-platform clipboard access for the chat box's Ctrl+C/X/V - uses tkinter
(ships with Python, not a new dependency) rather than pygame.scrap, which is
unreliable across pygame builds/platforms. A single hidden Tk root is created
lazily and reused, since spinning one up per call would be slow.
"""
_root = None


def _get_root():
    global _root
    if _root is None:
        import tkinter
        _root = tkinter.Tk()
        _root.withdraw()
    return _root


def get_text():
    try:
        return _get_root().clipboard_get()
    except Exception:
        return ""


def set_text(text):
    try:
        root = _get_root()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
    except Exception:
        pass

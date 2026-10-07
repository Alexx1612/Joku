"""
Eye adaptation (realism pass): at nightfall your light starts small and widens as your eyes
get used to the dark (~25 s); stepping out of a bright lamp into the dark briefly shrinks it
again. A plain per-client helper - main.py and coop_client.py each keep one.
"""
NIGHTFALL_START = 0.62     # light radius right after dark falls
DAZZLED = 0.72             # after standing in bright light, then stepping out
ADAPT_RATE = 1 / 25.0      # per second toward full


class EyeAdaptation:
    def __init__(self):
        self.level = 1.0
        self._was_night = False
        self._bright_t = 0.0

    def update(self, dt, night, in_bright_light):
        if night and not self._was_night:
            self.level = NIGHTFALL_START
        self._was_night = night
        if not night:
            self.level = 1.0
            return 1.0
        if in_bright_light:
            self._bright_t += dt
        else:
            if self._bright_t > 2.0:
                self.level = min(self.level, DAZZLED)
            self._bright_t = 0.0
        self.level = min(1.0, self.level + ADAPT_RATE * dt)
        return self.level

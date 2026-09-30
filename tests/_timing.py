"""
Shared helper for the generation-time budget checks.

Windows 11 power-throttles ("EcoQoS") a console process that has no foreground
window and no live audio stream after a few seconds of running - exactly what a
headless test with SDL's dummy audio driver looks like - and everything in it
then runs ~3-4x slower. That made the world-generation budgets measure the OS's
power saving, not the game (a player's game window has real audio and focus, so
it is never throttled). The budget checks opt their own process out first.
"""
import sys


def disable_power_throttling():
    """Best effort: opt THIS process out of Windows execution-speed throttling. No-op elsewhere."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG),
                        ("StateMask", wintypes.ULONG)]

        PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
        PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
        ProcessPowerThrottling = 4
        state = PROCESS_POWER_THROTTLING_STATE(PROCESS_POWER_THROTTLING_CURRENT_VERSION,
                                               PROCESS_POWER_THROTTLING_EXECUTION_SPEED, 0)
        k32 = ctypes.windll.kernel32
        k32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        return bool(k32.SetProcessInformation(k32.GetCurrentProcess(), ProcessPowerThrottling,
                                              ctypes.byref(state), ctypes.sizeof(state)))
    except Exception:
        return False

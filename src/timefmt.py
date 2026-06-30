"""
Shared time-formatting helpers (seconds float -> display string).

Kept in one place so the console reporter, the Excel exporter, and the GUI
all render times identically.
"""


def fmt_time(secs: float) -> str:
    """Total seconds -> "M:SS.hh" (minutes always shown). e.g. 125.67 -> "2:05.67"."""
    mins = int(secs // 60)
    s = secs - mins * 60
    return f"{mins}:{s:05.2f}"


def fmt_split(secs: float) -> str:
    """Like fmt_time but uses a "0:" prefix for sub-minute splits. 28.5 -> "0:28.50"."""
    mins = int(secs // 60)
    s = secs - mins * 60
    return f"{mins}:{s:05.2f}" if mins else f"0:{s:05.2f}"


def secs_to_str(total_secs: float) -> str:
    """Total seconds -> "M:SS.ss" or "SS.ss" (minute prefix omitted under 1 min)."""
    mins = int(total_secs // 60)
    secs = total_secs - mins * 60
    return f"{mins}:{secs:05.2f}" if mins > 0 else f"{secs:.2f}"

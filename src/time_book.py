import time
from contextlib import contextmanager

class TimerBook:
    def __init__(self):
        self._global_start = time.perf_counter()
        self.sections = {}
        self._threshold = 0.0

    def global_elapsed(self):
        return time.perf_counter() - self._global_start

    @contextmanager
    def section(self, name):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.sections[name] = self.sections.get(name, 0.0) + elapsed

    def reset(self):
        """Reset all measurements (global and sections)."""
        self._global_start = time.perf_counter()
        self.sections.clear()

    def report(self):
        lines = [f"Global: {self.global_elapsed():.3f}s"]
        for k, v in self.sections.items():
            if v >= self._threshold:
                lines.append(f"{k}: {v:.3f}s")
        return "\n".join(lines)


# Module-level singleton to share across modules
_TIMER_SINGLETON = TimerBook()


def get_timer():
    """Return the shared TimerBook instance."""
    return _TIMER_SINGLETON


def set_threshold(threshold: float):
    """Set a threshold for reporting sections.

    Sections with elapsed time below this threshold will be omitted from the report.
    """
    _TIMER_SINGLETON._threshold = threshold

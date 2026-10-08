"""登录限速:滑动窗口,内存实现(单实例;重启即清零,详见部署文档)。"""
from __future__ import annotations

import threading
import time


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: int):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def parse(spec: str) -> tuple[int, int]:
        # "5/300" -> (5, 300)
        try:
            n, w = spec.split("/", 1)
            return max(1, int(n)), max(1, int(w))
        except Exception:
            return 5, 300

    def _prune(self, key: str, now: float) -> None:
        lst = self._events.get(key, [])
        lst[:] = [t for t in lst if now - t < self.window]
        self._events[key] = lst

    def allow(self, key: str) -> bool:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now)
            return len(self._events.get(key, [])) < self.max_events

    def hit(self, key: str) -> None:
        with self._lock:
            self._events.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

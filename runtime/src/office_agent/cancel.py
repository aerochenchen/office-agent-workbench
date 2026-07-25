from __future__ import annotations

import threading


class CancelledError(Exception):
    """Raised when a CancelToken has been cancelled."""


class CancelToken:
    """Thread-safe cooperative cancellation for one agent turn."""

    def __init__(self) -> None:
        self._cancelled = False
        self._lock = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True

    def check(self) -> None:
        with self._lock:
            if self._cancelled:
                raise CancelledError("cancelled")

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

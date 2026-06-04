import threading
import time


class BatchControl:
    """Cooperative run controls for the demo: pause / resume / cancel a batch run.

    The worker checks this between items (and waits while paused), so a long
    `Seed 200 → Run` can be paused or killed live without corrupting state.
    Thread-safe enough for the single-process demo.
    """

    def __init__(self) -> None:
        self._paused = threading.Event()
        self._cancelled = threading.Event()
        self._running = threading.Event()

    # --- state ---
    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def snapshot(self) -> dict:
        return {"running": self.running, "paused": self.paused, "cancelled": self.cancelled}

    # --- transitions ---
    def start(self) -> None:
        self._cancelled.clear()
        self._paused.clear()
        self._running.set()

    def finish(self) -> None:
        self._running.clear()
        self._paused.clear()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def cancel(self) -> None:
        self._cancelled.set()
        self._paused.clear()  # unblock a paused loop so it can see the cancel

    # --- worker hook ---
    def wait_if_paused(self, poll: float = 0.1) -> None:
        """Block while paused; return immediately once resumed or cancelled."""
        while self._paused.is_set() and not self._cancelled.is_set():
            time.sleep(poll)


# Single process-wide control instance shared by the app + worker.
batch_control = BatchControl()

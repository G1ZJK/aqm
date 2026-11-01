"""Poller service: end-to-end ingest loop.

Polls the ZN-MT29 over the LAN at the configured interval, normalizes the raw
DPS payload into a :class:`~aqm.reading.Reading` (computing AQI), stores it, and
invokes an optional per-reading callback (used by the alerts engine). Designed
so the single-iteration logic (:meth:`Poller.poll_once`) is unit-testable with
a mocked device client, independent of real hardware, timing, or MongoDB.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from .config import AppConfig
from .reading import Reading, normalize
from .storage import ReadingStore

logger = logging.getLogger("aqm.poller")


class DeviceClient(Protocol):
    """Minimal interface the poller needs from a device client."""

    def status(self) -> dict[str, Any]:
        ...


ReadingCallback = Callable[[Reading], None]


class Poller:
    """Owns the ingest loop. Hardware access is injected for testability."""

    def __init__(
        self,
        config: AppConfig,
        store: ReadingStore,
        device: DeviceClient,
        on_reading: ReadingCallback | None = None,
    ):
        self._config = config
        self._store = store
        self._device = device
        self._on_reading = on_reading
        self._running = False

    def poll_once(self) -> Reading | None:
        """Poll the device once; normalize and store a reading.

        Returns the stored :class:`Reading`, or ``None`` if the device returned
        no usable data (logged, not raised, so the loop keeps running).
        """
        try:
            status = self._device.status()
        except Exception as exc:  # noqa: BLE001 - never let a poll crash the loop
            logger.warning("Device poll failed: %s", exc)
            return None

        raw_dps = (status or {}).get("dps")
        if not raw_dps:
            logger.warning("Device returned no datapoints: %r", status)
            return None

        reading = normalize(
            raw_dps,
            self._config.device.dps_map,
            self._config.device.scaling,
        )
        if not reading.values:
            logger.warning("No parameters resolved from DPS %r", raw_dps)
            return None

        try:
            self._store.insert(reading)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to store reading: %s", exc)
            return None

        if self._on_reading is not None:
            try:
                self._on_reading(reading)
            except Exception as exc:  # noqa: BLE001 - callback must not kill loop
                logger.error("on_reading callback error: %s", exc)

        logger.debug("Stored reading: %s", reading.values)
        return reading

    def run_forever(self, *, max_iterations: int | None = None) -> None:
        """Run the polling loop until stopped.

        ``max_iterations`` bounds the loop (used by tests/smoke runs). The
        interval sleep is skipped after the final iteration.
        """
        self._running = True
        interval = self._config.device.poll_interval_seconds
        iterations = 0
        logger.info("Poller started (interval %.1fs).", interval)
        while self._running:
            self.poll_once()
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            time.sleep(interval)
        logger.info("Poller stopped after %d iteration(s).", iterations)

    def stop(self) -> None:
        self._running = False

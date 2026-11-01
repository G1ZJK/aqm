"""Entry point: the poller service (end-to-end ingest).

Wires config -> MongoDB -> device -> poller, with alert evaluation on each
reading. Run with:  python -m aqm.poller_main [config.yaml]
"""

from __future__ import annotations

import sys

from .alerts import AlertManager
from .config import load_config
from .device import build_device
from .logging_setup import setup_logging
from .mongodb import make_sync_client, require_healthy
from .poller import Poller
from .storage import ReadingStore


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = sys.argv[1:] if argv is None else argv
    path = args[0] if args else None
    config = load_config(path)

    require_healthy(config.mongo)
    client = make_sync_client(config.mongo)
    db = client[config.mongo.database]

    store = ReadingStore(db, config.mongo, config.device.device_id)
    store.ensure_collection()

    alert_manager = AlertManager(db, config.mongo, config.alerts)
    device = build_device(config.device)

    poller = Poller(config, store, device, on_reading=alert_manager.process)
    try:
        poller.run_forever()
    except KeyboardInterrupt:
        poller.stop()
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

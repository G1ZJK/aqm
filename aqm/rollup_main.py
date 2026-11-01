"""Entry point: the rollup scheduler service.

Runs an APScheduler background job that periodically rolls raw readings into
daily/weekly/monthly collections. On startup it backfills the configured
window. Run with:  python -m aqm.rollup_main [config.yaml]

Pass ``--once`` to run a single rollup and exit (useful for cron or testing).
"""

from __future__ import annotations

import logging
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler

from .config import load_config
from .logging_setup import setup_logging
from .mongodb import make_sync_client, require_healthy
from .rollup import RollupJob

logger = logging.getLogger("aqm.rollup_main")


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = sys.argv[1:] if argv is None else argv
    run_once = "--once" in args
    positional = [a for a in args if not a.startswith("--")]
    path = positional[0] if positional else None
    config = load_config(path)

    require_healthy(config.mongo)
    client = make_sync_client(config.mongo)
    db = client[config.mongo.database]
    job = RollupJob(db, config.mongo, config.rollup)

    def run():
        try:
            result = job.run_recent()
            logger.info("Rollup complete: %s", result)
        except Exception:  # noqa: BLE001
            logger.exception("Rollup run failed")

    # Startup backfill.
    run()

    if run_once or not config.rollup.enabled:
        client.close()
        return 0

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(run, "interval", minutes=config.rollup.interval_minutes)
    scheduler.start()
    logger.info("Rollup scheduler started (every %d min).", config.rollup.interval_minutes)
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

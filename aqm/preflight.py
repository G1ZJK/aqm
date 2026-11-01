"""CLI: MongoDB preflight check.

Usage:
    python -m aqm.preflight [path/to/config.yaml]

Reports the MongoDB version and whether native time-series collections are
supported. Exits non-zero if MongoDB is unreachable.
"""

from __future__ import annotations

import sys

from .config import load_config
from .logging_setup import setup_logging
from .mongodb import MongoUnavailableError, check_health


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = sys.argv[1:] if argv is None else argv
    path = args[0] if args else None
    try:
        cfg = load_config(path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    try:
        report = check_health(cfg.mongo)
    except MongoUnavailableError as exc:
        print(f"UNREACHABLE: {exc}", file=sys.stderr)
        return 1
    print(report.message)
    if not report.supports_timeseries:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

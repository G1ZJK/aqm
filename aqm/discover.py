"""CLI: connect to the ZN-MT29 and dump its raw DPS values.

Usage:
    python -m aqm.discover [path/to/config.yaml]

Prints the raw datapoints so you can build ``device.dps_map`` in config. Also
shows how the current mapping resolves, to help verify your map.
"""

from __future__ import annotations

import json
import sys

from .config import load_config
from .device import fetch_status, map_dps_to_parameters
from .logging_setup import setup_logging


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
        status = fetch_status(cfg.device)
    except Exception as exc:  # noqa: BLE001 - surface any tinytuya/network error
        print(f"ERROR: could not read device: {exc}", file=sys.stderr)
        print(
            "Tips: verify ip/local_key/version in config; try version 3.4 or 3.5; "
            "ensure the device is on the same LAN.",
            file=sys.stderr,
        )
        return 1

    raw_dps = status.get("dps", {})
    print("Raw DPS payload:")
    print(json.dumps(raw_dps, indent=2))
    print("\nResolved via current dps_map:")
    mapped = map_dps_to_parameters(raw_dps, cfg.device.dps_map)
    print(json.dumps(mapped, indent=2))

    unmapped = sorted(set(map(str, raw_dps)) - set(cfg.device.dps_map))
    if unmapped:
        print(f"\nUnmapped DPS ids (add to dps_map if relevant): {', '.join(unmapped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

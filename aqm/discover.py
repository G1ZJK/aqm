"""CLI: connect to the ZN-MT29 and dump its raw DPS values.

Usage:
    python -m aqm.discover [path/to/config.yaml]

Prints the full raw status (so tinytuya errors are visible), the datapoints,
and how the current ``device.dps_map`` resolves them. If the configured
protocol version yields no datapoints, it probes the other common versions
(3.1 / 3.3 / 3.4 / 3.5) and reports which one works.
"""

from __future__ import annotations

import json
import sys

from .config import load_config
from .device import build_device, map_dps_to_parameters
from .logging_setup import setup_logging

_PROBE_VERSIONS = (3.3, 3.4, 3.5, 3.1)


def _status_for_version(cfg_device, version: float) -> dict:
    """Fetch status at a specific protocol version."""
    cfg_device = cfg_device.model_copy(update={"version": version})
    device = build_device(cfg_device)
    return device.status() or {}


def _has_dps(status: dict) -> bool:
    return bool(status) and bool(status.get("dps"))


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
        status = _status_for_version(cfg.device, cfg.device.version)
    except Exception as exc:  # noqa: BLE001 - surface any tinytuya/network error
        print(f"ERROR: could not read device: {exc}", file=sys.stderr)
        print(
            "Tips: verify ip/local_key in config; ensure the device is on the "
            "same LAN and reachable from this host.",
            file=sys.stderr,
        )
        return 1

    print(f"Full raw status (version {cfg.device.version}):")
    print(json.dumps(status, indent=2, default=str))

    # tinytuya returns errors inside the status dict, e.g. {"Error":..,"Err":"905"}.
    if "Error" in status or "Err" in status:
        print(
            "\nDevice returned an ERROR, not data. Common causes:\n"
            "  Err 905 -> wrong IP / device unreachable on the LAN.\n"
            "  Err 901/914 -> wrong local_key (re-run the tinytuya wizard; the "
            "key changes if you re-pair the device in the app).\n"
            "  decryption errors -> wrong protocol version.",
            file=sys.stderr,
        )

    if not _has_dps(status):
        print("\nNo datapoints at the configured version. Probing other versions…")
        for version in _PROBE_VERSIONS:
            if version == cfg.device.version:
                continue
            try:
                probe = _status_for_version(cfg.device, version)
            except Exception as exc:  # noqa: BLE001
                print(f"  version {version}: error ({exc})")
                continue
            if _has_dps(probe):
                print(f"  version {version}: SUCCESS — set 'version: {version}' in config.yaml")
                print(json.dumps(probe.get("dps", {}), indent=2))
                return 0
            print(f"  version {version}: no datapoints")
        print(
            "\nNo version returned datapoints. Most likely the local_key is "
            "stale or the IP is wrong. Re-run 'python -m tinytuya wizard' and "
            "'python -m tinytuya scan' to refresh both.",
            file=sys.stderr,
        )
        return 1

    raw_dps = status.get("dps", {})
    print("\nResolved via current dps_map:")
    mapped = map_dps_to_parameters(raw_dps, cfg.device.dps_map)
    print(json.dumps(mapped, indent=2))

    unmapped = sorted(set(map(str, raw_dps)) - set(cfg.device.dps_map))
    if unmapped:
        print(f"\nUnmapped DPS ids (add to dps_map if relevant): {', '.join(unmapped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI: load and print the redacted configuration.

Usage:
    python -m aqm.config_cli [path/to/config.yaml]
"""

from __future__ import annotations

import json
import sys

from .config import load_config


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = args[0] if args else None
    try:
        config = load_config(path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR: invalid configuration:\n{exc}", file=sys.stderr)
        return 1
    print(json.dumps(config.redacted(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Entry point: the FastAPI web server (via uvicorn).

Run with:  python -m aqm.web_main [config.yaml]
Binds to the host/port from config (default 0.0.0.0:8000, LAN-accessible).
"""

from __future__ import annotations

import sys

import uvicorn

from .config import load_config
from .logging_setup import setup_logging
from .web import create_app


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = sys.argv[1:] if argv is None else argv
    path = args[0] if args else None
    config = load_config(path)
    app = create_app(config)
    uvicorn.run(app, host=config.web.host, port=config.web.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

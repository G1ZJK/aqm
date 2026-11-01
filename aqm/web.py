"""FastAPI backend: current values, historical/bucketed stats, alerts, SSE.

The app exposes a small JSON API plus a server-rendered dashboard. Data access
goes through injectable provider functions so tests can substitute fakes
without a live MongoDB.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from .config import AppConfig, load_config
from .parameters import PARAMETERS
from .queries import ALL_BUCKETS, QueryService

_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_BASE_DIR / "templates"))
_STATIC_DIR = _BASE_DIR / "static"


def _parse_dt(value: str | None, default: datetime) -> datetime:
    if value is None:
        return default
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid datetime: {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def create_app(
    config: AppConfig | None = None,
    *,
    query_service: QueryService | None = None,
    alert_provider=None,
    event_source=None,
) -> FastAPI:
    """Build the FastAPI app.

    ``query_service``/``alert_provider``/``event_source`` can be injected for
    testing; in production they are created from the Mongo connection.
    """
    config = config or load_config()
    app = FastAPI(title=config.web.title)

    # Lazily created production dependencies.
    state: dict = {"query": query_service, "alerts": alert_provider, "events": event_source}

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    def get_query() -> QueryService:
        if state["query"] is None:
            from motor.motor_asyncio import AsyncIOMotorClient

            client = AsyncIOMotorClient(
                config.mongo.uri,
                serverSelectionTimeoutMS=config.mongo.server_selection_timeout_ms,
                tz_aware=True,
            )
            state["query"] = QueryService(client[config.mongo.database], config.mongo)
        return state["query"]

    async def get_active_alerts() -> list[dict]:
        if state["alerts"] is not None:
            result = state["alerts"]()
            if asyncio.iscoroutine(result):
                return await result
            return result
        # Default: read the alerts collection via the query service's db.
        qs = get_query()
        cursor = qs._db[config.mongo.alerts_collection].find({"active": True})  # noqa: SLF001
        out = []
        async for d in cursor:
            d["param"] = d.pop("_id")
            out.append(d)
        return out

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/parameters")
    async def parameters() -> list[dict]:
        return [{"key": p.key, "label": p.label, "unit": p.unit} for p in PARAMETERS]

    @app.get("/api/current")
    async def current(qs: QueryService = Depends(get_query)) -> dict:
        reading = await qs.current()
        if reading is None:
            return {"ts": None, "values": {}}
        return reading

    @app.get("/api/history")
    async def history(
        metric: str = Query(..., description="parameter key"),
        bucket: str = Query("hourly"),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        qs: QueryService = Depends(get_query),
    ) -> dict:
        if bucket not in ALL_BUCKETS:
            raise HTTPException(status_code=400, detail=f"invalid bucket: {bucket}")
        now = datetime.now(UTC)
        default_from = now - timedelta(hours=24)
        start = _parse_dt(from_, default_from)
        end = _parse_dt(to, now)
        series = await qs.history(metric, bucket, start, end)
        return {"metric": metric, "bucket": bucket, "series": series}

    @app.get("/api/alerts")
    async def alerts() -> dict:
        active = await get_active_alerts()
        return {"active": active}

    @app.get("/api/stream")
    async def stream(request: Request):
        """SSE stream of {reading, alerts} snapshots."""

        async def event_generator():
            while True:
                if await request.is_disconnected():
                    break
                if state["events"] is not None:
                    payload = state["events"]()
                    if asyncio.iscoroutine(payload):
                        payload = await payload
                else:
                    qs = get_query()
                    reading = await qs.current()
                    active = await get_active_alerts()
                    payload = {"reading": reading, "alerts": active}
                yield {"event": "update", "data": json.dumps(payload, default=str)}
                await asyncio.sleep(config.device.poll_interval_seconds)

        return EventSourceResponse(event_generator())

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return _TEMPLATES.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "title": config.web.title,
                "parameters": [
                    {"key": p.key, "label": p.label, "unit": p.unit} for p in PARAMETERS
                ],
                "buckets": list(ALL_BUCKETS),
            },
        )

    app.state.config = config
    return app

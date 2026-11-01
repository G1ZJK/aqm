# Air Quality Monitor — Raspberry Pi 5 + ZN-MT29

A LAN-only web dashboard that reads air quality data from a **ZN-MT29** (Tuya
WiFi) monitor over the local network, stores all parameters in **MongoDB**,
computes time-bucketed statistics (avg, stddev, min, max, count), shows live
values and historical trend charts, and raises threshold alerts.

- **No cloud at runtime.** The device is read locally with `tinytuya`.
- **Parameters (11):** CO₂, CO, TVOC, HCHO, PM0.3, PM1, PM2.5, PM10,
  temperature, humidity, and a computed **AQI** (US EPA).
- **Buckets:** minute, hourly (on-demand aggregation) and daily, weekly,
  monthly (pre-aggregated rollups).
- **Stack:** Python · tinytuya · MongoDB 7.0 · FastAPI · APScheduler ·
  Chart.js (vendored, no Node build) · systemd.

## Architecture

```
ZN-MT29 (WiFi) --LAN/tinytuya--> Poller --normalize+AQI--> MongoDB time-series (TTL)
                                               |                     |
                                               v                     v
                                         Alerts engine        On-demand aggregation (minute/hourly)
                                               |                     |
                                   Rollup job -> daily/weekly/monthly collections
                                               |                     |
                                               +------> FastAPI <-----+
                                                          |
                                           JSON / SSE  -> Browser dashboard (Chart.js)
```

Three services run on the Pi: **poller**, **rollup scheduler**, **web**.

## Quick start with Docker (recommended)

The easiest way to run everything — MongoDB plus the three app services — is
Docker Compose. The app image is built once and reused by all three services.

Prerequisites: Docker Engine + the Compose plugin on the Pi.

```bash
curl -fsSL https://get.docker.com | sh          # installs Docker (ARM64 ok on Pi 5)
sudo usermod -aG docker "$USER"                 # then log out/in so 'docker' works without sudo
```

Configure and launch:

```bash
cp config.example.yaml config.yaml   # fill in device_id, local_key, ip (see sections 2 & 5)
cp .env.example .env                  # optional: set WEB_PORT (default 8080)
docker compose up -d --build
```

The dashboard is at `http://<pi-ip>:8080` (or whatever `WEB_PORT` you set).

Notes:
- **MongoDB runs in a container** (`mongo:7.0`, official ARM64) with data on a
  named volume `mongo_data`, so you do **not** need the bare-metal MongoDB
  install in section 1. Mongo is only reachable on the internal compose network,
  not published to the LAN.
- **Mongo URI is injected** via `AQM_MONGO_URI=mongodb://mongo:27017`, so the
  same `config.yaml` works in Docker and bare-metal — the `mongo.uri` in the
  file is ignored inside compose.
- **Port:** the container listens on 8000 internally; compose maps it to host
  `WEB_PORT` (default **8080**) to avoid clashing with an existing app on 8000.
- **Device access:** the poller reaches the ZN-MT29 by its LAN IP over the
  normal bridge network — no special networking needed, since the Pi routes to
  the device. Keep `device.ip` set to the device's LAN address.
- `config.yaml` is mounted **read-only**; edit it and `docker compose restart`
  to apply changes.

Common commands:

```bash
docker compose logs -f web         # tail a service (web / poller / rollup / mongo)
docker compose ps                   # status
docker compose restart poller       # restart one service after a config edit
docker compose down                 # stop (data persists in the mongo_data volume)
docker compose down -v              # stop AND delete MongoDB data
```

Verify connectivity and the device mapping from inside a container (see
sections 4 & 5 for what to look for):

```bash
docker compose run --rm web python -m aqm.preflight
docker compose run --rm web python -m aqm.discover
```

If you use Docker you can skip to section 2 (device credentials) and section 5
(DPS mapping); the manual sections 1, 3, 6, and 7 are for a bare-metal install.

## 1. Prerequisites: MongoDB 7.0 on Raspberry Pi 5 (bare-metal install)

The Pi 5 (Cortex-A76, ARMv8.2-A) runs official MongoDB 7.0 ARM64 on 64-bit
Raspberry Pi OS. (Pi 4 and earlier are ARMv8.0 and are **not** supported by
official MongoDB 5.0+.)

```bash
sudo apt-get install -y gnupg curl
curl -fsSL https://pgp.mongodb.com/server-7.0.asc | \
  sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] http://repo.mongodb.org/apt/debian bookworm/mongodb-org/7.0 main" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt-get update
sudo apt-get install -y mongodb-org
sudo systemctl enable --now mongod
mongod --version    # expect db version v7.0.x
```

> If your Raspberry Pi OS release uses a different Debian codename, replace
> `bookworm` accordingly. See the MongoDB docs for the current repo path.

## 2. Get the ZN-MT29 device id, local key, and IP

Local reading needs the device's **Device ID** and **Local Key**. Obtain them
once via a free Tuya developer account:

1. Create a project at <https://iot.tuya.com> (Cloud → Development).
2. Link your Smart Life / Tuya app account to the project
   (Cloud → … → Link Tuya App Account).
3. Run the tinytuya wizard and follow the prompts:
   ```bash
   python -m tinytuya wizard
   ```
   It writes `devices.json` containing each device's **id** and **local key**.
4. Find the device IP (router client list, or `python -m tinytuya scan`).

Copy the example config and fill it in (this file is git-ignored):

```bash
cp config.example.yaml config.yaml
# edit config.yaml: device_id, local_key, ip, version
```

## 3. Install the app

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Verify connectivity

```bash
# MongoDB reachable + time-series supported?
python -m aqm.preflight config.yaml

# Print the loaded config (secrets redacted)
python -m aqm.config_cli config.yaml
```

## 5. Discover the DPS → parameter mapping

The DPS (datapoint) ids vary by firmware, so confirm them against your device:

```bash
python -m aqm.discover config.yaml
```

This prints the raw DPS payload and how the current `dps_map` resolves it, plus
any **unmapped** ids. Edit `device.dps_map` (and `device.scaling`, e.g.
`temperature: 0.1` if the device reports tenths) in `config.yaml` until every
parameter resolves correctly. If polling returns nothing, try
`version: 3.4` or `3.5`.

## 6. Run the services (manual)

```bash
python -m aqm.poller_main config.yaml     # ingest loop
python -m aqm.rollup_main config.yaml     # rollup scheduler (--once for a single run)
python -m aqm.web_main config.yaml        # dashboard at http://<pi-ip>:8000
```

Open `http://<pi-ip>:8000` from any device on the LAN.

## 7. Deploy with systemd (boot persistence)

```bash
sudo mkdir -p /opt/air_quality_monitor
sudo cp -r . /opt/air_quality_monitor
cd /opt/air_quality_monitor
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

sudo cp deploy/aqm-poller.service /etc/systemd/system/
sudo cp deploy/aqm-rollup.service /etc/systemd/system/
sudo cp deploy/aqm-web.service   /etc/systemd/system/
# Edit the unit files if your user/paths differ (default user 'pi',
# path /opt/air_quality_monitor).

sudo systemctl daemon-reload
sudo systemctl enable --now aqm-poller aqm-rollup aqm-web
sudo systemctl status aqm-poller aqm-rollup aqm-web
```

After a reboot, the dashboard returns automatically.

## Retention

Raw readings live in a MongoDB **time-series collection** with a TTL index
(`mongo.raw_retention_seconds`, default 30 days). Rollup collections
(`rollup_daily/weekly/monthly`) are kept indefinitely for long-term trends.

## Network / access

- The web server binds to `web.host` (default `0.0.0.0`, port `8000`) — reachable
  on the LAN. For LAN-only, do not port-forward 8000 on your router.
- MongoDB listens on localhost by default; keep it that way for a single-Pi
  deployment.

## API

| Endpoint | Description |
| --- | --- |
| `GET /health` | Liveness check |
| `GET /api/parameters` | List of parameters (key, label, unit) |
| `GET /api/current` | Latest reading `{ts, values}` |
| `GET /api/history?metric=&bucket=&from=&to=` | Per-bucket stats (avg/stddev/min/max/count) |
| `GET /api/alerts` | Active alerts |
| `GET /api/stream` | SSE stream of `{reading, alerts}` |

`bucket` ∈ `minute`, `hourly` (on-demand) and `daily`, `weekly`, `monthly`
(rollups). `from`/`to` are ISO-8601; defaults to the last 24h.

## Development & tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests run without hardware or a live MongoDB: device access and the aggregation
pipeline are exercised through pure functions and mocks. `mongomock` cannot
execute `$dateTrunc` or create time-series collections, so the bucketing math
is verified in `aqm/stats.py` (the same engine the rollup job uses) and the
MongoDB pipeline is verified structurally. End-to-end `$dateTrunc` aggregation
runs live on the Pi's MongoDB 7.0.
```

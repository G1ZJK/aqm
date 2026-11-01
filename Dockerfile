# Air Quality Monitor — application image.
# One image runs all three services (poller / rollup / web); the service is
# chosen by the command in docker-compose.yml.
#
# python:3.12-slim-bookworm has official linux/arm64 variants, so this builds
# and runs natively on a Raspberry Pi 5 (64-bit Raspberry Pi OS).

FROM python:3.12-slim-bookworm AS base

# Faster, cleaner Python in containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application package (includes templates + static assets).
COPY aqm ./aqm

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Config is provided at runtime via a read-only mount (see docker-compose.yml).
# AQM_CONFIG points the loader at the mounted file; AQM_MONGO_URI overrides the
# Mongo host so the same config.yaml works outside Docker too.
ENV AQM_CONFIG=/config/config.yaml

# Default to the web service; compose overrides this for poller/rollup.
EXPOSE 8000
CMD ["python", "-m", "aqm.web_main"]

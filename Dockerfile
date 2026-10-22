FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HC_DATA_DIR=/config

WORKDIR /srv

# Debian security fixes published since the base image was last rebuilt -
# the python:*-slim tags lag behind them by days to weeks.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY VERSION ./VERSION
RUN date -u +"%Y-%m-%d %H:%M UTC" > ./BUILD_DATE

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh && mkdir -p /config

# Starts as root, then drops to PUID:PGID if they're set (docker-entrypoint.sh)
# - /config is typically a bind-mounted host directory (Unraid, plain
# `docker run`, etc.) created root-owned by the Docker daemon, so the
# entrypoint takes ownership of it first. Without PUID/PGID it stays root,
# as earlier versions always did.

EXPOSE 8080 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/healthz', timeout=3)" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "app.run"]

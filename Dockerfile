FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HC_DATA_DIR=/config

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY VERSION ./VERSION
RUN date -u +"%Y-%m-%d %H:%M UTC" > ./BUILD_DATE

RUN mkdir -p /config

# Runs as root: /config is typically a bind-mounted host directory (Unraid,
# plain `docker run`, etc.) created root-owned by the Docker daemon, and a
# non-root app user would otherwise be unable to write the SQLite DB/secret
# key to it. Low-risk tradeoff for a homelab monitoring tool with no
# untrusted input execution.

EXPOSE 8080 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/healthz', timeout=3)" || exit 1

CMD ["python", "-m", "app.run"]

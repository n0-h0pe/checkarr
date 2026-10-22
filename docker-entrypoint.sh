#!/bin/sh
# Runs Checkarr as PUID:PGID when they're set (the Unraid template sets
# 99:100, nobody:users), taking ownership of /config first so a volume
# created by an older root-only image stays writable. Without them it runs
# as root, same as before - /config is often a host directory the Docker
# daemon created root-owned, which a non-root user couldn't write to.
set -e

umask "${UMASK:-022}"

if [ "$(id -u)" = "0" ] && [ -n "$PUID" ] && [ "$PUID" != "0" ]; then
    if command -v setpriv >/dev/null 2>&1; then
        PGID="${PGID:-$PUID}"
        find /config \( ! -user "$PUID" -o ! -group "$PGID" \) -exec chown "$PUID:$PGID" {} +
        exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups -- "$@"
    fi
    echo "docker-entrypoint: setpriv not found, ignoring PUID/PGID and running as root" >&2
fi

exec "$@"

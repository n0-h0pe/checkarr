# Security notes

- API keys are encrypted with Fernet before being stored in SQLite, using a
  key from `HC_APP_SECRET_KEY` if set, otherwise a key generated on first
  run and persisted to `/config/secret.key`. Set `HC_APP_SECRET_KEY` and
  back it up, if the generated key file is lost, stored API keys can't be
  decrypted and services will need their keys re-entered. This only applies
  to secrets actually stored in the database, one sourced from an
  environment variable never touches this encryption at all, by design.
- The admin web UI/API (port 8080) has no authentication by default (fine
  on a trusted LAN behind your own reverse proxy/VPN). Set `HC_AUTH_USERNAME`
  and `HC_AUTH_PASSWORD` to require HTTP Basic Auth for it. This does not
  apply to the public dashboard port (8090), which is unauthenticated by
  design, see Public dashboard above.
- Filesystem checks only ever read paths you've explicitly bind-mounted
  read-only, the container does not need write access to your media.
- "Sign in to Plex" never sees your Plex password, it uses Plex's standard
  PIN-based sign-in flow: this app only ever receives the resulting token,
  via a popup hosted on plex.tv itself.

# Security notes

- On first boot a setup guide asks where the encryption key below should
  live (and can generate one for `HC_APP_SECRET_KEY` in your browser), walks
  through adding a first service, and shows where everything else is.
  Settings > Customizations > Show setup guide opens it again.

- API keys are encrypted with Fernet before being stored in SQLite, using a
  key from `HC_APP_SECRET_KEY` if set, otherwise a key generated on first
  run and persisted to `/config/secret.key`. Set `HC_APP_SECRET_KEY` and
  back it up, if the generated key file is lost, stored API keys can't be
  decrypted and services will need their keys re-entered. This only applies
  to secrets actually stored in the database, one sourced from an
  environment variable never touches this encryption at all, by design.
  The FTP check's password is encrypted the same way, and never sent back
  out by the API once saved.
- The admin web UI/API (port 8080) has no authentication by default (fine
  on a trusted LAN behind your own reverse proxy/VPN). Set `HC_AUTH_USERNAME`
  and `HC_AUTH_PASSWORD` to require HTTP Basic Auth for it. This does not
  apply to the public dashboard port (8090), which is unauthenticated by
  design, see Public dashboard above.
- The public dashboard port only ever gets each service's name, type, icon
  and check results - never its addresses, username, notes or any check's
  settings.
- The admin app refuses any state-changing request (add, edit, delete,
  prune, test...) a browser sends from another site, so a web page you
  happen to visit can't quietly make changes through your browser. Scripts
  and tools like curl are unaffected.
- Ordinary checks don't verify TLS certificates (so self-signed local
  HTTPS just works) - the separate SSL certificate check is what reports
  certificate problems. That also means an API key sent to a remote
  `https://` address isn't protected against someone able to intercept that
  connection; prefer a VPN or the local address for API-heavy checks.
- Email alerts verify the SMTP server's certificate. Turn off "Verify the
  server's TLS certificate" on the channel only for a local relay with a
  self-signed one.
- Set `PUID`/`PGID` to run the container as an ordinary user rather than
  root - see [DeployingCheckarr.md](DeployingCheckarr.md).
- Filesystem checks only ever read paths you've explicitly bind-mounted
  read-only, the container does not need write access to your media.
- "Sign in to Plex" never sees your Plex password, it uses Plex's standard
  PIN-based sign-in flow: this app only ever receives the resulting token,
  via a popup hosted on plex.tv itself.

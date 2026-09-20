# Friends-only deployment

Gravity Wars enforces access in FastAPI. Caddy supplies TLS and same-origin
routing; Next.js only provides an early UI gate. A copied or fabricated
frontend cookie cannot authorize an API request or WebSocket action.

## One-time admin setup

Create the only administrator password hash on a trusted machine. The command
prompts twice without echoing the password; the password itself is never a
command-line argument or log entry.

```bash
cd /srv/gravitywars
mkdir -p secrets
chmod 700 secrets
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
umask 077
python -m app.auth.cli hash-password > ../secrets/admin_password_hash
chmod 600 ../secrets/admin_password_hash
```

Only the Argon2id hash is written. Keep `secrets/` out of Git and backups with
broader readership. There is deliberately no default password and production
startup fails if the hash file is missing or empty. To change the password,
generate a replacement file in the same way and recreate only the API
container. Sign out before rotating the password; changing the hash does not
silently delete existing server-side sessions, which expire after 12 hours.

## Atlas migration

1. Pull or copy the reviewed revision into `/srv/gravitywars` on Atlas. Keep it
   as a separate Compose project; do not edit Mnemosyne files or services.
2. Generate `secrets/admin_password_hash` as above.
3. Copy `.env.example` to `.env` and set `CADDY_NETWORK_NAME` to the existing
   Docker network shared by Caddy. Confirm with `docker network ls`; do not
   guess the name.
4. Build and start only this project:

   ```bash
   cd /srv/gravitywars
   docker compose config
   docker compose build
   docker compose up -d
   docker compose ps
   ```

   The Compose file publishes no host ports and explicitly keeps Uvicorn at
   one worker because game state is in memory.
5. Merge `deploy/Caddyfile.gravity-wars.example` into the existing Caddy
   configuration. Preserve every unrelated site block. Validate using the
   existing Caddy container's configuration command, then reload Caddy through
   its existing management procedure. Do not restart or replace the shared
   Caddy service as part of the Gravity Wars Compose project.
6. Check `https://gravity-wars.karloverse.dev/api/health`, verify the private
   gate in a clean browser, then sign in and run a four-browser smoke game.

No `NEXT_PUBLIC_*` variable is needed in production. Browser API calls and
WebSockets use the production origin and Caddy routes `/api/*` and `/ws/*` to
the private API container. The configured origin is checked again on login,
invitation redemption, cookie-authenticated mutations, and WebSocket upgrades.
The example's `request_body` defense-in-depth directive requires Caddy 2.10 or
newer. The API independently enforces the same 16 KiB limit, including streamed
bodies; if the shared Caddy is older, remove only that stanza during the
reviewed merge rather than changing the unrelated proxy deployment.

## State, cleanup, and backup

Lobby and match state remain in the single API process and do not survive an
API restart or deployment. On startup, access records tied to those vanished
lobbies are invalidated, so an old invitation or guest session fails closed.
Admin and guest session tokens, CSRF tokens, and invitation secrets are stored
only as SHA-256 digests in the private SQLite volume. Expired sessions and
orphaned lobby records are cleaned automatically. The database directory is
mode `0700` and the database mode `0600` inside the container.

For a consistent online backup, use SQLite's backup operation, then copy the
result to a restricted directory and remove the in-container copy:

```bash
cd /srv/gravitywars
docker compose exec -T api python -c "import sqlite3; source=sqlite3.connect('/data/access.sqlite3'); target=sqlite3.connect('/data/access-backup.sqlite3'); source.backup(target); target.close(); source.close()"
umask 077
docker cp gravitywars-api:/data/access-backup.sqlite3 ./access-backup.sqlite3
docker compose exec -T api python -c "from pathlib import Path; Path('/data/access-backup.sqlite3').unlink(missing_ok=True)"
```

Treat the backup as private security data even though it contains no raw
password, cookie, player token, or invitation secret.

## Logging and privacy

Invitation links use `/invite#secret`. URL fragments are not sent in HTTP
requests, proxy logs, Referer headers, or link-preview GETs. Redemption sends
the secret only in the POST body; the supplied Caddy access log does not record
bodies or request headers. Do not enable Caddy debug/header logging or FastAPI
body logging for this site. Uvicorn access logs are disabled in the container.
The invitation page has no third-party assets and all app responses set
`Referrer-Policy: no-referrer`.

This is a technical friends-only access control system. It is not a legal
determination or a guarantee of any GDPR, Impressum, or other exemption.

## Rollback

Before an update, record the running image IDs with `docker compose images` and
make the SQLite backup above. To roll back, check out the prior reviewed
revision (or restore its tagged images) and run `docker compose up -d --build`.
Restore the database backup only if the rollback specifically requires it;
stop the Gravity Wars project first and never overwrite a live SQLite file.
Reload the previous Gravity Wars Caddy site block only if routing changed.
Rollback or restart ends all in-memory lobbies and matches, but it must not
touch the shared Caddy container or Mnemosyne Compose project.

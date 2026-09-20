# Gravity Wars

A private four-player browser game built with FastAPI, native WebSockets,
Next.js, TypeScript, and Tailwind CSS. One configured administrator hosts a
lobby and sends three single-use invitation links; there is no public signup,
PIN join, lobby browser, or guest password.

## Run locally

Create a private Argon2id administrator hash. The password is entered through
the terminal prompt and is neither echoed nor placed in shell history:

```bash
mkdir -p secrets
chmod 700 secrets
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
umask 077
python -m app.auth.cli hash-password > ../secrets/admin_password_hash
chmod 600 ../secrets/admin_password_hash
```

Start the API:

```bash
cd backend
source .venv/bin/activate
ADMIN_PASSWORD_HASH_FILE=../secrets/admin_password_hash \
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000 \
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal, start Next.js:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`, choose **Administrator sign in**, and use the
password entered above. A host action creates one lobby and exactly three
invitations. Invitation secrets stay after `#` in each URL, so GET requests and
messenger link previews do not redeem or log them.

## Phones on the same LAN

Use the development computer's LAN address in both configurations. For example,
if it is `192.168.1.23`, run the API with:

```bash
ADMIN_PASSWORD_HASH_FILE=../secrets/admin_password_hash \
ALLOWED_ORIGINS=http://192.168.1.23:3000 \
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Set `frontend/.env.local` to:

```dotenv
NEXT_PUBLIC_API_ORIGIN=http://192.168.1.23:8000
NEXT_PUBLIC_WS_ORIGIN=ws://192.168.1.23:8000
```

Start Next.js on `0.0.0.0` with `npm run dev`, allow ports 3000 and 8000 only
on the trusted LAN if the local firewall requires it, and open
`http://192.168.1.23:3000` on each device.

## Verification

```bash
cd backend
source .venv/bin/activate
python -m unittest discover -s tests -v

cd ../frontend
npm run typecheck
npm run lint
npm run build
```

Browser tests expect already-running local servers and a test-only password
that matches the backend hash:

```bash
E2E_ADMIN_PASSWORD='the password entered for the local test hash' npm run test:e2e
```

Do not reuse the production password for tests or put it in a committed file.

## Production

The production Compose stack publishes no API or web ports, uses one Uvicorn
worker, mounts a private SQLite volume for access state, and connects only to
the existing external Caddy network. See
[friends-only deployment](docs/friends-only-deployment.md) for Atlas migration,
Caddy routing, credential bootstrap, backup/cleanup, and rollback instructions.
Those instructions do not deploy, restart shared Caddy, or modify Mnemosyne.

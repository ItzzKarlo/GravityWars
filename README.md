# Gravity Wars

A four-player browser game built with FastAPI, native WebSockets, Next.js, TypeScript, and Tailwind CSS.

## Run locally

Start the API:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal, start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend uses the browser's current hostname with port `8000` for the API by default, so this setup also works from another device on the same network.

## Play from a phone on the same LAN

1. Find the development computer's LAN address, for example `192.168.1.23`.
2. Start both servers with the `0.0.0.0` host commands above.
3. Allow ports `3000` and `8000` through the computer's firewall if necessary.
4. Set the backend's allowed frontend origin and restart it:

```bash
FRONTEND_ORIGIN=http://192.168.1.23:3000 uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. On the phone, open `http://192.168.1.23:3000`.

For a nonstandard API host or port, copy `frontend/.env.example` to `frontend/.env.local` and set both public origins before starting or building Next.js. Invitation links always use the origin from which the frontend was opened; they never contain player session tokens.

## Checks

```bash
cd backend && python -m unittest discover -s tests -v
cd frontend && npm run typecheck && npm run lint && npm run build
```

# MinerWatch (Albedo_RADAR)

Real-time miner intelligence / model-commitment tracking for Bittensor SN97 (Albedo).

- `backend/` — Python 3.12 FastAPI API (`app.main:app`) + a collector (`app.collectors.commitment_poller`). Async SQLAlchemy → PostgreSQL, Redis for the live SSE feed. Bittensor SDK reads chain state.
- `frontend/` — Next.js 15 / React 19 dashboard. It proxies the browser's `/api/v1/*` calls to the FastAPI backend.

## Cursor Cloud specific instructions

The update script provisions the Python venv (`backend/.venv`) and frontend `node_modules`. PostgreSQL, Redis and the `minerwatch` DB/user are provisioned once during environment setup and persist in the VM snapshot. The notes below are the non-obvious things needed to actually run things.

### Start the datastores (they do NOT auto-start)
There is no systemd in the VM, so start them manually each session:

```
sudo pg_ctlcluster 16 main start
sudo redis-server --daemonize yes
```

The DB/user already exist (`postgresql+asyncpg://minerwatch:minerwatch@localhost:5432/minerwatch`). If the cluster is ever missing the role/db, recreate with:
`sudo -u postgres psql -c "CREATE USER minerwatch WITH PASSWORD 'minerwatch';" -c "CREATE DATABASE minerwatch OWNER minerwatch;"`

The backend config (`backend/app/config.py`) defaults already point at `localhost` Postgres/Redis, so no `.env` is required for local dev.

### Run the API and frontend (dev mode)
- API: from `backend/`, `.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`. Schema/tables are auto-created on startup (`init_db`), so no manual migration step.
- Frontend: from `frontend/`, `npm run dev` (port 3000). The browser hits the same-origin proxy `frontend/src/app/api/v1/[...path]/route.ts`, which forwards to `API_URL`/`NEXT_PUBLIC_API_URL` (default `http://localhost:8000/api/v1`). Both must be running for the dashboard to show data.
- Health checks: `GET /health` and `GET /health/db`.

### Collector caveat (key gotcha)
`app.collectors.commitment_poller` and several `/api/v1` endpoints with `live=true` (and `/commitments/onchain`) connect to the **live Bittensor `finney` network** via the SDK. That outbound chain access is generally unavailable in the cloud VM, so the collector will not populate the DB here. The API + dashboard run fully against PostgreSQL; to demo with data, seed the DB directly (insert `Miner` / `MinerCommitment` / `MinerSlotStatus` rows for subnet 97, version `v6`) — this is exactly what the collector would otherwise write. `bittensor` imports inside the API routes are lazy, so the API starts fine without chain access.

### Tests / lint / build
- Backend tests: from `backend/`, `PYTHONPATH=backend .venv/bin/python -m pytest --asyncio-mode=auto` (the 2 async tests in `test_market_client.py` need `pytest-asyncio`, which the update script installs; `--asyncio-mode=auto` is required since there is no pytest config). All 41 tests are offline/unit.
- Frontend build: `npm run build` (works).
- `npm run lint` (`next lint`) is **not usable non-interactively** — ESLint is not configured in the repo and the command drops into an interactive setup prompt. Don't rely on it; use `npm run build` (includes type checking) for verification.

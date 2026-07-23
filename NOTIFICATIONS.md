# Notifications — Slack

## Problem

After `docker compose build && up`, the collector **fresh-fetches everything** (repos, commits, duels). That looks like "new" data but isn't — you only want Slack for **real changes after the dashboard is warm**.

## Solution: grace + sync gates + seed

Notifications go live only when **all** of these are true:

| Gate | Default | Purpose |
|------|---------|---------|
| `NOTIFICATION_GRACE_SECONDS` | **300** (5 min) | Minimum wait after collector start |
| Full chain scan | automatic | All on-chain commits loaded once |
| `NOTIFICATION_MIN_HUB_INDEX_PROBES` | **1** | Lightweight Hippius hub HTTP fetch (no DB) |
| `NOTIFICATION_STARTUP_MAX_SECONDS` | **600** (10 min) | Go LIVE anyway if hub probe cannot run |
| Startup seed | automatic | Mark DB (best-effort) + dashboard + hub index as "already seen" |

**Live time** ≈ `max(5 min, full scan done, 1× hub probe OR 10 min cap)` — then only **new** deltas post to `#albedo`.

Repo track (`REPO_TRACK` in logs) is for **dashboard DB sync only** — it does **not** gate Slack. If your DB is flaky, notifications still go LIVE via HTTP hub probes.

Grace runs on **every** collector start (including restarts with Postgres data). Prior alerts in the DB are only used for dedupe — they do **not** skip grace. Set `NOTIFICATION_SKIP_STARTUP_GRACE=true` only if you explicitly want instant live mode.

## Config (`.env`)

```env
NOTIFICATIONS_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_CHANNEL=#albedo
SLACK_APP_NAME=Albedo_Notification

NOTIFICATION_GRACE_SECONDS=300
NOTIFICATION_MIN_HUB_INDEX_PROBES=1    # HTTP only; 0 = skip hub gate
NOTIFICATION_STARTUP_MAX_SECONDS=600   # fallback LIVE cap
```

### Tuning guide

| Situation | Try |
|-----------|-----|
| Still bulk flood at ~2 min | Check logs for `skip-startup-grace` — grace may be bypassed |
| Want fastest LIVE (DB unreliable) | `NOTIFICATION_MIN_HUB_INDEX_PROBES=0` (grace + full scan only) |
| Hub API slow | Wait for fallback or lower grace; check `HUB_PROBE` logs |
| `REPO_TRACK failed` in logs | Dashboard repo sync issue — **does not block Slack** anymore |
| Want faster alerts on restart | `NOTIFICATION_SKIP_STARTUP_GRACE=true` (not recommended) |

## Deploy

```bash
cp .env.example .env
docker compose build --no-cache collector api
docker compose up -d --force-recreate collector api
```

## Verify

```bash
curl http://localhost:8000/api/v1/notifications/status
curl -X POST http://localhost:8000/api/v1/notifications/test-slack
docker compose logs --tail 500 collector 2>&1 | grep -iE 'NOTIFY_STATUS|notifications LIVE|HUB_PROBE|ALERT |NOTIFICATIONS netuid'
```

`notifications/status` includes `collector_live`, `eval_pipeline` (Hippius validate queue depth), and `alerts_by_kind` / `slack_sent_by_kind` so you can confirm eval alerts are recording and delivering.

Expected sequence:

```
notifications grace period until ... (300s) — initial fetch will NOT post to Slack
HUB_PROBE netuid=97 albedo_repos=142 ... startup_probe=1/1
notifications LIVE from ... — only changes after docker startup are sent
```

```bash
curl -X POST http://localhost:8000/api/v1/notifications/test-slack
```

## Per-kind settings (dashboard)

Use **Notifications** in the MinerWatch header (bell icon) or `GET/PATCH /api/v1/notifications/settings` to toggle Slack alerts per event type.

Defaults (when unset in Redis):

| Kind | Default |
|------|---------|
| Eval / duel / crown / reg fee | **on** |
| `repo_new`, `repo_updated` | **off** |
| On-chain commit / slot kinds | **off** |
| `github_commit` | **on** |

`NOTIFICATIONS_ENABLED=false` in `.env` disables everything regardless of dashboard toggles.

## What notifies after live

| Event | Kind |
|-------|------|
| Model enters eval validation queue | `eval_queue_entered` |
| New duel | `duel_new` |
| Reg fee crosses below 0.55 τ | `reg_fee_low` |
| Crowned | `crown_won` |
| King defended | `king_defended` |
| Crown lost | `crown_lost` |
| Eval disqualified | `eval_dq` |
| Eval infra failed (validation) | `eval_dq` (`TERMINAL_INFRA_FAILED`) |
| **New Hippius or Hugging Face repo** | `repo_new` |

`repo_new` fires only the first time a repo appears on Hippius Hub or Hugging Face (manifest updates do **not** notify).

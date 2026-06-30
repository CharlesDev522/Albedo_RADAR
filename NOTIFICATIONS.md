# Notifications — Slack

## Problem

After `docker compose build && up`, the collector **fresh-fetches everything** (repos, commits, duels). That looks like "new" data but isn't — you only want Slack for **real changes after the dashboard is warm**.

## Solution: grace + sync gates + seed

Notifications go live only when **all** of these are true:

| Gate | Default | Purpose |
|------|---------|---------|
| `NOTIFICATION_GRACE_SECONDS` | **300** (5 min) | Minimum wait after collector start |
| Full chain scan | automatic | All on-chain commits loaded once |
| `NOTIFICATION_MIN_REPO_TRACK_PASSES` | **2** | Hub/repo index scanned twice (catches slow discovery) |
| Startup seed | automatic | Mark all ingested DB + dashboard state as "already seen" |

**Live time** = `max(5 min, full scan done, 2× repo track)` — then only **new** deltas post to `#albedo`.

Grace runs on **every** collector start (including restarts with Postgres data). Prior alerts in the DB are only used for dedupe — they do **not** skip grace. Set `NOTIFICATION_SKIP_STARTUP_GRACE=true` only if you explicitly want instant live mode.

## Config (`.env`)

```env
NOTIFICATIONS_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_CHANNEL=#albedo
SLACK_APP_NAME=Albedo_Notification

# Tune if you still see bulk after docker up:
NOTIFICATION_GRACE_SECONDS=300          # 5 min (try 600 for slow machines)
NOTIFICATION_MIN_REPO_TRACK_PASSES=2   # try 3 if hub index is slow
```

### Tuning guide

| Situation | Try |
|-----------|-----|
| Still bulk flood at ~2 min | Check logs for `skip-startup-grace` or `resume mode` — grace may be bypassed. Otherwise try `NOTIFICATION_GRACE_SECONDS=600` |
| Repos trickle in slowly | `NOTIFICATION_MIN_REPO_TRACK_PASSES=3` |
| Want faster alerts on restart | `NOTIFICATION_SKIP_STARTUP_GRACE=true` (not recommended — can re-flood Slack) |
| Fresh empty DB every build | Grace + seed always runs — this is correct |

## Deploy

```bash
cp .env.example .env
docker compose build --no-cache collector api
docker compose up -d --force-recreate collector api
```

## Verify

```bash
curl http://localhost:8000/api/v1/notifications/status
docker compose logs collector | grep -i notification
```

Expected sequence:

```
notifications grace period until ... (300s) — initial fetch will NOT post to Slack
notifications not live yet — grace 240s remaining; SN97 waiting for 1 more repo track pass(es)
notifications LIVE from ... — only changes after docker startup are sent
```

```bash
curl -X POST http://localhost:8000/api/v1/notifications/test-slack
```

## What notifies after live

| Event | Kind |
|-------|------|
| New repo | `repo_new` |
| New duel | `duel_new` |
| New on-chain commit | `commit_new` |
| Reg fee drops below 0.75 τ | `reg_fee_low` |
| Crowned | `crown_won` |
| King defended | `king_defended` |
| Crown lost | `crown_lost` |

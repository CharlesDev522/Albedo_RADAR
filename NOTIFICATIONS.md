# Notifications — Slack

MinerWatch sends **Slack-only** alerts for **genuinely new** changes after `docker compose up`.

## 60-second grace period (fixes bulk flood)

On fresh `docker compose up`:

1. **0–60s grace** — collector ingests all repos, commits, slots, duels silently (no Slack)
2. **After 60s** — seeds everything already in DB + dashboard as "seen"
3. **Live** — only real new changes post to `#albedo`

```env
NOTIFICATION_GRACE_SECONDS=60
```

Collector logs:

```
notifications grace period until 2026-... (60s) — initial fetch will NOT post to Slack
notifications LIVE from 2026-... — only changes after docker grace are sent
```

Restarts with existing alert history skip grace (resume mode).

## What notifies

| Your event | Alert kind | When it fires |
|------------|------------|---------------|
| New repo on hub | `repo_new` | Hub discovers a repo not seen before |
| New duel started | `duel_new` | New `current_eval.eval_run_id` |
| New on-chain commit | `commit_new` | New v6 commitment for a hotkey |
| Reg fee drops below threshold | `reg_fee_low` | Burn crosses below 0.75 τ |
| Duel finish — crowned | `crown_won` | `coronated: true` |
| Duel finish — king defended | `king_defended` | Finished duel, challenger lost |
| King reign ended | `crown_lost` | `king_version` changes |

## Setup

```bash
cp .env.example .env
# set SLACK_WEBHOOK_URL, SLACK_CHANNEL=#albedo, SLACK_APP_NAME=Albedo_Notification
docker compose build --no-cache collector api
docker compose up -d --force-recreate collector api
```

## Verify

```bash
curl http://localhost:8000/api/v1/notifications/status
curl -X POST http://localhost:8000/api/v1/notifications/test-slack
docker compose logs collector | grep -i notification
```

## How it works

```
docker compose up
  → 60s grace (silent ingest)
  → seed all DB + dashboard state as seen
  → LIVE — only new deltas → Slack #albedo
```

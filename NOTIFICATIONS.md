# Notifications — Slack

MinerWatch sends **Slack-only** alerts for live changes detected **after** collector startup (no bulk flood on `docker compose up`).

## What notifies (your requirements)

| Your event | Alert kind | When it fires | Post-startup only |
|------------|------------|---------------|-------------------|
| New repo on hub | `repo_new` | Hippius/hub index discovers a repo not seen before | Yes — startup sync is silent |
| New duel started | `duel_new` | `current_eval` gets a new `eval_run_id` | Yes — live duel at boot is seeded |
| New on-chain commit | `commit_new` | New v6 commitment row for a hotkey | Yes |
| Reg fee drops below threshold | `reg_fee_low` | Burn crosses **below** 0.75 τ (edge-triggered) | Yes — already-low fee at boot is seeded |
| Duel finish — crowned | `crown_won` | `eval_runs` entry with `coronated: true` | Yes — history bootstrapped |
| Duel finish — king defended | `king_defended` | Finished duel, `challenger_won: false` | Yes — history bootstrapped |
| King reign ended | `crown_lost` | `king_version` changes in reign | Yes |

### Also sent (optional noise — on-chain/hub)

| Alert kind | When |
|------------|------|
| `commit_updated` | On-chain digest changes |
| `repo_updated` | Hub manifest digest changes |
| `slot_new` / `slot_changed` | Slot commitment changes |

## Troubleshooting — no Slack messages

### 1. Create `.env` (required)

```bash
cp .env.example .env
```

Edit `.env` and set your real webhook:

```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T07UP6DQ519/...
SLACK_CHANNEL=#albedo
SLACK_APP_NAME=Albedo_Notification
NOTIFICATIONS_ENABLED=true
```

### 2. Recreate collector (loads new env)

```bash
docker compose up -d --force-recreate collector
```

### 3. Check status

```bash
curl http://localhost:8000/api/v1/notifications/status
```

`webhook_configured` must be `true`.

### 4. Send test message

```bash
curl -X POST http://localhost:8000/api/v1/notifications/test-slack
```

You should see a test message in `#albedo` immediately.

### 5. Check collector logs

```bash
docker compose logs collector | grep -i notification
```

Look for:

```
notifications: enabled webhook=set channel=#albedo ...
notifications armed after startup sync ...
```

If you see `SLACK_WEBHOOK_URL is missing` — `.env` is not loaded; fix step 1–2.

---

```bash
cp .env.example .env
# set SLACK_WEBHOOK_URL, SLACK_CHANNEL=#albedo, SLACK_APP_NAME=Albedo_Notification
docker compose build --no-cache collector
docker compose up -d
```

Collector log when ready:

```
notifications armed after startup sync — only new events from 2026-... will post to Slack
```

## Slack config (`.env`)

```env
NOTIFICATIONS_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_CHANNEL=#albedo
SLACK_APP_NAME=Albedo_Notification
NOTIFICATION_REG_FEE_THRESHOLD_TAO=0.75
```

## How it works

```
docker compose up
  → collector DISARMED
  → full sync (repos, commits, slots, duels) — silent
  → notifications ARMED
  → only deltas after this point → Slack #albedo
```

Dedup: in-memory cache + `alert_notifications.source_key` in PostgreSQL.

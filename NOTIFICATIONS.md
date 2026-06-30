# Notifications — Slack

MinerWatch emits **kind-tagged alerts** from the collector (Docker) and delivers them to **Slack** (`#albedo` via `Albedo_Notification`).

## Alert kinds

| Kind | Label | Example title |
|------|-------|---------------|
| `crown_won` | Crowned | `[crown_won] cyantest/model` |
| `crown_lost` | Crown Lost | `[crown_lost] king v3` |
| `commit_new` | New Commit | `[commit_new] uid 12 — repo/ns` |
| `commit_updated` | Commit Updated | `[commit_updated] uid 12 — repo/ns` |
| `slot_new` | New Slot | `[slot_new] uid 5 — timelock` |
| `slot_changed` | Slot Changed | `[slot_changed] uid 5 — timelock` |
| `repo_new` | New Repo | `[repo_new] namespace/repo` |
| `repo_updated` | Repo Updated | `[repo_updated] namespace/repo` |
| `reg_fee_low` | Low Reg Fee | `[reg_fee_low] SN97 — 0.6200 τ` |

Each alert has a **message** line plus ordered **detail** fields (uid, hotkey, digest, margins, etc.).

---

## Docker setup

1. Copy env file:

```bash
cp .env.example .env
```

2. Set Slack webhook in `.env`:

```env
NOTIFICATIONS_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_CHANNEL=#albedo
SLACK_APP_NAME=Albedo_Notification
NOTIFICATION_REG_FEE_THRESHOLD_TAO=0.75
ALBEDO_NOTIFICATION_POLL_SECONDS=15
```

3. Build and run:

```bash
docker compose build --no-cache api collector
docker compose up -d
```

The **collector** sends Slack alerts and persists them to PostgreSQL.

**Startup behavior:** on first `docker compose up` (empty alert history), the collector completes one full sync (commits, slots, repos, crown bootstrap) **without** posting to Slack, then arms notifications. Only events detected **after** that point are sent. Restarts with existing alert history arm immediately.

---

## Alert history API (optional)

- `GET /api/v1/notifications?since_id=0&limit=50&kinds=crown_won,commit_new`

---

## How it works

```
collector (Docker)
  ├─ commits / slots / repos → NotificationDispatcher
  ├─ crown + reg fee poll    → NotificationWatcher
  ├─ dedupe (memory + DB)    → alert_notifications table
  ├─ startup gate            → suppress until first sync done
  └─ Slack webhook           → #albedo
```

On **fresh install**, crown history is bootstrapped (no flood of old coronations).

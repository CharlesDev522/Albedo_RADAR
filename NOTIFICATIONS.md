# Notifications — Slack + Windows 11

MinerWatch emits **kind-tagged alerts** from the collector (Docker) and delivers them via **Slack** and/or a **desktop notifier**.

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

## Docker setup (recommended)

1. Copy env file:

```bash
cp .env.example .env
```

2. Set Slack webhook in `.env`:

```env
NOTIFICATIONS_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_CHANNEL=#albedo-alerts
NOTIFICATION_REG_FEE_THRESHOLD_TAO=0.75
ALBEDO_NOTIFICATION_POLL_SECONDS=15
```

3. Build and run:

```bash
docker compose build --no-cache api collector
docker compose up -d
```

The **collector** sends Slack alerts and persists them to PostgreSQL. No extra setup required for Slack.

4. Optional — log notifier container (polls API inside Docker network):

```bash
docker compose --profile notifier up -d notifier
```

This service logs kind-tagged alerts to stdout. For **native Win11 toasts**, run the client on your Windows host (below).

---

## Windows 11 desktop toasts

Run on your **Windows PC** (points at Docker API on `localhost:8000`):

```powershell
cd backend
pip install -r requirements.txt -r requirements-notifier.txt
$env:MINERWATCH_API_URL = "http://localhost:8000/api/v1"
python -m app.notifiers.poll_client
```

Or use the legacy host script:

```powershell
pip install -r scripts/requirements-windows.txt
python scripts/windows_notifier.py
```

Optional filters:

```env
NOTIFIER_POLL_SECONDS=10
NOTIFIER_KINDS=crown_won,crown_lost,commit_new,reg_fee_low
NOTIFIER_ACK=true
```

---

## API

- `GET /api/v1/notifications?since_id=0&limit=50&kinds=crown_won,commit_new`
- `POST /api/v1/notifications/{id}/ack`

---

## How it works

```
collector (Docker)
  ├─ commits / slots / repos → NotificationDispatcher
  ├─ crown + reg fee poll    → NotificationWatcher
  ├─ dedupe (memory + DB)    → alert_notifications table
  └─ Slack webhook           → your channel

notifier (optional Docker profile OR Windows host)
  └─ polls GET /notifications → Win11 toast / logs
```

On **fresh install**, crown history is bootstrapped (no flood of old coronations).

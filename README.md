# Albedo_RADAR
MinerWatch

Real-time miner intelligence, tracking, and analytics platform for Bittensor subnets.

Overview

MinerWatch is a continuous monitoring and analytics platform designed to track miner activity across a Bittensor subnet.

The platform collects on-chain and subnet-level data, monitors miner behavior over time, and generates insights about:

UID changes
Hotkey movements
Coldkey ownership
Registration events
Deregistrations
Stake changes
Validator relationships
Rank & emission trends
Performance history
Wallet clustering
Miner migration patterns

The goal is to provide a transparent view of subnet dynamics and help users understand how miners evolve over time.

Core Features
Miner Registry

Track every miner currently active within a subnet.

UID
Hotkey
Coldkey
Registration Block
First Seen
Last Seen
Current Status
Historical Timeline

Every miner receives a complete timeline.

2026-01-12 Registered
2026-02-03 UID changed
2026-03-08 Emission spike
2026-03-20 Stake added
2026-04-01 Deregistered
Hotkey Intelligence

Track hotkeys over time.

Features:

New hotkeys
Hotkey replacement
Hotkey transfers
Recycled hotkeys
Multiple UIDs using same hotkey
Coldkey Intelligence

Analyze wallet ownership.

Coldkey
 ├─ Miner A
 ├─ Miner B
 ├─ Miner C
 └─ Validator D

Metrics:

Number of miners
Total stake
Total emissions
Validator relationships
Emission Analytics

Track miner rewards.

Metrics:

Current emission
Daily emission
Weekly emission
Emission growth
Emission decline

Charts:

Emission History
Stake History
Rank History
Rank Tracking

Monitor rank evolution.

Rank #45
Rank #32
Rank #21
Rank #11
Rank #7

Detect:

Rising miners
Falling miners
Stable miners
Stake Analytics

Track:

TAO stake
Alpha stake
Delegation changes
Stake inflows
Stake outflows
Registration Monitor

Real-time feed.

New miner registered

UID: 87
Hotkey: xxxx
Coldkey: yyyy
Block: 8,123,555
Deregistration Monitor

Detect:

Miner removed
UID replaced
Subnet ejection
Leaderboards
Top Emission
#1 Miner A
#2 Miner B
#3 Miner C
Top Stake
#1 Miner A
#2 Miner B
#3 Miner C
Fastest Growth
30-Day Growth
New Rising Miners
Last 7 Days
Miner Relationship Graph

Visual graph showing:

Coldkey
   ↓
Hotkey
   ↓
UID

and

Coldkey
   ↓
Multiple Miners

Useful for discovering:

Miner farms
Large operators
Wallet clusters
Alerts

User-defined alerts.

Examples:

Notify when:

- New miner registers
- UID changes
- Emission > X
- Stake changes > X%
- Validator stake changes
Architecture
                 Bittensor Network
                         │
                         ▼
                Subtensor RPC Layer
                         │
                         ▼
                  Data Collectors
                         │
      ┌──────────────────┼──────────────────┐
      ▼                  ▼                  ▼
 Registration     Emission Poller      Stake Poller
 Monitor          Rank Monitor         Validator Monitor
      │                  │                  │
      └──────────────────┼──────────────────┘
                         ▼
                    Event Stream
                       (Kafka)
                         │
                         ▼
                 Processing Engine
                         │
      ┌──────────────────┼──────────────────┐
      ▼                  ▼                  ▼
 Miner State      Relationship      Trend Analysis
 Builder          Builder           Engine
      │                  │                  │
      └──────────────────┼──────────────────┘
                         ▼
                    PostgreSQL
                         │
                         ▼
                     ClickHouse
                   (Time Series)
                         │
                         ▼
                     REST API
                         │
                         ▼
                    Web Dashboard
Database Design
miners
id
uid
hotkey
coldkey
subnet
registered_at
first_seen
last_seen
status
emissions
id
miner_id
block
emission
timestamp
stakes
id
miner_id
stake
timestamp
rankings
id
miner_id
rank
timestamp
events
id
event_type
miner_id
data
timestamp
Technology Stack
Backend
Python
FastAPI
Bittensor SDK
SQLAlchemy
Storage
PostgreSQL
ClickHouse
Redis
Streaming
Kafka
Frontend
Next.js
React
TailwindCSS
Infrastructure
Docker
Kubernetes
Prometheus
Grafana
Future Roadmap
Phase 1
Miner tracking
UID history
Hotkey tracking
Coldkey tracking
Basic leaderboard
Phase 2
Emission analytics
Stake analytics
Historical charts
Alerts
Phase 3
Wallet clustering
Miner intelligence scoring
Operator detection
Predictive analytics
Phase 4
Cross-subnet tracking
Validator tracking
API marketplace
Public intelligence portal
Vision

MinerWatch aims to become the "Arkham Intelligence for Bittensor" — providing full transparency into miner activity, ownership patterns, emissions, and subnet evolution through real-time monitoring and historical analytics.

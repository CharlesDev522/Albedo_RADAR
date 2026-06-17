"""Real-time live feed via Server-Sent Events (Redis pub/sub)."""

from __future__ import annotations

import asyncio
import json
import logging
import time

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.subnet_commit_rules import model_versions_sql_tuple
from app.collectors.event_publisher import EventPublisher
from app.config import get_settings
from app.db.models import MinerCommitment
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/live", tags=["live"])
settings = get_settings()


@router.get("/stream")
async def live_stream(subnet: int = Query(default=97)):
    """SSE stream — pushes instantly when collector detects new/updated v6 commits."""

    async def event_generator():
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis.pubsub()
        await pubsub.subscribe(EventPublisher.LIVE_CHANNEL)

        # Send last known state for this subnet on connect
        cached = await redis.get(EventPublisher.STATE_KEY_PREFIX + str(subnet))
        if not cached:
            cached = await redis.get(EventPublisher.STATE_KEY)
        if cached:
            try:
                payload = json.loads(cached)
                if payload.get("subnet") == subnet:
                    yield f"event: commit\ndata: {cached}\n\n"
            except json.JSONDecodeError:
                pass
        yield f"event: connected\ndata: {json.dumps({'subnet': subnet, 'status': 'live'})}\n\n"

        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if message and message["type"] == "message":
                    try:
                        payload = json.loads(message["data"])
                        if payload.get("subnet") == subnet:
                            yield f"event: commit\ndata: {message['data']}\n\n"
                    except json.JSONDecodeError:
                        pass
                else:
                    # heartbeat keeps connection alive
                    yield f"event: ping\ndata: {json.dumps({'ts': time.time()})}\n\n"
        finally:
            await pubsub.unsubscribe(EventPublisher.LIVE_CHANNEL)
            await redis.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/recent")
async def recent_commits(
    subnet: int = Query(default=97),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lightweight poll endpoint — returns newest v6 commits (for fallback refresh)."""
    result = await db.execute(
        select(MinerCommitment)
        .where(
            MinerCommitment.subnet == subnet,
            MinerCommitment.version.in_(model_versions_sql_tuple(subnet)),
        )
        .order_by(MinerCommitment.last_updated.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    return {
        "subnet": subnet,
        "count": len(rows),
        "commits": [
            {
                "uid": r.uid,
                "hotkey": r.hotkey,
                "coldkey": r.coldkey,
                "registered_at_block": r.registered_at_block,
                "commit_block": r.commit_block,
                "repo": r.repo,
                "digest": r.digest,
                "model_uri": r.model_uri,
                "commit_source": r.commit_source,
                "last_updated": r.last_updated.isoformat() if r.last_updated else None,
            }
            for r in rows
        ],
    }

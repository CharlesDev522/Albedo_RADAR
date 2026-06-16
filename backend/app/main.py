"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.api.routes import (
    coldkeys,
    commitments,
    encrypted_commitments,
    events,
    hotkeys,
    leaderboards,
    live,
    miners,
    slot_status,
)
from app.config import get_settings
from app.db.init_db import init_db
from app.db.models import Miner, MinerCommitment
from app.db.session import engine, get_db
from app.schemas.miner import HealthResponse

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(engine)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="Real-time v6 commitment tracking and miner intelligence for Bittensor subnet 97",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = settings.api_prefix
app.include_router(live.router, prefix=api_prefix)
app.include_router(commitments.router, prefix=api_prefix)
app.include_router(encrypted_commitments.router, prefix=api_prefix)
app.include_router(slot_status.router, prefix=api_prefix)
app.include_router(miners.router, prefix=api_prefix)
app.include_router(leaderboards.router, prefix=api_prefix)
app.include_router(hotkeys.router, prefix=api_prefix)
app.include_router(coldkeys.router, prefix=api_prefix)
app.include_router(events.router, prefix=api_prefix)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        network=settings.bittensor_network,
        default_subnet=settings.default_subnet,
    )


@app.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)) -> dict:
    """Quick check: is the collector writing to PostgreSQL?"""
    miners = (await db.execute(select(func.count()).select_from(Miner))).scalar() or 0
    commits = (await db.execute(select(func.count()).select_from(MinerCommitment))).scalar() or 0
    uids = (
        await db.execute(
            select(MinerCommitment.uid)
            .where(MinerCommitment.subnet == settings.default_subnet, MinerCommitment.uid.isnot(None))
            .order_by(MinerCommitment.uid.asc())
        )
    ).scalars().all()
    return {
        "status": "ok" if commits > 0 else "empty",
        "miners_in_db": miners,
        "v5_commits_in_db": commits,
        "v5_uids": list(uids),
        "subnet": settings.default_subnet,
        "hint": "If v5_commits_in_db is 0, check GET /api/v1/commitments/onchain and collector logs",
    }

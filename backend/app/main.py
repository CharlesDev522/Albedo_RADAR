"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import coldkeys, commitments, events, hotkeys, leaderboards, miners
from app.config import get_settings
from app.db.models import Base
from app.db.session import engine
from app.schemas.miner import HealthResponse

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="Real-time v5 commitment tracking and miner intelligence for Bittensor subnet 97",
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
app.include_router(commitments.router, prefix=api_prefix)
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

"""Database schema initialization and migrations."""

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.migrate import run_migrations
from app.db.models import Base

logger = logging.getLogger(__name__)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_migrations(conn)
    logger.info("database schema ready")

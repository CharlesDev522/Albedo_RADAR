"""Database schema initialization and migrations."""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.migrate import run_migrations
from app.db.models import Base


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_migrations(conn)

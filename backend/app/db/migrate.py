"""Lightweight schema migrations (create_all does not alter existing tables)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

MIGRATIONS: list[str] = [
    """
    ALTER TABLE miner_commitments
    ADD COLUMN IF NOT EXISTS commit_source VARCHAR(16) DEFAULT 'active'
    """,
]


async def run_migrations(conn: AsyncConnection) -> None:
    for sql in MIGRATIONS:
        await conn.execute(text(sql.strip()))

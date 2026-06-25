"""Lightweight schema migrations (create_all does not alter existing tables)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

MIGRATIONS: list[str] = [
    """
    ALTER TABLE miner_commitments
    ADD COLUMN IF NOT EXISTS commit_source VARCHAR(16) DEFAULT 'active'
    """,
    """
    UPDATE miner_commitments
    SET commit_source = 'active'
    WHERE commit_source IS NULL
    """,
    """
    ALTER TABLE hippius_repo_revisions
    ADD COLUMN IF NOT EXISTS files_json JSONB DEFAULT '[]'::jsonb
    """,
]


async def run_migrations(conn: AsyncConnection) -> None:
    for sql in MIGRATIONS:
        await conn.execute(text(sql.strip()))

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
    DO $$ BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'hippius_repo_revisions'
      ) THEN
        ALTER TABLE hippius_repo_revisions
        ADD COLUMN IF NOT EXISTS files_json JSONB DEFAULT '[]'::jsonb;
      END IF;
    END $$
    """,
    """
    DO $$ BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'hippius_repo_tracks'
      ) THEN
        ALTER TABLE hippius_repo_tracks
        DROP CONSTRAINT IF EXISTS uq_hippius_repo_track_subnet_repo;
        BEGIN
          ALTER TABLE hippius_repo_tracks
          ADD CONSTRAINT uq_hippius_repo_track_subnet_hotkey UNIQUE (subnet, hotkey);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END;
        CREATE INDEX IF NOT EXISTS ix_hippius_repo_tracks_repo
          ON hippius_repo_tracks (subnet, repo);
        ALTER TABLE hippius_repo_tracks
        ADD COLUMN IF NOT EXISTS repo_host VARCHAR(16) DEFAULT 'hippius';
      END IF;
    END $$
    """,
]


async def run_migrations(conn: AsyncConnection) -> None:
    for sql in MIGRATIONS:
        await conn.execute(text(sql.strip()))

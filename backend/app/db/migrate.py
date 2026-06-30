"""Lightweight schema migrations (create_all does not alter existing tables)."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

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

        DELETE FROM hippius_repo_tracks WHERE hotkey IS NULL;

        DELETE FROM hippius_repo_tracks t
        USING hippius_repo_tracks t2
        WHERE t.id < t2.id
          AND t.subnet = t2.subnet
          AND t.hotkey = t2.hotkey;

        IF NOT EXISTS (
          SELECT 1 FROM pg_constraint
          WHERE conname = 'uq_hippius_repo_track_subnet_hotkey'
        ) THEN
          BEGIN
            ALTER TABLE hippius_repo_tracks
            ADD CONSTRAINT uq_hippius_repo_track_subnet_hotkey UNIQUE (subnet, hotkey);
          EXCEPTION
            WHEN duplicate_object THEN NULL;
            WHEN unique_violation THEN NULL;
          END;
        END IF;

        CREATE INDEX IF NOT EXISTS ix_hippius_repo_tracks_repo
          ON hippius_repo_tracks (subnet, repo);

        ALTER TABLE hippius_repo_tracks
        ADD COLUMN IF NOT EXISTS repo_host VARCHAR(16) DEFAULT 'hippius';
      END IF;
    END $$
    """,
]


async def run_migrations(conn: AsyncConnection) -> None:
    for idx, sql in enumerate(MIGRATIONS):
        try:
            await conn.execute(text(sql.strip()))
        except Exception:
            logger.exception("migration %d failed (continuing)", idx)

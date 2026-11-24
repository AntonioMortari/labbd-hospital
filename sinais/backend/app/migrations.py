"""Apply ordered SQL migrations once, protected by a database advisory lock."""

import logging
from pathlib import Path

import asyncpg


LOGGER = logging.getLogger(__name__)
MIGRATION_DIR = Path(__file__).resolve().parent.parent / "migrations"
MIGRATION_LOCK_ID = 840_271_993


async def apply_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_ID)
        try:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            for migration_path in sorted(MIGRATION_DIR.glob("*.sql")):
                exists = await connection.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version = $1)",
                    migration_path.name,
                )
                if exists:
                    continue
                sql = migration_path.read_text(encoding="utf-8")
                async with connection.transaction():
                    await connection.execute(sql)
                    await connection.execute(
                        "INSERT INTO schema_migrations(version) VALUES($1)",
                        migration_path.name,
                    )
                LOGGER.info(
                    "database_migration_applied",
                    extra={"event_fields": {"version": migration_path.name}},
                )
        finally:
            await connection.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_ID)


async def ensure_grafana_reader(
    pool: asyncpg.Pool, username: str, password: str
) -> None:
    async with pool.acquire() as connection:
        exists = await connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = $1)",
            username,
        )
        action = "ALTER ROLE" if exists else "CREATE ROLE"
        role_statement = await connection.fetchval(
            "SELECT format('%s %I LOGIN PASSWORD %L', $1::TEXT, $2::TEXT, $3::TEXT)",
            action,
            username,
            password,
        )
        await connection.execute(role_statement)
        statements = (
            "SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), $1::TEXT)",
            "SELECT format('GRANT USAGE ON SCHEMA public TO %I', $1::TEXT)",
            "SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', $1::TEXT)",
            "SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO %I', $1::TEXT)",
        )
        for statement in statements:
            rendered = await connection.fetchval(statement, username)
            await connection.execute(rendered)

"""Acesso ao PostgreSQL: pool de conexões, transação com usuário e tradução de erros."""
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from fastapi import HTTPException

pool: asyncpg.Pool | None = None


async def _codecs(conn: asyncpg.Connection) -> None:
    for tipo in ("json", "jsonb"):
        await conn.set_type_codec(tipo, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def init_pool(dsn: str) -> None:
    global pool
    # 3 réplicas x 2 workers x 10 = 60 conexões, abaixo do max_connections padrão (100)
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10, init=_codecs)


async def close_pool() -> None:
    if pool is not None:
        await pool.close()


@asynccontextmanager
async def tx(usuario: str) -> AsyncIterator[asyncpg.Connection]:
    """Abre uma transação e informa ao banco quem está operando (lido pelo trigger de auditoria)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.usuario', $1, true)", usuario)
            yield conn


# SQLSTATE -> status HTTP
_STATUS = {
    "23P01": 409,  # exclusion_violation: horário sobreposto
    "23505": 409,  # unique_violation: CPF/CRM duplicado
    "23503": 422,  # foreign_key_violation: referência inexistente
    "23514": 422,  # check_violation
    "P0001": 422,  # RAISE EXCEPTION da procedure (plano vencido etc.)
}


def erro_http(e: Exception) -> HTTPException:
    sqlstate = getattr(e, "sqlstate", None) or ""
    if sqlstate in ("23P01", "40P01"):
        # 40P01 (deadlock): o Postgres desfez esta transação porque outra disputava o mesmo
        # intervalo. Para quem chamou, o resultado é o mesmo: o horário não ficou com ele.
        return HTTPException(409, "Horário indisponível para este médico ou paciente")
    status = _STATUS.get(sqlstate)
    if status is None and (sqlstate.startswith("22") or isinstance(e, asyncpg.DataError)):
        status = 422  # dados inválidos (data mal formatada, período invertido...)
    if status is None:
        return HTTPException(500, "Erro interno no banco de dados")
    detalhe = getattr(e, "message", None) or str(e)
    if getattr(e, "detail", None):
        detalhe = f"{detalhe} ({e.detail})"
    return HTTPException(status, detalhe)

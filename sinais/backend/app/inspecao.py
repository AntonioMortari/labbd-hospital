"""Estrutura do TimescaleDB para a aba "Banco por dentro": hypertable, chunks, agregações contínuas e políticas. Somente leitura."""

import json

import asyncpg
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1/db", tags=["banco"])


@router.get("/estrutura")
async def estrutura(request: Request) -> dict[str, object]:
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as c:
        hyper = await c.fetch(
            """SELECT h.hypertable_name AS nome, h.num_chunks AS chunks, h.compression_enabled AS compressao,
                      pg_size_pretty(hypertable_size(format('%I.%I', h.hypertable_schema, h.hypertable_name)::regclass)) AS tamanho,
                      approximate_row_count(format('%I.%I', h.hypertable_schema, h.hypertable_name)::regclass) AS linhas
                 FROM timescaledb_information.hypertables h ORDER BY h.hypertable_name""")
        agregacoes = await c.fetch(
            """SELECT view_name AS nome, hypertable_name AS origem, materialized_only AS so_materializada
                 FROM timescaledb_information.continuous_aggregates ORDER BY view_name""")
        jobs = await c.fetch(
            """SELECT j.proc_name, COALESCE(ca.view_name, j.hypertable_name) AS tabela,
                      j.schedule_interval::text AS intervalo, j.config::text AS config
                 FROM timescaledb_information.jobs j
                 LEFT JOIN timescaledb_information.continuous_aggregates ca
                        ON ca.materialization_hypertable_name = j.hypertable_name
                WHERE j.proc_name IN ('policy_retention', 'policy_refresh_continuous_aggregate')
                ORDER BY 2, j.proc_name""")
        chunks = await c.fetch(
            """SELECT chunk_name AS nome, range_start, range_end FROM timescaledb_information.chunks
                WHERE hypertable_name = 'vital_signs' ORDER BY range_start DESC LIMIT 5""")
        ingestao = await c.fetchrow(
            """SELECT count(*) FILTER (WHERE observed_at > now() - interval '1 minute') AS ultimo_minuto,
                      count(DISTINCT patient_id) FILTER (WHERE observed_at > now() - interval '1 minute') AS pacientes_ativos,
                      min(observed_at) AS mais_antiga, max(observed_at) AS mais_recente
                 FROM vital_signs""")
        versao = await c.fetchval("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
    politicas = []
    for j in jobs:
        cfg = json.loads(j["config"] or "{}")
        if j["proc_name"] == "policy_retention":
            politicas.append({"tipo": "retenção", "tabela": j["tabela"], "detalhe": f"apaga dados com mais de {cfg.get('drop_after')}", "roda_a_cada": j["intervalo"]})
        else:
            politicas.append({"tipo": "atualização", "tabela": j["tabela"],
                              "detalhe": f"atualiza de {cfg.get('start_offset')} atrás até {cfg.get('end_offset')} atrás", "roda_a_cada": j["intervalo"]})
    return {
        "versao_timescaledb": versao,
        "hypertables": [dict(r) for r in hyper],
        "agregacoes": [dict(r) for r in agregacoes],
        "politicas": politicas,
        "chunks": [{"nome": r["nome"], "inicio": r["range_start"].isoformat(), "fim": r["range_end"].isoformat()} for r in chunks],
        "ingestao": {"ultimo_minuto": ingestao["ultimo_minuto"], "pacientes_ativos": ingestao["pacientes_ativos"],
                     "mais_antiga": ingestao["mais_antiga"].isoformat() if ingestao["mais_antiga"] else None,
                     "mais_recente": ingestao["mais_recente"].isoformat() if ingestao["mais_recente"] else None},
    }

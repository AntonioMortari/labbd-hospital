"""FastAPI routes and application lifecycle."""

import asyncio
import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import AsyncIterator

import asyncpg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.alerts import run_alert_worker
from app.analytics import fetch_patient_trends
from app.config import Settings
from app.external_data import seed_demo_data
from app.inspecao import router as inspecao_router
from app.ingestion import (
    ConflictingBatchError,
    InvalidDeviceError,
    write_batch,
)
from app.logging_config import configure_logging, log_event
from app.migrations import apply_migrations, ensure_grafana_reader
from app.schemas import IngestResponse, ReadingBatch


LOGGER = logging.getLogger(__name__)
configure_logging()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    pool = await asyncpg.create_pool(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        command_timeout=30,
    )
    worker: asyncio.Task[None] | None = None
    try:
        await apply_migrations(pool)
        await ensure_grafana_reader(
            pool,
            settings.grafana_db_user,
            settings.grafana_db_password,
        )
        await seed_demo_data(pool, settings)
        application.state.settings = settings
        application.state.pool = pool
        worker = asyncio.create_task(
            run_alert_worker(pool, settings), name="vital-alert-worker"
        )
        application.state.alert_worker = worker
        log_event(LOGGER, logging.INFO, "api_started")
        yield
    finally:
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
        await pool.close()


app = FastAPI(
    title="UTI Vital Signs API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.include_router(inspecao_router)


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    pool: asyncpg.Pool = request.app.state.pool
    worker: asyncio.Task[None] = request.app.state.alert_worker
    await pool.fetchval("SELECT 1")
    if worker.done():
        raise HTTPException(status_code=503, detail="Alert worker is not running")
    return {"status": "ok"}


@app.get("/api/v1/patients")
async def list_patients(request: Request) -> list[dict[str, object]]:
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                patient.patient_id AS id,
                patient.patient_name AS name,
                patient.bed,
                patient.external_source,
                device.device_id,
                device.last_seen_at,
                latest.observed_at,
                latest.hr,
                latest.spo2,
                latest.bp_sys,
                latest.bp_dia,
                CASE
                    WHEN active.severity = 'critical' THEN 'critical'
                    WHEN active.severity = 'warning' THEN 'warning'
                    ELSE 'normal'
                END AS status
            FROM patients AS patient
            JOIN devices AS device
                ON device.patient_id = patient.patient_id AND device.active
            LEFT JOIN LATERAL (
                SELECT observed_at, hr, spo2, bp_sys, bp_dia
                FROM vital_signs
                WHERE patient_id = patient.patient_id
                  AND device_id = device.device_id
                ORDER BY observed_at DESC
                LIMIT 1
            ) AS latest ON TRUE
            LEFT JOIN LATERAL (
                SELECT severity
                FROM alerts
                WHERE patient_id = patient.patient_id AND resolved_at IS NULL
                ORDER BY (severity = 'critical') DESC, first_seen_at DESC
                LIMIT 1
            ) AS active ON TRUE
            ORDER BY patient.bed
            """
        )
    return [dict(row) for row in rows]


@app.get("/api/v1/alerts")
async def list_active_alerts(request: Request) -> list[dict[str, object]]:
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                alert.alert_id,
                alert.patient_id,
                patient.patient_name,
                patient.bed,
                alert.device_id,
                alert.rule_key,
                alert.title,
                alert.description,
                alert.severity,
                alert.measured_value,
                alert.threshold,
                alert.sustained_seconds,
                alert.first_seen_at,
                alert.last_seen_at
            FROM alerts AS alert
            JOIN patients AS patient USING (patient_id)
            WHERE alert.resolved_at IS NULL
            ORDER BY
                (alert.severity = 'critical') DESC,
                alert.first_seen_at DESC
            """
        )
    return [dict(row) for row in rows]


@app.get("/api/v1/analytics/trends/{patient_id}")
async def patient_trends(
    patient_id: str,
    request: Request,
    minutes: int = Query(default=60, ge=5, le=43_200),
) -> list[dict[str, object]]:
    pool: asyncpg.Pool = request.app.state.pool
    exists = await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM patients WHERE patient_id = $1)",
        patient_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Patient not found")
    rows = await fetch_patient_trends(pool, patient_id, minutes)
    return [dict(row) for row in rows]


@app.post(
    "/api/v1/readings",
    status_code=202,
    response_model=IngestResponse,
)
async def ingest_readings(
    batch: ReadingBatch, request: Request
) -> IngestResponse:
    pool: asyncpg.Pool = request.app.state.pool
    started_at = perf_counter()
    try:
        accepted, duplicates = await write_batch(pool, batch.readings)
    except InvalidDeviceError as error:
        log_event(
            LOGGER,
            logging.WARNING,
            "reading_batch_rejected",
            reason="unknown_or_inactive_device",
            error=str(error),
            received=len(batch.readings),
        )
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ConflictingBatchError as error:
        log_event(
            LOGGER,
            logging.WARNING,
            "reading_batch_rejected",
            reason="conflicting_idempotency_key",
            received=len(batch.readings),
        )
        raise HTTPException(status_code=409, detail=str(error)) from error

    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    log_event(
        LOGGER,
        logging.INFO,
        "reading_batch_ingested",
        received=len(batch.readings),
        accepted=accepted,
        duplicates=duplicates,
        duration_ms=duration_ms,
    )
    return IngestResponse(
        accepted=accepted,
        duplicates=duplicates,
        received=len(batch.readings),
    )


@app.exception_handler(asyncpg.PostgresError)
async def database_error_handler(
    _request: Request, error: asyncpg.PostgresError
) -> JSONResponse:
    log_event(
        LOGGER,
        logging.ERROR,
        "database_request_failed",
        error_type=type(error).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database operation failed"},
    )

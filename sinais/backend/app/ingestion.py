"""Idempotent batch writing to the TimescaleDB hypertable."""

from collections.abc import Sequence

import asyncpg

from app.schemas import VitalReading


class InvalidDeviceError(ValueError):
    """Raised when a reading references a device not assigned to its patient."""


class ConflictingBatchError(ValueError):
    """Raised when one batch contains different readings for the same key."""


async def write_batch(
    pool: asyncpg.Pool, readings: Sequence[VitalReading]
) -> tuple[int, int]:
    unique_readings: dict[tuple[object, str, str], VitalReading] = {}
    for reading in readings:
        key = (reading.observed_at, reading.patient_id, reading.device_id)
        previous = unique_readings.get(key)
        if previous is not None and previous != reading:
            raise ConflictingBatchError(
                "A batch contains conflicting values for the same reading key"
            )
        unique_readings[key] = reading

    records = [
        (
            reading.observed_at,
            reading.patient_id,
            reading.device_id,
            reading.hr,
            reading.spo2,
            reading.bp_sys,
            reading.bp_dia,
        )
        for reading in unique_readings.values()
    ]

    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                CREATE TEMP TABLE ingest_stage (
                    observed_at TIMESTAMPTZ NOT NULL,
                    patient_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    hr SMALLINT NOT NULL,
                    spo2 SMALLINT NOT NULL,
                    bp_sys SMALLINT NOT NULL,
                    bp_dia SMALLINT NOT NULL
                ) ON COMMIT DROP
                """
            )
            await connection.copy_records_to_table(
                "ingest_stage",
                records=records,
                columns=(
                    "observed_at",
                    "patient_id",
                    "device_id",
                    "hr",
                    "spo2",
                    "bp_sys",
                    "bp_dia",
                ),
            )

            invalid_device = await connection.fetchrow(
                """
                SELECT stage.patient_id, stage.device_id
                FROM ingest_stage AS stage
                LEFT JOIN devices AS device
                    ON device.device_id = stage.device_id
                    AND device.patient_id = stage.patient_id
                    AND device.active
                WHERE device.device_id IS NULL
                LIMIT 1
                """
            )
            if invalid_device is not None:
                raise InvalidDeviceError(
                    f"Device {invalid_device['device_id']} is not active for "
                    f"patient {invalid_device['patient_id']}"
                )

            inserted = await connection.fetchval(
                """
                WITH inserted AS (
                    INSERT INTO vital_signs(
                        observed_at, patient_id, device_id, hr, spo2, bp_sys, bp_dia
                    )
                    SELECT
                        observed_at, patient_id, device_id, hr, spo2, bp_sys, bp_dia
                    FROM ingest_stage
                    ON CONFLICT (observed_at, patient_id, device_id) DO NOTHING
                    RETURNING 1
                )
                SELECT COUNT(*) FROM inserted
                """
            )
            await connection.fetch(
                """
                SELECT device.device_id
                FROM devices AS device
                JOIN (
                    SELECT device_id, MAX(observed_at) AS last_seen_at
                    FROM ingest_stage
                    GROUP BY device_id
                ) AS staged
                    ON staged.device_id = device.device_id
                WHERE device.last_seen_at IS NULL
                   OR device.last_seen_at < staged.last_seen_at
                ORDER BY device.device_id
                FOR NO KEY UPDATE OF device
                """
            )
            await connection.execute(
                """
                UPDATE devices AS device
                SET last_seen_at = staged.last_seen_at
                FROM (
                    SELECT device_id, MAX(observed_at) AS last_seen_at
                    FROM ingest_stage
                    GROUP BY device_id
                ) AS staged
                WHERE device.device_id = staged.device_id
                  AND (
                      device.last_seen_at IS NULL
                      OR device.last_seen_at < staged.last_seen_at
                  )
                """
            )

    accepted = int(inserted)
    return accepted, len(readings) - accepted

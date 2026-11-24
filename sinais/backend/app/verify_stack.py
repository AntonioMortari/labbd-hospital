"""Verify the database schema and key HTTP flows against a running stack."""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import httpx

from app.config import Settings


async def verify_database(settings: Settings) -> None:
    pool = await asyncpg.create_pool(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM patients) AS patients,
                    (SELECT COUNT(*) FROM devices) AS devices,
                    EXISTS(
                        SELECT 1
                        FROM timescaledb_information.hypertables
                        WHERE hypertable_name = 'vital_signs'
                    ) AS has_hypertable,
                    (SELECT COUNT(*)
                     FROM timescaledb_information.continuous_aggregates
                     WHERE view_name IN ('vital_signs_1m', 'vital_signs_1h')
                    ) AS aggregates,
                    (SELECT COUNT(*)
                     FROM timescaledb_information.jobs
                     WHERE proc_name = 'policy_retention'
                    ) AS retention_jobs
                """
            )
        if (
            row["patients"] < 20
            or row["devices"] < 20
            or not row["has_hypertable"]
            or row["aggregates"] != 2
            or row["retention_jobs"] != 3
        ):
            raise RuntimeError(f"Database verification failed: {dict(row)}")
    finally:
        await pool.close()


async def verify_api() -> None:
    async with httpx.AsyncClient(
        base_url="http://localhost:8000", timeout=10.0
    ) as client:
        patients_response = await client.get("/api/v1/patients")
        patients_response.raise_for_status()
        patients: list[dict[str, Any]] = patients_response.json()
        if len(patients) < 20:
            raise RuntimeError("API did not return the expected demo patients")

        patient = patients[0]
        reading = {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "patient_id": patient["id"],
            "device_id": patient["device_id"],
            "hr": 80,
            "spo2": 98,
            "bp_sys": 120,
            "bp_dia": 80,
        }
        first = await client.post("/api/v1/readings", json={"readings": [reading]})
        first.raise_for_status()
        second = await client.post("/api/v1/readings", json={"readings": [reading]})
        second.raise_for_status()
        if first.json()["accepted"] != 1:
            raise RuntimeError("First reading was not inserted")
        if second.json()["accepted"] != 0 or second.json()["duplicates"] != 1:
            raise RuntimeError("Repeated reading was not idempotent")

        alerts_response = await client.get("/api/v1/alerts")
        alerts_response.raise_for_status()
        if not isinstance(alerts_response.json(), list):
            raise RuntimeError("Alert API did not return a list")

        trends_response = await client.get(
            f"/api/v1/analytics/trends/{patient['id']}",
            params={"minutes": 60},
        )
        trends_response.raise_for_status()
        if not isinstance(trends_response.json(), list):
            raise RuntimeError("Trend API did not return a list")


async def verify_sustained_alert(settings: Settings) -> bool:
    if settings.alert_webhook_url is not None:
        return False

    pool = await asyncpg.create_pool(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )
    patient_id = "patient_verify_alert"
    device_id = "monitor_verify_alert"
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "DELETE FROM vital_signs WHERE patient_id = $1", patient_id
                )
                await connection.execute(
                    "DELETE FROM alerts WHERE patient_id = $1", patient_id
                )
                await connection.execute(
                    "DELETE FROM devices WHERE device_id = $1", device_id
                )
                await connection.execute(
                    "DELETE FROM patients WHERE patient_id = $1", patient_id
                )
                await connection.execute(
                    """
                    INSERT INTO patients(
                        patient_id, patient_name, bed, external_source
                    )
                    VALUES($1, 'Paciente de teste', 'VERIFY-01', 'verification')
                    """,
                    patient_id,
                )
                await connection.execute(
                    """
                    INSERT INTO devices(device_id, patient_id, label)
                    VALUES($1, $2, 'Verification monitor')
                    """,
                    device_id,
                    patient_id,
                )

        span_seconds = (
            settings.spo2_alert_seconds + settings.alert_poll_seconds + 10
        )
        start = datetime.now(timezone.utc) - timedelta(seconds=span_seconds)
        readings = [
            {
                "observed_at": (start + timedelta(seconds=second)).isoformat(),
                "patient_id": patient_id,
                "device_id": device_id,
                "hr": 80,
                "spo2": 85,
                "bp_sys": 120,
                "bp_dia": 80,
            }
            for second in range(span_seconds + 1)
        ]
        async with httpx.AsyncClient(
            base_url="http://localhost:8000", timeout=10.0
        ) as client:
            response = await client.post(
                "/api/v1/readings", json={"readings": readings}
            )
            response.raise_for_status()
            if response.json()["accepted"] != len(readings):
                raise RuntimeError("Sustained-alert test readings were not inserted")

            deadline = time.monotonic() + settings.alert_poll_seconds + 10
            while time.monotonic() < deadline:
                active_alerts = await client.get("/api/v1/alerts")
                active_alerts.raise_for_status()
                if any(
                    alert["patient_id"] == patient_id
                    and alert["rule_key"] == "spo2_low_sustained"
                    for alert in active_alerts.json()
                ):
                    return True
                await asyncio.sleep(1)
            raise RuntimeError("Sustained SpO₂ alert was not generated")
    finally:
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "DELETE FROM vital_signs WHERE patient_id = $1", patient_id
                )
                await connection.execute(
                    "DELETE FROM alerts WHERE patient_id = $1", patient_id
                )
                await connection.execute(
                    "DELETE FROM devices WHERE device_id = $1", device_id
                )
                await connection.execute(
                    "DELETE FROM patients WHERE patient_id = $1", patient_id
                )
        await pool.close()


async def main() -> None:
    settings = Settings.from_env()
    await verify_database(settings)
    await verify_api()
    alert_tested = await verify_sustained_alert(settings)
    print(
        "database_schema=ok ingestion_idempotency=ok analytics_api=ok "
        f"sustained_alert={'ok' if alert_tested else 'skipped_webhook_configured'}"
    )


if __name__ == "__main__":
    asyncio.run(main())

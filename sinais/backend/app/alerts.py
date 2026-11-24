"""Periodic, duration-based evaluation and optional webhook delivery."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

import asyncpg
import httpx

from app.config import Settings
from app.logging_config import log_event


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AlertRule:
    key: str
    title: str
    severity: Literal["warning", "critical"]
    metric: str
    summary_column: str
    operator: Literal["lt", "gt"]
    threshold: float
    duration_seconds: int
    description_format: str


def build_rules(settings: Settings) -> tuple[AlertRule, ...]:
    return (
        AlertRule(
            key="spo2_low_sustained",
            title="SpO₂ baixa sustentada",
            severity="critical",
            metric="SpO₂",
            summary_column="max_spo2",
            operator="lt",
            threshold=90,
            duration_seconds=settings.spo2_alert_seconds,
            description_format="SpO₂ permaneceu abaixo de 90%; pior leitura: {value:.0f}%.",
        ),
        AlertRule(
            key="tachycardia_sustained",
            title="Taquicardia sustentada",
            severity="critical",
            metric="FC",
            summary_column="min_hr",
            operator="gt",
            threshold=120,
            duration_seconds=settings.heart_rate_alert_seconds,
            description_format="FC permaneceu acima de 120 bpm; maior leitura: {value:.0f} bpm.",
        ),
        AlertRule(
            key="hypotension_sustained",
            title="Hipotensão sustentada",
            severity="critical",
            metric="Pressão sistólica",
            summary_column="max_bp_sys",
            operator="lt",
            threshold=90,
            duration_seconds=settings.hypotension_alert_seconds,
            description_format="Pressão sistólica permaneceu abaixo de 90 mmHg; maior leitura: {value:.0f} mmHg.",
        ),
    )


SUMMARY_QUERY = """
SELECT
    patient_id,
    device_id,
    COUNT(*)::INTEGER AS sample_count,
    MIN(observed_at) AS first_seen_at,
    MAX(observed_at) AS last_seen_at,
    MIN(hr)::DOUBLE PRECISION AS min_hr,
    MAX(hr)::DOUBLE PRECISION AS max_hr,
    MIN(spo2)::DOUBLE PRECISION AS min_spo2,
    MAX(spo2)::DOUBLE PRECISION AS max_spo2,
    MIN(bp_sys)::DOUBLE PRECISION AS min_bp_sys,
    MAX(bp_sys)::DOUBLE PRECISION AS max_bp_sys
FROM vital_signs
WHERE observed_at >= now() - make_interval(secs => $3::DOUBLE PRECISION)
GROUP BY patient_id, device_id
HAVING COUNT(*) >= $2
   AND MAX(observed_at) - MIN(observed_at)
       >= make_interval(secs => $1::DOUBLE PRECISION)
"""


def _is_breached(rule: AlertRule, value: float) -> bool:
    if rule.operator == "lt":
        return value < rule.threshold
    return value > rule.threshold


async def _deliver_webhook(
    settings: Settings, alert: dict[str, object]
) -> None:
    if settings.alert_webhook_url is None:
        return
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(
                settings.alert_webhook_url,
                json={"event": "vital_alert", "alert": alert},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            log_event(
                LOGGER,
                logging.ERROR,
                "alert_webhook_delivery_failed",
                alert_id=alert["alert_id"],
                error_type=type(error).__name__,
            )
            return
    log_event(
        LOGGER,
        logging.INFO,
        "alert_webhook_delivered",
        alert_id=alert["alert_id"],
    )


async def evaluate_alerts(pool: asyncpg.Pool, settings: Settings) -> None:
    rules = build_rules(settings)
    notifications: list[dict[str, object]] = []
    async with pool.acquire() as connection:
        for rule in rules:
            minimum_samples = max(3, rule.duration_seconds // 2)
            summaries = await connection.fetch(
                SUMMARY_QUERY,
                rule.duration_seconds,
                minimum_samples,
                rule.duration_seconds + settings.alert_poll_seconds + 2,
            )
            qualifying = {
                (summary["patient_id"], summary["device_id"]): summary
                for summary in summaries
                if _is_breached(rule, float(summary[rule.summary_column]))
            }
            async with connection.transaction():
                active_rows = await connection.fetch(
                    """
                    SELECT alert_id, patient_id, device_id
                    FROM alerts
                    WHERE rule_key = $1 AND resolved_at IS NULL
                    """,
                    rule.key,
                )
                active_keys = {
                    (row["patient_id"], row["device_id"]): row["alert_id"]
                    for row in active_rows
                }

                for key, alert_id in active_keys.items():
                    if key not in qualifying:
                        await connection.execute(
                            """
                            UPDATE alerts SET resolved_at = now()
                            WHERE alert_id = $1 AND resolved_at IS NULL
                            """,
                            alert_id,
                        )
                        log_event(
                            LOGGER,
                            logging.INFO,
                            "vital_alert_resolved",
                            alert_id=alert_id,
                            rule_key=rule.key,
                            patient_id=key[0],
                        )

                for key, summary in qualifying.items():
                    measured_value = float(summary[rule.summary_column])
                    description = rule.description_format.format(
                        value=measured_value
                    )
                    alert_id = active_keys.get(key)
                    if alert_id is not None:
                        await connection.execute(
                            """
                            UPDATE alerts
                            SET last_seen_at = $1,
                                measured_value = $2,
                                description = $3
                            WHERE alert_id = $4 AND resolved_at IS NULL
                            """,
                            summary["last_seen_at"],
                            measured_value,
                            description,
                            alert_id,
                        )
                        continue

                    inserted = await connection.fetchrow(
                        """
                        INSERT INTO alerts(
                            patient_id, device_id, rule_key, title, description,
                            severity, measured_value, threshold, sustained_seconds,
                            first_seen_at, last_seen_at
                        )
                        VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        ON CONFLICT (patient_id, device_id, rule_key)
                            WHERE resolved_at IS NULL
                        DO NOTHING
                        RETURNING alert_id
                        """,
                        key[0],
                        key[1],
                        rule.key,
                        rule.title,
                        description,
                        rule.severity,
                        measured_value,
                        rule.threshold,
                        rule.duration_seconds,
                        summary["first_seen_at"],
                        summary["last_seen_at"],
                    )
                    if inserted is None:
                        continue

                    notification: dict[str, object] = {
                        "alert_id": inserted["alert_id"],
                        "patient_id": key[0],
                        "device_id": key[1],
                        "rule_key": rule.key,
                        "title": rule.title,
                        "description": description,
                        "severity": rule.severity,
                        "measured_value": measured_value,
                        "threshold": rule.threshold,
                        "sustained_seconds": rule.duration_seconds,
                        "first_seen_at": summary["first_seen_at"],
                        "last_seen_at": summary["last_seen_at"],
                    }
                    notifications.append(notification)
                    log_event(
                        LOGGER,
                        logging.WARNING,
                        "vital_alert_created",
                        alert_id=inserted["alert_id"],
                        rule_key=rule.key,
                        patient_id=key[0],
                        device_id=key[1],
                        severity=rule.severity,
                    )

    for notification in notifications:
        await _deliver_webhook(settings, notification)


async def run_alert_worker(pool: asyncpg.Pool, settings: Settings) -> None:
    while True:
        try:
            await evaluate_alerts(pool, settings)
        except asyncpg.PostgresError as error:
            log_event(
                LOGGER,
                logging.ERROR,
                "alert_evaluation_failed",
                error_type=type(error).__name__,
            )
        await asyncio.sleep(settings.alert_poll_seconds)

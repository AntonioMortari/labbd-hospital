"""Windowed trends over the minute continuous aggregate."""

import asyncpg


TREND_QUERY = """
WITH minute AS (
    SELECT
        bucket,
        patient_id,
        device_id,
        hr_avg,
        spo2_avg,
        bp_sys_avg,
        bp_dia_avg
    FROM vital_signs_1m
    WHERE patient_id = $1
      AND bucket >= now() - ($2::DOUBLE PRECISION * INTERVAL '1 minute')
),
windowed AS (
    SELECT
        *,
        AVG(spo2_avg) OVER (
            PARTITION BY patient_id, device_id
            ORDER BY bucket
            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
        ) AS spo2_moving_avg_5m,
        spo2_avg - LAG(spo2_avg) OVER (
            PARTITION BY patient_id, device_id ORDER BY bucket
        ) AS spo2_delta_1m,
        AVG(spo2_avg) OVER (
            PARTITION BY patient_id, device_id
            ORDER BY bucket
            ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
        ) AS spo2_mean_1h,
        STDDEV_POP(spo2_avg) OVER (
            PARTITION BY patient_id, device_id
            ORDER BY bucket
            ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
        ) AS spo2_stddev_1h,
        REGR_SLOPE(
            spo2_avg,
            EXTRACT(EPOCH FROM bucket)::DOUBLE PRECISION
        ) OVER (
            PARTITION BY patient_id, device_id
            ORDER BY bucket
            ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
        ) AS spo2_slope_per_second
    FROM minute
)
SELECT
    *,
    CASE
        WHEN spo2_stddev_1h > 0
        THEN (spo2_avg - spo2_mean_1h) / spo2_stddev_1h
        ELSE NULL
    END AS spo2_zscore_1h
FROM windowed
ORDER BY bucket
"""


async def fetch_patient_trends(
    pool: asyncpg.Pool, patient_id: str, minutes: int
) -> list[asyncpg.Record]:
    async with pool.acquire() as connection:
        return await connection.fetch(TREND_QUERY, patient_id, minutes)

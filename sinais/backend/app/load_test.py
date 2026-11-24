"""Generate configurable multi-patient batches and report write/query latency."""

import argparse
import asyncio
import os
import statistics
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


def build_batches(
    patients: list[dict[str, Any]], point_count: int, batch_size: int
) -> Iterator[list[dict[str, object]]]:
    start = datetime.now(timezone.utc) - timedelta(
        seconds=(point_count // len(patients)) + 60
    )
    batch: list[dict[str, object]] = []
    for index in range(point_count):
        patient = patients[index % len(patients)]
        observed_at = start + timedelta(seconds=index // len(patients))
        batch.append(
            {
                "observed_at": observed_at.isoformat(),
                "patient_id": patient["id"],
                "device_id": patient["device_id"],
                "hr": 70 + (index % 45),
                "spo2": 95 + (index % 5),
                "bp_sys": 110 + (index % 30),
                "bp_dia": 65 + (index % 20),
            }
        )
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


async def send_batch(
    client: httpx.AsyncClient, api_url: str, readings: list[dict[str, object]]
) -> tuple[int, float]:
    started_at = time.perf_counter()
    response = await client.post(
        f"{api_url}/api/v1/readings",
        json={"readings": readings},
    )
    response.raise_for_status()
    result = response.json()
    return int(result["accepted"]), (time.perf_counter() - started_at) * 1000


async def run_load_test(
    api_url: str, point_count: int, batch_size: int, workers: int
) -> None:
    if point_count <= 0 or batch_size <= 0 or workers <= 0:
        raise ValueError("points, batch size, and workers must be positive")
    if batch_size > 5000:
        raise ValueError("batch size cannot exceed the API limit of 5000 readings")

    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{api_url}/api/v1/patients")
        response.raise_for_status()
        patients = response.json()
        if not patients:
            raise RuntimeError("The API has no patients to use for the load test")

        started_at = time.perf_counter()
        pending: set[asyncio.Task[tuple[int, float]]] = set()
        all_tasks: set[asyncio.Task[tuple[int, float]]] = set()
        accepted = 0
        latencies_ms: list[float] = []
        try:
            for batch in build_batches(patients, point_count, batch_size):
                task = asyncio.create_task(send_batch(client, api_url, batch))
                pending.add(task)
                all_tasks.add(task)
                if len(pending) >= workers * 2:
                    completed, pending = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in completed:
                        batch_accepted, latency = task.result()
                        accepted += batch_accepted
                        latencies_ms.append(latency)

            for task in asyncio.as_completed(pending):
                batch_accepted, latency = await task
                accepted += batch_accepted
                latencies_ms.append(latency)
        finally:
            for task in pending:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*all_tasks, return_exceptions=True)

        write_seconds = time.perf_counter() - started_at
        query_started_at = time.perf_counter()
        trends = await client.get(
            f"{api_url}/api/v1/analytics/trends/{patients[0]['id']}",
            params={"minutes": 60},
        )
        trends.raise_for_status()
        query_latency_ms = (time.perf_counter() - query_started_at) * 1000

    median_latency = statistics.median(latencies_ms) if latencies_ms else 0
    print(
        f"patients={len(patients)} accepted={accepted}/{point_count} "
        f"write_points_per_second={accepted / write_seconds:.1f} "
        f"batch_median_latency_ms={median_latency:.1f} "
        f"trend_query_latency_ms={query_latency_ms:.1f} "
        f"trend_rows={len(trends.json())}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-url",
        default=os.getenv("API_URL", "http://localhost:8000"),
    )
    parser.add_argument("--points", type=int, default=1_000_000)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    asyncio.run(
        run_load_test(args.api_url, args.points, args.batch_size, args.workers)
    )


if __name__ == "__main__":
    main()

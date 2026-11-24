"""Stream simulated monitor readings to the batch ingestion API."""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings
from app.logging_config import configure_logging, log_event
from app.patients import PATIENTS


LOGGER = logging.getLogger(__name__)
ALERT_TYPES = (
    "tachycardia",
    "bradycardia",
    "hypertension",
    "hypotension",
    "hypoxemia",
)


@dataclass(slots=True)
class PatientEpisode:
    alerting: bool
    transition_at: float
    alert_type: str = "normal"


def initialize_patient_episodes(now: float) -> dict[str, PatientEpisode]:
    return {
        patient["id"]: PatientEpisode(
            alerting=False,
            transition_at=now + random.uniform(0, 300),
        )
        for patient in PATIENTS
    }


def generate_for_patient(
    patient: dict[str, Any], episode: PatientEpisode, now: float
) -> tuple[int, int, int, int]:
    if now >= episode.transition_at:
        episode.alerting = not episode.alerting
        if episode.alerting:
            episode.alert_type = random.choice(ALERT_TYPES)
            episode.transition_at = now + random.uniform(90, 150)
        else:
            episode.alert_type = "normal"
            episode.transition_at = now + random.uniform(120, 300)

    baseline = patient["baseline"]
    hr = random.randint(*baseline["hr"])
    spo2 = random.randint(*baseline["spo2"])
    bp_sys = random.randint(*baseline["sbp"])
    bp_dia = random.randint(*baseline["dbp"])

    if episode.alerting:
        if episode.alert_type == "tachycardia":
            hr = random.randint(121, 140)
        elif episode.alert_type == "bradycardia":
            hr = random.randint(35, 49)
        elif episode.alert_type == "hypertension":
            bp_sys = random.randint(161, 180)
            bp_dia = random.randint(102, 115)
        elif episode.alert_type == "hypotension":
            bp_sys = random.randint(80, 89)
            bp_dia = random.randint(50, 59)
        elif episode.alert_type == "hypoxemia":
            spo2 = random.randint(84, 89)

    return hr, spo2, bp_sys, bp_dia


async def wait_for_api(client: httpx.AsyncClient, api_url: str) -> None:
    while True:
        try:
            response = await client.get(f"{api_url}/health")
            response.raise_for_status()
            return
        except httpx.HTTPError as error:
            log_event(
                LOGGER,
                logging.WARNING,
                "api_not_ready_retrying",
                error_type=type(error).__name__,
            )
            await asyncio.sleep(2)


async def run_simulator() -> None:
    configure_logging()
    settings = Settings.from_env()
    episodes = initialize_patient_episodes(time.monotonic())
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        await wait_for_api(client, settings.api_url)
        while True:
            cycle_started = time.monotonic()
            observed_at = datetime.now(timezone.utc).isoformat()
            readings: list[dict[str, object]] = []
            active_episodes = 0
            for patient in PATIENTS:
                episode = episodes[patient["id"]]
                values = generate_for_patient(patient, episode, cycle_started)
                active_episodes += int(episode.alerting)
                readings.append(
                    {
                        "observed_at": observed_at,
                        "patient_id": patient["id"],
                        "device_id": f"monitor_{patient['id']}",
                        "hr": values[0],
                        "spo2": values[1],
                        "bp_sys": values[2],
                        "bp_dia": values[3],
                    }
                )

            try:
                response = await client.post(
                    f"{settings.api_url}/api/v1/readings",
                    json={"readings": readings},
                )
                response.raise_for_status()
                log_event(
                    LOGGER,
                    logging.INFO,
                    "simulated_batch_sent",
                    readings=len(readings),
                    active_episodes=active_episodes,
                )
            except httpx.HTTPError as error:
                log_event(
                    LOGGER,
                    logging.ERROR,
                    "simulated_batch_failed",
                    readings=len(readings),
                    error_type=type(error).__name__,
                )

            elapsed = time.monotonic() - cycle_started
            await asyncio.sleep(
                max(0.0, settings.simulator_interval_seconds - elapsed)
            )


if __name__ == "__main__":
    asyncio.run(run_simulator())

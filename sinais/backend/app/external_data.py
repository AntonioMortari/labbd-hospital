"""Import synthetic demo names from the public RandomUser API."""

import logging

import asyncpg
import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.logging_config import log_event
from app.patients import PATIENTS


LOGGER = logging.getLogger(__name__)


class RandomUserName(BaseModel):
    first: str
    last: str


class RandomUserRecord(BaseModel):
    name: RandomUserName


class RandomUserResponse(BaseModel):
    results: list[RandomUserRecord]


async def fetch_randomuser_names(settings: Settings) -> list[str]:
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(
            settings.randomuser_api_url,
            params={
                "results": len(PATIENTS),
                "nat": "br",
                "inc": "name",
                "seed": "icu-demo",
            },
        )
        response.raise_for_status()
        payload = RandomUserResponse.model_validate(response.json())
    if len(payload.results) < len(PATIENTS):
        raise ValueError("RandomUser returned fewer profiles than requested")
    return [f"{person.name.first} {person.name.last}" for person in payload.results]


async def seed_demo_data(pool: asyncpg.Pool, settings: Settings) -> None:
    names: list[str] | None = None
    if settings.randomuser_enabled:
        try:
            names = await fetch_randomuser_names(settings)
        except (httpx.HTTPError, ValueError, ValidationError) as error:
            log_event(
                LOGGER,
                logging.WARNING,
                "synthetic_profile_import_failed_using_local_demo_names",
                error_type=type(error).__name__,
            )

    async with pool.acquire() as connection:
        async with connection.transaction():
            for index, patient in enumerate(PATIENTS):
                patient_id = patient["id"]
                patient_name = names[index] if names is not None else patient["name"]
                source = "randomuser.me" if names is not None else "local-demo"
                device_id = f"monitor_{patient_id}"
                await connection.execute(
                    """
                    INSERT INTO patients(patient_id, patient_name, bed, external_source)
                    VALUES($1, $2, $3, $4)
                    ON CONFLICT(patient_id) DO UPDATE SET
                        patient_name = EXCLUDED.patient_name,
                        bed = EXCLUDED.bed,
                        external_source = EXCLUDED.external_source
                    """,
                    patient_id,
                    patient_name,
                    patient["bed"],
                    source,
                )
                await connection.execute(
                    """
                    INSERT INTO devices(device_id, patient_id, label, active)
                    VALUES($1, $2, $3, TRUE)
                    ON CONFLICT(device_id) DO UPDATE SET
                        patient_id = EXCLUDED.patient_id,
                        label = EXCLUDED.label,
                        active = TRUE
                    """,
                    device_id,
                    patient_id,
                    f"Monitor {patient['bed']}",
                )

    log_event(
        LOGGER,
        logging.INFO,
        "demo_patients_seeded",
        patient_count=len(PATIENTS),
        profile_source="randomuser.me" if names is not None else "local-demo",
    )

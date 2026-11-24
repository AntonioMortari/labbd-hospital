from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import ReadingBatch, VitalReading


def valid_reading() -> dict[str, object]:
    return {
        "observed_at": datetime.now(timezone.utc),
        "patient_id": "patient_001",
        "device_id": "monitor_patient_001",
        "hr": 80,
        "spo2": 98,
        "bp_sys": 120,
        "bp_dia": 80,
    }


def test_reading_requires_timezone() -> None:
    reading = valid_reading()
    reading["observed_at"] = datetime(2026, 1, 1)

    with pytest.raises(ValidationError, match="timezone"):
        VitalReading.model_validate(reading)


def test_reading_rejects_impossible_pressure_pair() -> None:
    reading = valid_reading()
    reading["bp_sys"] = 80
    reading["bp_dia"] = 90

    with pytest.raises(ValidationError, match="greater than"):
        VitalReading.model_validate(reading)


def test_batch_rejects_out_of_range_spo2() -> None:
    reading = valid_reading()
    reading["spo2"] = 120

    with pytest.raises(ValidationError):
        ReadingBatch.model_validate({"readings": [reading]})

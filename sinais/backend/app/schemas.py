"""Validated API payloads and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VitalReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    patient_id: str = Field(min_length=1, max_length=64)
    device_id: str = Field(min_length=1, max_length=64)
    hr: int = Field(ge=20, le=250)
    spo2: int = Field(ge=50, le=100)
    bp_sys: int = Field(ge=30, le=300)
    bp_dia: int = Field(ge=20, le=200)

    @model_validator(mode="after")
    def validate_measurement(self) -> "VitalReading":
        if self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if self.bp_sys <= self.bp_dia:
            raise ValueError("bp_sys must be greater than bp_dia")
        return self


class ReadingBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    readings: list[VitalReading] = Field(min_length=1, max_length=5000)


class IngestResponse(BaseModel):
    accepted: int
    duplicates: int
    received: int

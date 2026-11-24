CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    patient_name TEXT NOT NULL,
    bed TEXT NOT NULL UNIQUE,
    external_source TEXT NOT NULL DEFAULT 'local-demo',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (device_id, patient_id)
);

CREATE TABLE IF NOT EXISTS vital_signs (
    observed_at TIMESTAMPTZ NOT NULL,
    patient_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    hr SMALLINT NOT NULL CHECK (hr BETWEEN 20 AND 250),
    spo2 SMALLINT NOT NULL CHECK (spo2 BETWEEN 50 AND 100),
    bp_sys SMALLINT NOT NULL CHECK (bp_sys BETWEEN 30 AND 300),
    bp_dia SMALLINT NOT NULL CHECK (bp_dia BETWEEN 20 AND 200),
    CHECK (bp_sys > bp_dia),
    PRIMARY KEY (observed_at, patient_id, device_id),
    FOREIGN KEY (device_id, patient_id)
        REFERENCES devices(device_id, patient_id)
);

SELECT create_hypertable(
    'vital_signs',
    'observed_at',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS ix_vital_signs_patient_time
    ON vital_signs (patient_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS ix_vital_signs_device_time
    ON vital_signs (device_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id BIGSERIAL PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical')),
    measured_value DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    sustained_seconds INTEGER NOT NULL CHECK (sustained_seconds > 0),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    FOREIGN KEY (device_id, patient_id)
        REFERENCES devices(device_id, patient_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_alerts_active_rule_patient
    ON alerts (patient_id, device_id, rule_key)
    WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_alerts_active_time
    ON alerts (resolved_at, first_seen_at DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS vital_signs_1m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket(INTERVAL '1 minute', observed_at) AS bucket,
    patient_id,
    device_id,
    AVG(hr)::DOUBLE PRECISION AS hr_avg,
    AVG(spo2)::DOUBLE PRECISION AS spo2_avg,
    AVG(bp_sys)::DOUBLE PRECISION AS bp_sys_avg,
    AVG(bp_dia)::DOUBLE PRECISION AS bp_dia_avg,
    COUNT(*)::INTEGER AS sample_count
FROM vital_signs
GROUP BY bucket, patient_id, device_id
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS vital_signs_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket(INTERVAL '1 hour', observed_at) AS bucket,
    patient_id,
    device_id,
    AVG(hr)::DOUBLE PRECISION AS hr_avg,
    AVG(spo2)::DOUBLE PRECISION AS spo2_avg,
    AVG(bp_sys)::DOUBLE PRECISION AS bp_sys_avg,
    AVG(bp_dia)::DOUBLE PRECISION AS bp_dia_avg,
    COUNT(*)::INTEGER AS sample_count
FROM vital_signs
GROUP BY bucket, patient_id, device_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'vital_signs_1m',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);
SELECT add_continuous_aggregate_policy(
    'vital_signs_1h',
    start_offset => INTERVAL '30 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);
SELECT add_retention_policy(
    'vital_signs',
    INTERVAL '30 days',
    if_not_exists => TRUE
);
SELECT add_retention_policy(
    'vital_signs_1m',
    INTERVAL '365 days',
    if_not_exists => TRUE
);
SELECT add_retention_policy(
    'vital_signs_1h',
    INTERVAL '5 years',
    if_not_exists => TRUE
);

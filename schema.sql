-- FloatChat PostgreSQL Schema
-- Run: psql -U postgres -d floatchat -f schema.sql

-- Enable PostGIS extension for geospatial support
CREATE EXTENSION IF NOT EXISTS postgis;

-- ══════════════════════════════════
-- Table 1: floats
-- Stores metadata about each ARGO float
-- ══════════════════════════════════
CREATE TABLE IF NOT EXISTS floats (
    wmo_id          INTEGER PRIMARY KEY,
    dac             VARCHAR(20),        -- Data Assembly Centre (e.g. CSIO, CORIOLIS)
    platform_type   VARCHAR(50),        -- Float model
    deploy_date     DATE,
    deploy_lat      NUMERIC(8,4),
    deploy_lon      NUMERIC(8,4),
    deploy_location GEOGRAPHY(POINT),   -- PostGIS point
    status          VARCHAR(20),        -- active / inactive
    pi_name         VARCHAR(100),       -- Principal Investigator
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ══════════════════════════════════
-- Table 2: profiles
-- Each float cycle = one profile
-- ══════════════════════════════════
CREATE TABLE IF NOT EXISTS profiles (
    profile_id      SERIAL PRIMARY KEY,
    wmo_id          INTEGER REFERENCES floats(wmo_id),
    cycle_number    INTEGER,
    profile_date    TIMESTAMP,          -- UTC
    latitude        NUMERIC(8,4),
    longitude       NUMERIC(8,4),
    location        GEOGRAPHY(POINT),   -- PostGIS point
    max_depth       NUMERIC(8,2),       -- dbar
    data_mode       CHAR(1),            -- R=realtime D=delayed A=adjusted
    source          VARCHAR(20),        -- argovis / erddap / gdac
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(wmo_id, cycle_number)
);

-- ══════════════════════════════════
-- Table 3: measurements
-- Individual depth-level readings per profile
-- ══════════════════════════════════
CREATE TABLE IF NOT EXISTS measurements (
    measurement_id  SERIAL PRIMARY KEY,
    profile_id      INTEGER REFERENCES profiles(profile_id),
    pressure        NUMERIC(8,2),       -- dbar
    depth_m         NUMERIC(8,2),       -- metres
    temperature     NUMERIC(8,4),       -- degrees Celsius
    salinity        NUMERIC(8,4),       -- PSU
    temp_qc         SMALLINT,           -- QC flag 1-9
    sal_qc          SMALLINT,           -- QC flag 1-9
    pres_qc         SMALLINT            -- QC flag 1-9
);

-- ══════════════════════════════════
-- Table 4: query_cache
-- Cache repeat queries to avoid API calls
-- ══════════════════════════════════
CREATE TABLE IF NOT EXISTS query_cache (
    cache_id        SERIAL PRIMARY KEY,
    query_hash      VARCHAR(64) UNIQUE, -- MD5 hash of query params
    query_params    JSONB,              -- Original query params
    result_json     JSONB,              -- Cached result
    created_at      TIMESTAMP DEFAULT NOW(),
    expires_at      TIMESTAMP           -- TTL expiry
);

-- ══════════════════════════════════
-- INDEXES for fast queries
-- ══════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_profiles_wmo      ON profiles(wmo_id);
CREATE INDEX IF NOT EXISTS idx_profiles_date     ON profiles(profile_date);
CREATE INDEX IF NOT EXISTS idx_profiles_location ON profiles USING GIST(location);
CREATE INDEX IF NOT EXISTS idx_meas_profile      ON measurements(profile_id);
CREATE INDEX IF NOT EXISTS idx_meas_temp_qc      ON measurements(temp_qc);
CREATE INDEX IF NOT EXISTS idx_meas_sal_qc       ON measurements(sal_qc);
CREATE INDEX IF NOT EXISTS idx_cache_hash        ON query_cache(query_hash);
CREATE INDEX IF NOT EXISTS idx_cache_expiry      ON query_cache(expires_at);

-- ══════════════════════════════════
-- VIEW: clean_measurements
-- Only QC flag 1 and 2 — pre-filtered good data
-- This is the key improvement over existing FloatChats
-- ══════════════════════════════════
CREATE OR REPLACE VIEW clean_measurements AS
SELECT
    m.*,
    p.profile_date,
    p.latitude,
    p.longitude,
    p.wmo_id,
    p.data_mode
FROM measurements m
JOIN profiles p ON m.profile_id = p.profile_id
WHERE
    m.temp_qc IN (1, 2)
AND m.sal_qc  IN (1, 2)
AND m.pres_qc IN (1, 2);

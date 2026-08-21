-- GaweYuk Slice 4A: Job Source & Verification Network.
-- Forward-only migration. Additive; does not modify Slice 1-3 tables.
-- This single migration file accumulates all Slice 4A tables while the
-- feature branch is unmerged (do not create 008 for later 4A tasks).

CREATE TABLE IF NOT EXISTS job_sources (
    source_id TEXT PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    trust_tier TEXT NOT NULL,
    acquisition_method TEXT NOT NULL,
    primary_domain TEXT,
    country_scope_json TEXT NOT NULL,
    compliance_status TEXT NOT NULL,
    rollout_state TEXT NOT NULL,
    health_state TEXT NOT NULL,
    verification_policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_source_state_events (
    event_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_state TEXT,
    new_state TEXT,
    reason_code TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY(source_id) REFERENCES job_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_job_source_state_events_source
ON job_source_state_events(source_id, occurred_at);

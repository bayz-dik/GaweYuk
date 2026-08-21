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


-- Task 4: evidence families and source appearances.

CREATE TABLE IF NOT EXISTS evidence_families (
    evidence_family_id TEXT PRIMARY KEY,
    origin_source_id TEXT,
    origin_external_id TEXT,
    lineage_kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_source_appearances (
    appearance_id TEXT PRIMARY KEY,
    canonical_job_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    apply_url TEXT,
    evidence_family_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    latest_observation_id TEXT NOT NULL,
    appearance_state TEXT NOT NULL,
    UNIQUE(source_id, external_id),
    FOREIGN KEY(canonical_job_id) REFERENCES canonical_jobs(canonical_job_id),
    FOREIGN KEY(latest_observation_id)
        REFERENCES raw_job_observations(observation_id)
);

CREATE INDEX IF NOT EXISTS idx_job_source_appearances_job
ON job_source_appearances(canonical_job_id);

CREATE INDEX IF NOT EXISTS idx_job_source_appearances_family
ON job_source_appearances(evidence_family_id);

-- Normalized provenance for a raw observation: which registered source and
-- evidence family produced it, plus captured apply URL. Kept separate from
-- raw_job_observations so the Slice 1 raw table stays additive-compatible.
CREATE TABLE IF NOT EXISTS observation_provenance (
    observation_id TEXT PRIMARY KEY,
    source_id TEXT,
    evidence_family_id TEXT NOT NULL,
    apply_url TEXT,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(observation_id)
        REFERENCES raw_job_observations(observation_id)
);

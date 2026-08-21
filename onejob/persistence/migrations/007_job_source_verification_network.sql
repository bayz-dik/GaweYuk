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


-- Task 5: company identity graph and immutable identity snapshots.

CREATE TABLE IF NOT EXISTS company_identity_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_identity_relationships (
    relationship_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    verification_method TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    first_verified_at TEXT NOT NULL,
    last_verified_at TEXT NOT NULL,
    FOREIGN KEY(node_id) REFERENCES company_identity_nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_company_identity_rel_company
ON company_identity_relationships(company_id);

CREATE TABLE IF NOT EXISTS company_identity_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    state TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(company_id, input_fingerprint)
);


-- Task 9: immutable job verification snapshots.

CREATE TABLE IF NOT EXISTS job_verification_snapshots (
    verification_id TEXT PRIMARY KEY,
    canonical_job_id TEXT NOT NULL,
    canonical_version_id TEXT,
    identity_snapshot_id TEXT,
    trust_evaluation_id TEXT,
    identity_state TEXT NOT NULL,
    trust_classification TEXT NOT NULL,
    destination_status TEXT NOT NULL,
    freshness_state TEXT NOT NULL,
    corroboration_json TEXT NOT NULL,
    hard_gate_hits_json TEXT NOT NULL,
    unknowns_json TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    verification_policy_version TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_job_verification_fingerprint
ON job_verification_snapshots(canonical_job_id, input_fingerprint);

CREATE TABLE IF NOT EXISTS job_verification_snapshot_evidence (
    verification_id TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    PRIMARY KEY(verification_id, evidence_ref),
    FOREIGN KEY(verification_id)
        REFERENCES job_verification_snapshots(verification_id)
);


-- Task 10: publication decisions (append-only) and current head pointer.

CREATE TABLE IF NOT EXISTS publication_decisions (
    decision_id TEXT PRIMARY KEY,
    canonical_job_id TEXT NOT NULL,
    verification_id TEXT,
    state TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    valid_until TEXT,
    policy_version TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_publication_job_time
ON publication_decisions(canonical_job_id, decided_at DESC);

CREATE TABLE IF NOT EXISTS job_publication_heads (
    canonical_job_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    state TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(decision_id) REFERENCES publication_decisions(decision_id)
);


-- Task 11: human verification review queue.

CREATE TABLE IF NOT EXISTS verification_cases (
    case_id TEXT PRIMARY KEY,
    canonical_job_id TEXT NOT NULL,
    verification_id TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    priority TEXT NOT NULL,
    state TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    assigned_to TEXT,
    resolved_at TEXT,
    resolution_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_verification_cases_state
ON verification_cases(state, priority);

CREATE TABLE IF NOT EXISTS verification_resolutions (
    resolution_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    evidence_snapshot_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    notes TEXT,
    decided_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES verification_cases(case_id)
);

CREATE TABLE IF NOT EXISTS verification_review_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    request_fingerprint TEXT NOT NULL,
    resolution_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);


-- Task 12: persistent reverification work queue.

CREATE TABLE IF NOT EXISTS reverification_work (
    work_id TEXT PRIMARY KEY,
    canonical_job_id TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_class TEXT,
    claimed_at TEXT,
    completed_at TEXT,
    UNIQUE(canonical_job_id, due_at)
);

CREATE INDEX IF NOT EXISTS idx_reverification_due
ON reverification_work(status, due_at);

CREATE TABLE IF NOT EXISTS career_twins (
    twin_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    ontology_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS career_entities (
    entity_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    canonicalized_from_candidate_id TEXT,
    canonical_successor_id TEXT,
    created_at TEXT NOT NULL,
    retired_at TEXT,
    erased_at TEXT,
    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id),
    FOREIGN KEY(canonical_successor_id)
        REFERENCES career_entities(entity_id)
);

CREATE INDEX IF NOT EXISTS idx_career_entities_twin_type_lifecycle
ON career_entities(twin_id, entity_type, lifecycle_state);


CREATE TABLE IF NOT EXISTS career_claims (
    claim_id TEXT PRIMARY KEY,
    claim_family_id TEXT NOT NULL,
    twin_id TEXT NOT NULL,
    subject_entity_id TEXT NOT NULL,

    predicate TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    value_json TEXT,
    value_type TEXT NOT NULL,

    approval_state TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    ontology_version TEXT NOT NULL,

    supersedes_claim_id TEXT,
    rebased_from_claim_id TEXT,

    valid_from TEXT,
    valid_to TEXT,

    created_at TEXT NOT NULL,
    approved_at TEXT,
    retired_at TEXT,
    erased_at TEXT,

    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id),
    FOREIGN KEY(subject_entity_id)
        REFERENCES career_entities(entity_id),
    FOREIGN KEY(supersedes_claim_id)
        REFERENCES career_claims(claim_id),
    FOREIGN KEY(rebased_from_claim_id)
        REFERENCES career_claims(claim_id)
);

CREATE INDEX IF NOT EXISTS idx_career_claims_subject_predicate
ON career_claims(twin_id, subject_entity_id, predicate);

CREATE INDEX IF NOT EXISTS idx_career_claims_family_lifecycle
ON career_claims(claim_family_id, lifecycle_state);

CREATE INDEX IF NOT EXISTS idx_career_claims_twin_active
ON career_claims(twin_id, approval_state, lifecycle_state);


CREATE TABLE IF NOT EXISTS career_evidence (
    evidence_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL,

    source_type TEXT NOT NULL,
    source_reference TEXT,
    evidence_family_id TEXT NOT NULL,

    observed_at TEXT NOT NULL,
    extractor_version TEXT,

    payload_reference TEXT,
    payload_fingerprint TEXT NOT NULL,

    trust_tier TEXT NOT NULL,
    independence_status TEXT NOT NULL,
    privacy_class TEXT NOT NULL,

    erased_at TEXT,

    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id)
);

CREATE INDEX IF NOT EXISTS idx_career_evidence_twin_family
ON career_evidence(twin_id, evidence_family_id);


CREATE TABLE IF NOT EXISTS career_claim_evidence (
    claim_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,

    support_type TEXT NOT NULL,
    confidence REAL NOT NULL,

    PRIMARY KEY(claim_id, evidence_id),

    FOREIGN KEY(claim_id)
        REFERENCES career_claims(claim_id),
    FOREIGN KEY(evidence_id)
        REFERENCES career_evidence(evidence_id)
);


CREATE TABLE IF NOT EXISTS career_claim_assessments (
    assessment_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,

    provenance_trust_tier TEXT NOT NULL,
    claim_confidence REAL NOT NULL
        CHECK(claim_confidence >= 0.0 AND claim_confidence <= 1.0),

    evidence_fingerprint TEXT NOT NULL,
    assessed_at TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,

    FOREIGN KEY(claim_id)
        REFERENCES career_claims(claim_id)
);

CREATE INDEX IF NOT EXISTS idx_career_claim_assessments_claim
ON career_claim_assessments(claim_id, assessed_at);


CREATE TABLE IF NOT EXISTS career_projection_cache (
    twin_id TEXT PRIMARY KEY,

    projection_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    payload_json TEXT NOT NULL,

    built_at TEXT NOT NULL,
    stale_at TEXT,

    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id)
);


CREATE TABLE IF NOT EXISTS career_events (
    event_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL,

    event_type TEXT NOT NULL,
    subject_id TEXT,

    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',

    causation_id TEXT,
    correlation_id TEXT,

    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id)
);

CREATE INDEX IF NOT EXISTS idx_career_events_twin_time
ON career_events(twin_id, occurred_at);


CREATE TABLE IF NOT EXISTS career_event_outbox (
    event_id TEXT PRIMARY KEY,

    status TEXT NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,

    next_attempt_at TEXT,
    processed_at TEXT,
    last_error TEXT,

    FOREIGN KEY(event_id)
        REFERENCES career_events(event_id)
);

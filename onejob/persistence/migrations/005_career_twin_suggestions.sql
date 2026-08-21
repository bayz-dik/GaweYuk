-- Career Twin v2 Slice 2: suggestion intake + review pipeline.
-- Forward-only migration. Does not modify or rewrite any Slice 1 tables.

-- Groups related suggestions from one intake operation.
CREATE TABLE IF NOT EXISTS career_suggestion_batches (
    batch_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL,

    source_type TEXT NOT NULL,
    source_reference TEXT,
    intake_version TEXT NOT NULL,
    evidence_family_id TEXT NOT NULL,

    lifecycle TEXT NOT NULL DEFAULT 'OPEN',

    created_at TEXT NOT NULL,
    completed_at TEXT,

    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id)
);

CREATE INDEX IF NOT EXISTS idx_career_batches_twin_lifecycle
ON career_suggestion_batches(twin_id, lifecycle);


-- Staged possible entities, distinct from canonical career_entities.
CREATE TABLE IF NOT EXISTS career_candidate_entities (
    candidate_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    twin_id TEXT NOT NULL,

    proposed_entity_type TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    display_hint TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL DEFAULT 'STAGED',

    created_at TEXT NOT NULL,
    promoted_entity_id TEXT,

    FOREIGN KEY(batch_id)
        REFERENCES career_suggestion_batches(batch_id),
    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id),
    FOREIGN KEY(promoted_entity_id)
        REFERENCES career_entities(entity_id)
);

CREATE INDEX IF NOT EXISTS idx_career_candidates_batch
ON career_candidate_entities(batch_id);

CREATE INDEX IF NOT EXISTS idx_career_candidates_twin_fingerprint
ON career_candidate_entities(twin_id, fingerprint);


-- Central proposal record with the two-axis (decision x disposition) state.
CREATE TABLE IF NOT EXISTS career_atomic_suggestions (
    suggestion_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    twin_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    resolved_entity_id TEXT,

    predicate TEXT NOT NULL,
    proposed_value_json TEXT,
    value_type TEXT NOT NULL,

    decision_state TEXT NOT NULL DEFAULT 'PENDING',
    disposition TEXT NOT NULL DEFAULT 'READY',

    normalized_value_fingerprint TEXT NOT NULL,
    expected_active_claim_id TEXT,

    version INTEGER NOT NULL DEFAULT 1,

    created_at TEXT NOT NULL,
    decided_at TEXT,
    decision_actor_id TEXT,

    FOREIGN KEY(batch_id)
        REFERENCES career_suggestion_batches(batch_id),
    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id),
    FOREIGN KEY(candidate_id)
        REFERENCES career_candidate_entities(candidate_id),
    FOREIGN KEY(resolved_entity_id)
        REFERENCES career_entities(entity_id),
    FOREIGN KEY(expected_active_claim_id)
        REFERENCES career_claims(claim_id)
);

CREATE INDEX IF NOT EXISTS idx_career_suggestions_batch
ON career_atomic_suggestions(batch_id);

CREATE INDEX IF NOT EXISTS idx_career_suggestions_twin_state
ON career_atomic_suggestions(twin_id, decision_state, disposition);

CREATE INDEX IF NOT EXISTS idx_career_suggestions_fingerprint
ON career_atomic_suggestions(
    twin_id,
    predicate,
    normalized_value_fingerprint
);


-- Normalized many-to-many link between suggestions and evidence.
CREATE TABLE IF NOT EXISTS career_suggestion_evidence (
    suggestion_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,

    PRIMARY KEY(suggestion_id, evidence_id),

    FOREIGN KEY(suggestion_id)
        REFERENCES career_atomic_suggestions(suggestion_id),
    FOREIGN KEY(evidence_id)
        REFERENCES career_evidence(evidence_id)
);


-- Appendable/versioned entity resolution assessments (not mutable truth).
CREATE TABLE IF NOT EXISTS career_entity_resolutions (
    resolution_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    proposed_entity_id TEXT,

    confidence REAL,
    confidence_band TEXT NOT NULL,
    method TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    signals_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL,
    supersedes_resolution_id TEXT,

    FOREIGN KEY(candidate_id)
        REFERENCES career_candidate_entities(candidate_id),
    FOREIGN KEY(proposed_entity_id)
        REFERENCES career_entities(entity_id),
    FOREIGN KEY(supersedes_resolution_id)
        REFERENCES career_entity_resolutions(resolution_id)
);

CREATE INDEX IF NOT EXISTS idx_career_resolutions_candidate
ON career_entity_resolutions(candidate_id, created_at);


-- Mutually incompatible alternatives for a canonical claim family.
CREATE TABLE IF NOT EXISTS career_conflict_sets (
    conflict_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    active_claim_id TEXT,

    status TEXT NOT NULL DEFAULT 'OPEN',
    version INTEGER NOT NULL DEFAULT 1,

    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolution_type TEXT,
    resolution_claim_id TEXT,

    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id),
    FOREIGN KEY(entity_id)
        REFERENCES career_entities(entity_id),
    FOREIGN KEY(active_claim_id)
        REFERENCES career_claims(claim_id),
    FOREIGN KEY(resolution_claim_id)
        REFERENCES career_claims(claim_id)
);

CREATE INDEX IF NOT EXISTS idx_career_conflicts_twin_status
ON career_conflict_sets(twin_id, status);

CREATE INDEX IF NOT EXISTS idx_career_conflicts_family
ON career_conflict_sets(twin_id, entity_id, predicate);


-- Link table between conflicts and their competing suggestions, with an
-- optional cluster key so equivalent proposed values group into one
-- review alternative while preserving individual provenance.
CREATE TABLE IF NOT EXISTS career_conflict_suggestions (
    conflict_id TEXT NOT NULL,
    suggestion_id TEXT NOT NULL,
    cluster_key TEXT,

    PRIMARY KEY(conflict_id, suggestion_id),

    FOREIGN KEY(conflict_id)
        REFERENCES career_conflict_sets(conflict_id),
    FOREIGN KEY(suggestion_id)
        REFERENCES career_atomic_suggestions(suggestion_id)
);


-- Rejection/suppression memory. Never projected as canonical career truth.
CREATE TABLE IF NOT EXISTS career_suppression_records (
    suppression_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL,

    entity_scope TEXT,
    candidate_scope TEXT,
    predicate TEXT NOT NULL,
    normalized_value_fingerprint TEXT NOT NULL,
    evidence_family_scope TEXT,
    source_scope TEXT,

    strength TEXT NOT NULL,
    reason TEXT,

    created_at TEXT NOT NULL,
    expires_at TEXT,
    lifted_at TEXT,

    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id)
);

CREATE INDEX IF NOT EXISTS idx_career_suppression_match
ON career_suppression_records(
    twin_id,
    predicate,
    normalized_value_fingerprint
);


-- Idempotency metadata for consequential write commands.
CREATE TABLE IF NOT EXISTS career_idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    request_fingerprint TEXT NOT NULL,
    result_reference TEXT,
    created_at TEXT NOT NULL
);

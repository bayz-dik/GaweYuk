-- Career Twin v2 Slice 3: Career Intent, Saved Career Targets, contextual evaluation.
-- Forward-only migration. Does not modify or rewrite any Slice 1/2 tables.

-- ---------------------------------------------------------------------------
-- Career Intent
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS career_intents (
    intent_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL UNIQUE,
    active_version_id TEXT,
    created_at TEXT NOT NULL,
    created_by_actor_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS career_intent_versions (
    intent_version_id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    supersedes_version_id TEXT,
    created_by_actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,

    UNIQUE(intent_id, version_number),

    FOREIGN KEY(intent_id)
        REFERENCES career_intents(intent_id),
    FOREIGN KEY(supersedes_version_id)
        REFERENCES career_intent_versions(intent_version_id)
);

CREATE INDEX IF NOT EXISTS idx_career_intent_versions_intent
ON career_intent_versions(intent_id, version_number);

CREATE TABLE IF NOT EXISTS career_intent_statements (
    statement_id TEXT PRIMARY KEY,
    intent_version_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    operator TEXT NOT NULL,
    value_json TEXT,
    value_type TEXT NOT NULL,
    strength TEXT NOT NULL,
    effective_from TEXT,
    expires_at TEXT,
    unknown_policy TEXT,
    provenance_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY(intent_version_id)
        REFERENCES career_intent_versions(intent_version_id)
);

CREATE INDEX IF NOT EXISTS idx_career_intent_statements_version
ON career_intent_statements(intent_version_id);

CREATE TABLE IF NOT EXISTS career_intent_suggestions (
    suggestion_id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    proposed_value_json TEXT,
    proposed_strength TEXT NOT NULL,
    operator TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL,
    source TEXT NOT NULL,
    decision_state TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    fingerprint TEXT NOT NULL,

    FOREIGN KEY(intent_id)
        REFERENCES career_intents(intent_id)
);

CREATE INDEX IF NOT EXISTS idx_career_intent_suggestions_intent
ON career_intent_suggestions(intent_id, decision_state);

CREATE TABLE IF NOT EXISTS career_intent_suppressions (
    suppression_id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    lifted_at TEXT,

    FOREIGN KEY(intent_id)
        REFERENCES career_intents(intent_id)
);

CREATE INDEX IF NOT EXISTS idx_career_intent_suppressions_match
ON career_intent_suppressions(intent_id, fingerprint);


-- ---------------------------------------------------------------------------
-- Saved Career Targets
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS saved_career_targets (
    target_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL,
    active_version_id TEXT,
    lifecycle TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL,
    created_by_actor_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_saved_career_targets_twin
ON saved_career_targets(twin_id, lifecycle);

CREATE TABLE IF NOT EXISTS saved_career_target_versions (
    target_version_id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    supersedes_version_id TEXT,
    display_name TEXT NOT NULL,
    role_focus_json TEXT NOT NULL DEFAULT '[]',
    domain_focus_json TEXT NOT NULL DEFAULT '[]',
    explicit_keywords_json TEXT NOT NULL DEFAULT '[]',
    scope_definition_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,

    UNIQUE(target_id, version_number),

    FOREIGN KEY(target_id)
        REFERENCES saved_career_targets(target_id),
    FOREIGN KEY(supersedes_version_id)
        REFERENCES saved_career_target_versions(target_version_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_career_target_versions_target
ON saved_career_target_versions(target_id, version_number);

CREATE TABLE IF NOT EXISTS target_intent_overrides (
    override_id TEXT PRIMARY KEY,
    target_version_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    operation TEXT NOT NULL,
    value_json TEXT,
    strength TEXT,
    effective_from TEXT,
    expires_at TEXT,
    overrides_statement_id TEXT,
    explicit_exception_authority TEXT,

    FOREIGN KEY(target_version_id)
        REFERENCES saved_career_target_versions(target_version_id)
);

CREATE INDEX IF NOT EXISTS idx_target_intent_overrides_version
ON target_intent_overrides(target_version_id);

CREATE TABLE IF NOT EXISTS target_compatibility_assessments (
    compatibility_id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    target_version_id TEXT NOT NULL,
    against_intent_version_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    checked_at TEXT NOT NULL,
    validator_version TEXT NOT NULL,

    FOREIGN KEY(target_id)
        REFERENCES saved_career_targets(target_id),
    FOREIGN KEY(target_version_id)
        REFERENCES saved_career_target_versions(target_version_id)
);

CREATE INDEX IF NOT EXISTS idx_target_compatibility_lookup
ON target_compatibility_assessments(
    target_version_id,
    against_intent_version_id,
    validator_version
);

CREATE TABLE IF NOT EXISTS target_applicability_assessments (
    assessment_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL,
    job_context_fingerprint TEXT NOT NULL,
    intent_version_id TEXT NOT NULL,
    target_version_id TEXT NOT NULL,
    eligibility TEXT NOT NULL,
    applicability_score REAL NOT NULL,
    confidence_band TEXT NOT NULL,
    signals_json TEXT NOT NULL DEFAULT '[]',
    reasons_json TEXT NOT NULL DEFAULT '[]',
    router_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_target_applicability_lookup
ON target_applicability_assessments(
    twin_id,
    job_context_fingerprint,
    intent_version_id
);

CREATE TABLE IF NOT EXISTS target_routing_decisions (
    routing_decision_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL,
    job_context_fingerprint TEXT NOT NULL,
    intent_version_id TEXT NOT NULL,
    method TEXT NOT NULL,
    selected_target_version_id TEXT,
    winner_score REAL,
    winner_margin REAL,
    router_version TEXT NOT NULL,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    alternatives_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_target_routing_lookup
ON target_routing_decisions(twin_id, job_context_fingerprint);


-- ---------------------------------------------------------------------------
-- Contextual evaluation
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS resolved_target_views (
    resolved_view_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL,
    intent_version_id TEXT NOT NULL,
    target_version_id TEXT,
    routing_decision_id TEXT,
    scope TEXT NOT NULL,
    resolved_statements_json TEXT NOT NULL DEFAULT '[]',
    applied_overrides_json TEXT NOT NULL DEFAULT '[]',
    explicit_exceptions_json TEXT NOT NULL DEFAULT '[]',
    active_temporal_statements_json TEXT NOT NULL DEFAULT '[]',
    tensions_json TEXT NOT NULL DEFAULT '[]',
    validation_status TEXT NOT NULL,
    resolver_version TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,

    UNIQUE(twin_id, input_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_resolved_target_views_twin
ON resolved_target_views(twin_id);

CREATE TABLE IF NOT EXISTS constraint_assessments (
    assessment_id TEXT PRIMARY KEY,
    resolved_view_id TEXT NOT NULL,
    statement_id TEXT NOT NULL,
    result TEXT NOT NULL,
    observed_value_json TEXT,
    evidence_status TEXT NOT NULL,
    unknown_reason TEXT,
    required_action TEXT,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    evaluator_version TEXT NOT NULL,

    FOREIGN KEY(resolved_view_id)
        REFERENCES resolved_target_views(resolved_view_id)
);

CREATE INDEX IF NOT EXISTS idx_constraint_assessments_view
ON constraint_assessments(resolved_view_id);

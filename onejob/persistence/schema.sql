CREATE TABLE IF NOT EXISTS sources (
  source_key TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  health_status TEXT NOT NULL DEFAULT 'UNKNOWN',
  base_reliability REAL NOT NULL DEFAULT 0.50,
  freshness_score REAL NOT NULL DEFAULT 0.50,
  stale_rate REAL,
  duplicate_rate REAL,
  conflict_rate REAL,
  last_success_at TEXT,
  last_failure_at TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  collector_version TEXT
);

CREATE TABLE IF NOT EXISTS raw_job_observations (
  observation_id TEXT PRIMARY KEY,
  source_key TEXT NOT NULL,
  source_type TEXT NOT NULL,
  collector_version TEXT NOT NULL,
  external_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  canonical_hint_url TEXT,
  observed_at TEXT NOT NULL,
  published_at TEXT,
  updated_at TEXT,
  expires_at TEXT,
  title TEXT NOT NULL,
  company_name TEXT NOT NULL,
  location_text TEXT NOT NULL,
  description TEXT NOT NULL,
  salary_min INTEGER,
  salary_max INTEGER,
  currency TEXT,
  employment_type TEXT,
  skills_json TEXT NOT NULL,
  contact_email TEXT,
  source_payload_hash TEXT NOT NULL,
  raw_payload_reference TEXT,
  FOREIGN KEY(source_key) REFERENCES sources(source_key)
);

CREATE INDEX IF NOT EXISTS idx_observations_source_external
ON raw_job_observations(source_key, external_id, observed_at);

CREATE TABLE IF NOT EXISTS companies (
  company_id TEXT PRIMARY KEY,
  normalized_name TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_jobs (
  canonical_job_id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  title TEXT NOT NULL,
  normalized_title TEXT NOT NULL,
  location TEXT NOT NULL,
  normalized_location TEXT NOT NULL,
  description TEXT NOT NULL,
  salary_min INTEGER,
  salary_max INTEGER,
  currency TEXT,
  employment_type TEXT,
  contact_email TEXT,
  lifecycle_state TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  active_status_confidence REAL NOT NULL,
  FOREIGN KEY(company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS canonical_job_sources (
  canonical_job_id TEXT NOT NULL,
  observation_id TEXT NOT NULL UNIQUE,
  source_key TEXT NOT NULL,
  external_id TEXT NOT NULL,
  PRIMARY KEY(canonical_job_id, observation_id),
  FOREIGN KEY(canonical_job_id) REFERENCES canonical_jobs(canonical_job_id),
  FOREIGN KEY(observation_id) REFERENCES raw_job_observations(observation_id)
);

CREATE TABLE IF NOT EXISTS job_versions (
  version_id TEXT PRIMARY KEY,
  canonical_job_id TEXT NOT NULL,
  version_number INTEGER NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  content_hash TEXT NOT NULL,
  changed_fields_json TEXT NOT NULL,
  field_snapshot_json TEXT NOT NULL,
  UNIQUE(canonical_job_id, version_number)
);

CREATE TABLE IF NOT EXISTS job_events (
  event_id TEXT PRIMARY KEY,
  canonical_job_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS field_evidence (
  evidence_id TEXT PRIMARY KEY,
  canonical_job_id TEXT NOT NULL,
  observation_id TEXT NOT NULL,
  field_name TEXT NOT NULL,
  value_json TEXT NOT NULL,
  value_fingerprint TEXT NOT NULL,
  evidence_family_id TEXT NOT NULL,
  independence_status TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  confidence REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS field_consensus (
  canonical_job_id TEXT NOT NULL,
  field_name TEXT NOT NULL,
  selected_value_json TEXT NOT NULL,
  confidence REAL NOT NULL,
  primary_evidence_ids_json TEXT NOT NULL,
  conflicting_evidence_ids_json TEXT NOT NULL,
  resolution_reason TEXT NOT NULL,
  PRIMARY KEY(canonical_job_id, field_name)
);

CREATE TABLE IF NOT EXISTS source_conflicts (
  conflict_id TEXT PRIMARY KEY,
  canonical_job_id TEXT NOT NULL,
  field_name TEXT NOT NULL,
  status TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  resolved_at TEXT,
  evidence_ids_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_runs (
  run_id TEXT PRIMARY KEY,
  source_key TEXT NOT NULL,
  collector_version TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  observations_count INTEGER NOT NULL DEFAULT 0,
  new_count INTEGER NOT NULL DEFAULT 0,
  changed_count INTEGER NOT NULL DEFAULT 0,
  unchanged_count INTEGER NOT NULL DEFAULT 0,
  closed_count INTEGER NOT NULL DEFAULT 0,
  warnings_count INTEGER NOT NULL DEFAULT 0,
  error_summary TEXT
);

CREATE TABLE IF NOT EXISTS field_conflict_records (
    conflict_id TEXT PRIMARY KEY,
    canonical_job_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    status TEXT NOT NULL,
    selected_value_json TEXT,
    confidence REAL NOT NULL,
    primary_evidence_ids_json TEXT NOT NULL,
    conflicting_evidence_ids_json TEXT NOT NULL,
    resolution_reason TEXT,
    detected_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT,
    UNIQUE(canonical_job_id, field_name),
    FOREIGN KEY(canonical_job_id)
        REFERENCES canonical_jobs(canonical_job_id)
);

CREATE INDEX IF NOT EXISTS
idx_field_conflict_records_job_status
ON field_conflict_records(
    canonical_job_id,
    status
);

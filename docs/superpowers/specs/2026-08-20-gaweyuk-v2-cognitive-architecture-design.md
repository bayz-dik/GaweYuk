# GaweYuk V2 Cognitive Architecture Design

## 1. Purpose

GaweYuk is not a job board. It is a career decision system that builds one unified labor-market view from many independent job sources, determines the best-supported canonical truth about each opportunity, evaluates whether the opportunity is legitimate and active, reasons about fit and user policy, and recommends the best next action with explicit evidence and uncertainty.

V2 replaces the MVP's demo-only ingestion path with a real-data foundation while preserving the existing explainable matching, trust, answer, and decision behavior.

The long-term system must optimize decision quality, not application volume.

## 2. Product Constitution

These rules are project-wide invariants.

1. **Evidence before conclusion.** Every important field, score, and decision must be traceable to evidence.
2. **Uncertainty is first-class.** Unknown, stale, contradictory, or weakly supported data must remain uncertain instead of being silently guessed.
3. **No invented candidate facts.** Generated application content may rephrase supported facts but may not create experience, education, dates, skills, salary history, certifications, or personal facts.
4. **Hard user policy outranks semantic similarity.** A 99% profile match cannot override an explicit user constraint.
5. **Source appearances are not independent evidence by default.** Mirrored copies derived from one upstream source must be treated as one evidence family.
6. **Legitimate company != legitimate job != active hiring.** Company identity, posting authenticity, vacancy freshness, and hiring intent are separate beliefs.
7. **High-impact actions require stronger evidence.** Automation thresholds rise with irreversibility and user impact.
8. **GaweYuk may abstain.** `RESEARCH`, `ASK_USER`, `REVIEW`, `WAIT`, or `SKIP` are valid superior outcomes when the evidence does not support `APPLY`.
9. **User control is explicit.** Learned preferences may produce suggestions, never silent changes to hard policy.
10. **Optimize the user's career outcome, not platform engagement.** No feature should intentionally maximize time-in-app, application count, or notification volume at the expense of decision quality.

## 3. Scope Classification

V2 is an architectural expansion composed of several bounded subsystems. To keep implementation testable, V2 is divided into milestones.

### V2.0 — Real Data Foundation

Implementation target for the next engineering cycle:

- persistent database for jobs, observations, sources, evidence, and versions;
- universal collector contract;
- live connectors for structured ATS sources;
- adapter slots for job portals and open-web sources;
- provenance and evidence lineage;
- canonical job identity and deduplication;
- temporal job lifecycle and version history;
- source conflict representation;
- field-level confidence;
- source reliability baseline;
- freshness/stale detection;
- temporal trust inputs;
- CLI/API endpoints for collection, source health, and job history;
- migration path from `DemoRepository` to persistent repositories.

### V2.1 — Universal Source Coverage

- LinkedIn adapter architecture;
- JobStreet adapter architecture;
- Indeed adapter architecture;
- Glints adapter architecture;
- Kalibrr adapter architecture;
- company career-page discovery;
- connector health and degradation detection;
- crawl scheduling and budget allocation.

Adapters must comply with the same source contract. Where a platform cannot be collected reliably or permissibly through a stable public interface, the adapter may be disabled, assisted, link-only, or rely on user-authorized/browser-side collection rather than pretending to provide a reliable server-side collector.

### V2.2 — TrustGraph

- company identity graph;
- domain, email, recruiter, phone, ATS, job, and source relationships;
- evidence-family lineage;
- scam-pattern clustering;
- coordinated campaign detection;
- data poisoning defenses;
- ghost/evergreen classification;
- quarantine state;
- job privacy-risk score.

### V2.3 — Career Intelligence

- richer Career Twin;
- role ontology;
- skill ontology and transfer graph;
- market demand and skill momentum;
- salary truth estimates;
- commute intelligence;
- hiring-intent score;
- opportunity score;
- career optionality and trajectory.

### V2.4 — Application Intelligence

- Answer Vault;
- contradiction graph;
- application pre-flight validation;
- universal form-question ontology;
- assisted application routing;
- bounded autonomy and action risk;
- application outcome tracking.

### V2.5 — Learning and Prediction

- response/interview/offer funnel models;
- calibration;
- survival/time-to-response models;
- CV strategy experiments;
- exploration vs exploitation;
- outcome attribution;
- preference drift suggestions.

### V3 — Cognitive Layer

North-star capabilities, deliberately not required for V2.0:

- causal reasoning;
- counterfactual career simulation;
- expected value of information;
- active-learning question selection;
- multi-objective optimization;
- portfolio-level application planning;
- adversarial/falsification reasoning;
- agentic research orchestration;
- robust decision making across future scenarios.

## 4. Architectural Principle: Universal Ingestion Mesh

Every source is an adapter behind one contract.

```text
ATS / API -----------\
Job Portals -----------\
Company Career Pages ----> Source Adapter -> RawJobObservation
Open Web -------------/
Government / Events --/
                                |
                                v
                        Provenance / Lineage
                                |
                                v
                           Normalization
                                |
                                v
                     Entity Resolution / Dedupe
                                |
                                v
                       Temporal Canonical Job
                                |
             +------------------+------------------+
             |                  |                  |
          TrustGraph      Career Intelligence   Market Graph
             |                  |                  |
             +------------------+------------------+
                                |
                                v
                         Decision / Action
```

The core domain must never need source-specific logic for LinkedIn, Greenhouse, JobStreet, Lever, or any future source.

## 5. Source Classes

Each source declares a `source_type`:

- `ats`
- `job_portal`
- `company_career`
- `government`
- `agency`
- `university`
- `event`
- `open_web`
- `user_supplied`

`source_type` is descriptive, not an automatic trust verdict.

## 6. Universal Collector Contract

A collector is responsible only for obtaining source observations and reporting collector health. It does not perform canonical deduplication, trust classification, user matching, or application decisions.

Conceptual interface:

```python
class Collector(Protocol):
    source_key: str
    source_type: SourceType

    def collect(self, target: CollectionTarget) -> CollectionBatch:
        ...
```

`CollectionBatch` contains:

- collector identity and version;
- started/finished timestamps;
- collection target;
- raw observations;
- warnings;
- rate-limit/degradation metadata;
- collection status.

The first live implementations in V2.0 are structured ATS/public-job-board connectors because they provide deterministic fixtures for proving the ingestion architecture. Portal adapters remain first-class architecture from day one and join once the core is stable.

## 7. Raw Job Observation

The atomic ingestion object is an observation, not a canonical job.

Required conceptual fields:

```text
observation_id
source_key
source_type
collector_version
external_id
source_url
canonical_hint_url
observed_at
published_at?
updated_at?
expires_at?
title
company_name
location_text
description
salary_min?
salary_max?
currency?
employment_type?
skills[]
contact_email?
source_payload_hash
raw_payload_reference?
```

An observation is immutable after storage. A later crawl creates a new observation.

This allows exact reconstruction of what GaweYuk knew at any point in time.

## 8. Provenance and Evidence Lineage

Every observation receives lineage metadata.

Example:

```text
Company ATS -> LinkedIn mirror -> aggregator mirror
```

These must not count as three independent confirmations.

Evidence lineage records:

```text
evidence_id
observation_id
field_name
value_fingerprint
upstream_source?
evidence_family_id
observed_at
confidence
```

When upstream lineage is unknown, the system may mark evidence as `independence_unknown`; it must not silently assume independence.

## 9. Canonical Job Identity

A canonical job represents one real-world opportunity as best currently understood.

Identity signals include:

1. source-provided requisition/external IDs;
2. canonical company identity;
3. normalized role concept/title;
4. normalized location;
5. description similarity;
6. canonical/redirect URL relationships;
7. publication-time proximity;
8. salary/employment-type agreement;
9. evidence lineage.

Deduplication produces a match probability and evidence rather than only a boolean.

Outcomes:

- `SAME_OPPORTUNITY`
- `LIKELY_SAME`
- `UNCERTAIN`
- `DISTINCT`

Only sufficiently supported matches are automatically merged. `UNCERTAIN` pairs remain separate but linked for later research.

## 10. Company Entity Resolution

Company names are aliases, not identities.

```text
PT Example Indonesia
Example Indonesia
Example, PT
EXAMPLE
```

must be capable of resolving to one `company_id` when evidence supports it.

Company identity sources may include:

- official domain;
- ATS tenant/company board;
- company career URL;
- normalized legal/display name;
- known addresses;
- verified source relationships.

V2.0 implements deterministic alias normalization and stable company IDs. Rich graph resolution belongs to V2.2.

## 11. Temporal Job Model

A canonical job has history, not one mutable row of truth.

Lifecycle states:

```text
DISCOVERED
ACTIVE
UPDATED
CLOSING
CLOSED
REOPENED
STALE
EVERGREEN
GHOST_SUSPECTED
QUARANTINED
```

V2.0 must implement at least:

```text
DISCOVERED
ACTIVE
UPDATED
CLOSED
REOPENED
STALE
```

Other states remain schema-compatible extensions.

## 12. Job Events

Every meaningful state transition is represented as an event.

Required V2.0 events:

```text
JOB_DISCOVERED
JOB_SEEN
JOB_CHANGED
JOB_CLOSED
JOB_REOPENED
SOURCE_CONFLICT_DETECTED
SOURCE_CONFLICT_RESOLVED
SOURCE_DEGRADED
SOURCE_RECOVERED
```

Future-compatible event names include:

```text
TRUST_CHANGED
HIRING_INTENT_CHANGED
JOB_QUARANTINED
JOB_VERIFIED
```

Events are append-only.

## 13. Job Version History

A version is created when canonical material fields change.

Material fields:

- title/role concept;
- company identity;
- location;
- description requirements;
- salary range;
- employment type;
- application URL/canonical destination;
- published/closing dates when available.

A version stores:

```text
version_id
canonical_job_id
version_number
valid_from
valid_to?
content_hash
changed_fields[]
field_snapshot
```

Examples of intelligence derived later from versions:

- salary increased;
- experience requirement relaxed;
- closing date extended;
- title changed;
- job repeatedly reopened.

## 14. Consensus Engine

The canonical job is constructed field by field from source evidence rather than by selecting one entire posting.

For each field the engine records:

```text
selected_value
confidence
primary_evidence_ids[]
conflicting_evidence_ids[]
resolution_reason
```

Baseline evidence priorities in V2.0 may use deterministic rules, but the data model must support learned source reliability later.

Example salary conflict:

```text
Company ATS: 6.5-8.0M
JobStreet:   5.0-7.0M
LinkedIn:   unknown

Canonical salary: 6.5-8.0M
Confidence: 0.94
Primary reason: current official company ATS observation
Conflict retained: JobStreet differs
```

The conflict is never discarded from history.

## 15. Field-Level Confidence

A job does not have one global truth confidence.

Minimum field-confidence dimensions:

```text
title_confidence
company_confidence
location_confidence
description_confidence
salary_confidence
published_at_confidence
active_status_confidence
```

Confidence must be constrained to `[0.0, 1.0]`.

A future model may produce calibrated probabilities; V2.0 starts with transparent deterministic weights.

## 16. Source Reliability Model

Source reliability is separate from source type.

A source profile stores:

```text
source_key
source_type
health_status
base_reliability
freshness_score
stale_rate?
duplicate_rate?
conflict_rate?
last_success_at?
last_failure_at?
consecutive_failures
collector_version
```

Initial reliability may use sensible defaults, but no source receives permanent trust merely because it is an ATS or large portal.

Later reliability updates may use:

- confirmed canonical agreement;
- stale-posting frequency;
- field conflict rate;
- redirect integrity;
- user/company verification;
- fraud history.

## 17. Collector Health

Health states:

```text
HEALTHY
DEGRADED
RATE_LIMITED
BROKEN
DISABLED
UNKNOWN
```

A collector is `DEGRADED` when it returns incomplete/structurally suspicious data but is still partially usable.

Collector failure must never crash ingestion for unrelated sources.

## 18. Freshness and Staleness

Freshness is source- and job-aware.

V2.0 baseline rules:

- `last_seen_at` updates whenever a canonical job is observed through any current source;
- a job is not closed merely because one mirror disappears;
- disappearance from the canonical/official source carries more weight than disappearance from a mirror;
- stale status is an inference with confidence, not deletion;
- closed jobs remain queryable through history.

No data is physically deleted simply because a vacancy closes.

## 19. TrustGraph Boundary

V2.0 adds temporal/provenance signals to the existing Trust Engine but does not attempt the full V2.2 fraud graph.

V2.0 Trust inputs include:

- official/current canonical source evidence;
- number of independent evidence families;
- current source health;
- age of evidence;
- cross-source conflicts;
- suspicious payment/contact signals already supported by V1;
- active/stale/closed status confidence.

Trust outputs remain explainable.

Trust labels must avoid categorical accusations unless hard evidence exists. Preferred states:

```text
VERIFIED
LIKELY_LEGIT
UNCERTAIN
SUSPICIOUS
HIGH_RISK
STALE
```

## 20. Hiring Intent Boundary

Hiring Intent is conceptually distinct from Trust.

```text
Trust: Is this posting/source/company relationship believable?
Hiring Intent: Does available evidence suggest the employer is actively trying to fill this role now?
```

V2.0 records the evidence required to compute Hiring Intent later but does not expose a high-confidence predictive model yet.

Future signals:

- vacancy recency;
- related hiring volume;
- requirement relaxation;
- salary increases;
- closing-date extensions;
- repeated reopen/repost behavior;
- company hiring pulse.

## 21. Persistent Storage

V2.0 requires persistence.

### Development / Termux

SQLite is the default because it runs locally without a service dependency.

### Production

PostgreSQL is the intended production database.

The repository interface must avoid SQLite-specific domain behavior so PostgreSQL migration does not require rewriting intelligence modules.

Core tables/entities:

```text
sources
collection_runs
raw_job_observations
companies
canonical_jobs
canonical_job_sources
job_versions
job_events
field_evidence
field_consensus
source_conflicts
```

Existing user profile data remains logically separate from the public job graph.

## 22. Repository Boundaries

The current `DemoRepository` must not remain the only data source.

V2.0 introduces focused repositories:

```text
JobRepository
SourceRepository
ObservationRepository
EvidenceRepository
JobHistoryRepository
CollectionRunRepository
```

A composed persistence service may coordinate transactions, but each interface must have one clear responsibility.

`DemoRepository` remains available only for deterministic demo/test usage.

## 23. Migration from V1 Service

Current flow:

```text
DemoRepository -> normalize -> dedupe -> match -> trust -> decision
```

V2.0 target flow:

```text
Collectors -> ObservationRepository
          -> Canonicalization Pipeline
          -> persistent Canonical Jobs
          -> existing match/trust/policy/decision service
```

The existing matching and answer engines should not need to know whether a job originated from demo JSON, Greenhouse, JobStreet, or company careers.

## 24. API Contract V2.0

Existing endpoints remain compatible where practical.

Existing:

```text
GET  /health
GET  /api/jobs
GET  /api/jobs/{job_id}
GET  /api/profile
POST /api/answers/suggest
```

New:

```text
GET  /api/sources
GET  /api/sources/{source_key}
POST /api/collect
GET  /api/collections/{run_id}
GET  /api/jobs/{job_id}/history
GET  /api/jobs/{job_id}/evidence
GET  /api/jobs/{job_id}/conflicts
```

`POST /api/collect` initiates an explicit bounded collection run. Scheduling is a later adapter around the same service.

## 25. CLI Contract V2.0

Existing commands remain.

New commands:

```bash
python -m onejob.cli collect
python -m onejob.cli sources
python -m onejob.cli source <source_key>
python -m onejob.cli history <job_id>
python -m onejob.cli evidence <job_id>
```

Example collection output:

```text
GaweYuk Collector

Sources checked:       18
Raw observations:     427
New opportunities:     83
Canonical jobs:       351
Duplicates merged:     76
Changed jobs:          14
Closed jobs:            8
Trust warnings:         5
```

Numbers are illustrative output formatting, not hard-coded expected values.

## 26. ATS Connectors in V2.0

Initial structured connectors:

- Greenhouse;
- Lever;
- Ashby.

Each connector must support injected HTTP clients/fixtures for deterministic tests.

The core collector contract must already support future connectors without schema changes.

## 27. Portal and Open-Web Adapters

V2.0 creates adapter interfaces and health semantics for:

- LinkedIn;
- JobStreet;
- Indeed;
- Glints;
- Kalibrr;
- company career pages;
- government sources;
- agencies/events.

The presence of an adapter type does not imply live scraping is enabled.

Where reliable public access is unavailable, the adapter status must say so rather than disguising a broken collector as coverage.

## 28. Adaptive Collection North Star

Future collection scheduling should optimize information gain, not brute-force frequency.

Potential priority signals:

- source historically changes often;
- company currently mass hiring;
- vacancy near closing;
- unresolved high-value field conflict;
- missing canonical-source confirmation;
- source reliability is uncertain;
- job is a high opportunity match for active users.

This remains outside V2.0 scheduling implementation but the collection API must not block it.

## 29. Evidence Expiration

Evidence stores observation time and may decay in confidence.

V2.0 uses rule-based freshness windows; later versions may calibrate decay by field/source type.

Examples:

- official vacancy active-status evidence decays quickly;
- legal company identity decays slowly;
- recruiter-company association decays faster than company domain ownership;
- salary/job requirement evidence is version-specific.

## 30. Conflict-Driven Research North Star

When high-value fields conflict, GaweYuk should eventually schedule targeted research rather than merely averaging values.

Example:

```text
Conflict: salary
Decision sensitivity: HIGH
Best missing evidence: official company posting
Action: research before auto-apply
```

V2.0 stores enough conflict metadata to enable this later.

## 31. Decision Quality and Abstention

A future `decision_confidence` should depend on:

- match certainty;
- trust certainty;
- information completeness;
- policy certainty;
- field conflicts;
- answer confidence;
- action reversibility.

V2.0 does not yet automate submissions. It must preserve the ability to produce:

```text
APPLY
REVIEW
SKIP
BLOCK
```

and remain schema-compatible with future:

```text
RESEARCH
ASK_USER
WAIT
```

## 32. Privacy Boundary

The public Job Graph and private Career Twin must remain logically distinct.

Collector code must never receive private user profile data merely to fetch public jobs.

Future personalized collection scheduling may receive coarse query criteria through an explicit scoped interface, not unrestricted Career Twin access.

## 33. Security

V2.0 constraints:

- no credentials committed to Git;
- connectors use environment/config injection for secrets when a source requires them;
- raw HTML/payload is treated as untrusted input;
- source URLs are validated before server-side fetching;
- redirect targets are recorded;
- arbitrary user-provided URLs must not become unrestricted SSRF primitives;
- database writes use parameterized APIs/ORM behavior;
- collection errors are sanitized before API exposure.

## 34. Observability

Every collection run records:

```text
run_id
source_key
collector_version
started_at
finished_at
status
observations_count
new_count
changed_count
unchanged_count
closed_count
warnings_count
error_summary?
```

This is the foundation for Collector Health and future reliability metrics.

## 35. Error Handling

Principles:

1. one source failure cannot abort unrelated sources;
2. malformed observation is quarantined/rejected with a reason;
3. temporary network failure does not mark jobs closed;
4. rate limiting produces `RATE_LIMITED`, not generic failure;
5. parser/schema drift produces `DEGRADED` or `BROKEN` based on severity;
6. canonicalization conflict does not discard source data;
7. DB transaction failure must not partially apply a canonicalization batch.

## 36. Testing Strategy

All new production behavior follows TDD.

Required test layers:

### Unit

- connector payload -> `RawJobObservation`;
- normalization;
- field evidence creation;
- canonical identity scoring;
- consensus selection;
- conflict detection;
- job-version diff;
- lifecycle transitions;
- freshness/stale rules;
- source-health transitions.

### Integration

- collection batch -> SQLite -> canonical jobs;
- repeated collection produces `JOB_SEEN`, not duplicate jobs;
- changed posting produces new version and `JOB_CHANGED`;
- disappeared mirror does not prematurely close canonical job;
- official-source removal plus sufficient evidence can close/stale a job;
- API reads persisted results;
- existing matching/trust/decision still works on persisted jobs.

### Regression

All V1 tests must remain green unless an explicitly documented interface migration updates them.

## 37. V2.0 Success Criteria

V2.0 is complete only when all are true:

1. GaweYuk can persist observations and canonical jobs in SQLite on Termux.
2. At least Greenhouse, Lever, and Ashby connectors satisfy the same collector interface and deterministic fixture tests.
3. Running the same collection twice does not create duplicate canonical jobs or duplicate material versions.
4. A material job change creates a new version with changed-field evidence.
5. Multiple source observations can merge into one canonical opportunity while retaining each source and lineage.
6. Conflicting field values remain visible and produce field-level confidence.
7. Source health is observable and isolated per connector.
8. Jobs have lifecycle/freshness state and history.
9. Existing matching, policy, trust, decision, and answer behavior can consume persisted canonical jobs.
10. CLI and API expose collection, source status, job history, evidence, and conflicts.
11. Full test suite is green.
12. No live connector failure can destroy previously persisted job history.

## 38. Explicit Non-Goals for V2.0

- auto-submit applications;
- browser automation;
- recruiter messaging;
- production multi-user authentication;
- ML-based fraud classification;
- causal inference;
- calibrated offer prediction;
- full skill ontology;
- market forecasting;
- autonomous policy modification;
- full LinkedIn/JobStreet/Indeed scraping implementation;
- mobile-native application.

These are deliberately deferred, not forgotten.

## 39. File/Module Direction

The exact implementation plan may adjust names after code review, but the responsibility boundaries are:

```text
onejob/
  collectors/
    base.py
    greenhouse.py
    lever.py
    ashby.py
  ingestion/
    models.py
    pipeline.py
    consensus.py
    identity.py
    lifecycle.py
  persistence/
    db.py
    repositories.py
    schema.py
  provenance/
    evidence.py
    lineage.py
  source_health.py
  service.py
  api.py
  cli.py
```

Existing matching/trust/answers/decision modules remain domain consumers rather than being merged into ingestion.

## 40. Branding and Package Naming

User-facing product name: **GaweYuk**.

The Python package remains `onejob` during V2.0 to avoid unrelated import churn. A package rename is a separate migration after V2.0 is stable.

## 41. North-Star Cognitive Architecture

The future system is organized around:

```text
PERCEPTION
- ingestion
- market signals
- TrustGraph

MEMORY
- temporal job graph
- Career Twin
- outcomes
- decision history

REASONING
- evidence arbitration
- uncertainty
- causal/counterfactual reasoning
- constraint satisfaction
- optimization

PLANNING
- strategic career plan
- tactical opportunity portfolio
- operational next action

ACTION
- research
- ask user
- prepare application
- bounded execution

LEARNING
- calibration
- outcome models
- source reliability
- preference suggestions
```

This is a North Star, not permission to prematurely implement every layer in V2.0.

## 42. Final Engineering Rule

When there is a conflict between adding another "smart" feature and improving truth, provenance, uncertainty, reproducibility, or testability, V2 chooses the latter.

A less flashy decision backed by strong evidence is better than a sophisticated prediction that GaweYuk cannot explain or reproduce.

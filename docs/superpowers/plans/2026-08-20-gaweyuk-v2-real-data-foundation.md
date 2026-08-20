# GaweYuk V2.0 Real Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the demo-only job ingestion path with a persistent, temporal, evidence-preserving real-data foundation that can ingest structured ATS observations, canonicalize them, retain provenance/version history, and expose collection/history/source state through the existing GaweYuk API and CLI.

**Architecture:** Keep the existing `onejob` package and its matching/trust/policy/answer modules as domain consumers. Add a source-agnostic collector contract, immutable observations, SQLite persistence through focused repositories, a canonicalization/versioning pipeline, lifecycle/source-health services, and a persisted service path that still produces the V1 job shape. SQLite is the local/Termux implementation; repository interfaces must not encode SQLite-only domain behavior so PostgreSQL can replace it later.

**Tech Stack:** Python 3.11+, Pydantic 2.8+, FastAPI 0.115+, sqlite3 from the Python standard library, httpx 0.27+, pytest 8+

**Spec:** `docs/superpowers/specs/2026-08-20-gaweyuk-v2-cognitive-architecture-design.md`

## Global Constraints

- User-facing product name remains **GaweYuk**.
- Python package remains `onejob` during V2.0.
- Every important field/decision remains traceable to evidence.
- Unknown/stale/conflicting data stays uncertain; never silently guess.
- No candidate facts may be invented.
- Collector code must not receive private Career Twin data.
- One collector failure must not abort unrelated collectors.
- Raw observations, job events, and job versions are append-only.
- Closed/stale jobs remain queryable; collection must never destroy history.
- Existing V1 tests remain green unless an explicitly documented compatible migration updates them.
- No auto-submit/browser automation is implemented in V2.0.
- No unrestricted user-provided server-side URL fetching is added.

---

## File Structure Locked by This Plan

```text
onejob/
  collectors/
    __init__.py
    base.py              # Collector protocol, target/batch/result types
    greenhouse.py        # Greenhouse structured connector
    lever.py             # Lever structured connector
    ashby.py             # Ashby structured connector
  ingestion/
    __init__.py
    models.py            # Observation, evidence, consensus, version/event models
    identity.py          # Stable company/job fingerprints and merge scoring
    consensus.py         # Field arbitration and explicit source conflicts
    lifecycle.py         # lifecycle transition decisions and freshness rules
    pipeline.py          # observation -> persistence -> canonicalization orchestration
  persistence/
    __init__.py
    db.py                # SQLite connection + transaction boundary + schema bootstrap
    repositories.py      # focused repository implementations
    schema.sql           # SQL schema only
  provenance/
    __init__.py
    evidence.py          # observation -> field evidence
    lineage.py           # evidence-family derivation
  source_health.py       # source health state transitions
  repository.py          # keep DemoRepository; add persisted profile compatibility helpers only
  service.py             # persisted jobs path + existing domain evaluation
  api.py                 # new V2 endpoints while preserving V1 routes
  cli.py                 # collect/sources/source/history/evidence commands

tests/
  fixtures/
    greenhouse_jobs.json
    lever_jobs.json
    ashby_jobs.json
  test_collector_contract.py
  test_collectors_greenhouse.py
  test_collectors_lever.py
  test_collectors_ashby.py
  test_persistence.py
  test_evidence_lineage.py
  test_identity_consensus.py
  test_version_lifecycle.py
  test_ingestion_pipeline.py
  test_service_persisted.py
  test_api_v2.py
  test_cli_v2.py
```

---

### Task 1: Universal Observation and Collector Contract

**Files:**
- Create: `onejob/collectors/__init__.py`
- Create: `onejob/collectors/base.py`
- Create: `onejob/ingestion/__init__.py`
- Create: `onejob/ingestion/models.py`
- Test: `tests/test_collector_contract.py`

**Interfaces:**
- Produces: `SourceType`, `CollectorHealthStatus`, `CollectionStatus`, `CollectionTarget`, `RawJobObservation`, `CollectionBatch`, `Collector`.
- `Collector.collect(target: CollectionTarget) -> CollectionBatch` is the only ingestion-facing connector entry point.

- [ ] **Step 1: Write the failing contract test**

```python
# tests/test_collector_contract.py
from datetime import datetime, timezone
from onejob.collectors.base import Collector, CollectionTarget
from onejob.ingestion.models import RawJobObservation, SourceType


class FixtureCollector:
    source_key = "fixture"
    source_type = SourceType.ATS
    collector_version = "test-1"

    def collect(self, target: CollectionTarget):
        from onejob.collectors.base import CollectionBatch, CollectionStatus
        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            status=CollectionStatus.SUCCESS,
            observations=[RawJobObservation(
                observation_id="obs-1",
                source_key="fixture",
                source_type=SourceType.ATS,
                collector_version="test-1",
                external_id="job-1",
                source_url="https://example.test/jobs/1",
                observed_at=datetime.now(timezone.utc),
                title="Production Operator",
                company_name="PT Example",
                location_text="Bekasi",
                description="Operate production machinery.",
                source_payload_hash="abc123",
            )],
        )


def test_collector_contract_returns_immutable_observations():
    collector: Collector = FixtureCollector()
    batch = collector.collect(CollectionTarget(tenant="example"))
    assert batch.source_key == "fixture"
    assert batch.observations[0].external_id == "job-1"
    assert batch.observations[0].model_config["frozen"] is True
```

- [ ] **Step 2: Run test to verify RED**

Run:
```bash
pytest tests/test_collector_contract.py -v
```
Expected: import failure because `onejob.collectors.base` and `onejob.ingestion.models` do not exist.

- [ ] **Step 3: Implement minimal models and collector protocol**

```python
# onejob/ingestion/models.py
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    ATS = "ats"
    JOB_PORTAL = "job_portal"
    COMPANY_CAREER = "company_career"
    GOVERNMENT = "government"
    AGENCY = "agency"
    UNIVERSITY = "university"
    EVENT = "event"
    OPEN_WEB = "open_web"
    USER_SUPPLIED = "user_supplied"


class RawJobObservation(BaseModel):
    model_config = ConfigDict(frozen=True)
    observation_id: str
    source_key: str
    source_type: SourceType
    collector_version: str
    external_id: str
    source_url: str
    canonical_hint_url: Optional[str] = None
    observed_at: datetime
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    title: str
    company_name: str
    location_text: str
    description: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None
    employment_type: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    contact_email: Optional[str] = None
    source_payload_hash: str
    raw_payload_reference: Optional[str] = None
```

```python
# onejob/collectors/base.py
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Protocol
from pydantic import BaseModel, Field
from onejob.ingestion.models import RawJobObservation, SourceType


class CollectionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    RATE_LIMITED = "RATE_LIMITED"


class CollectionTarget(BaseModel):
    tenant: str


class CollectionBatch(BaseModel):
    source_key: str
    source_type: SourceType
    collector_version: str
    target: CollectionTarget
    started_at: datetime
    finished_at: datetime
    status: CollectionStatus
    observations: list[RawJobObservation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_summary: str | None = None


class Collector(Protocol):
    source_key: str
    source_type: SourceType
    collector_version: str
    def collect(self, target: CollectionTarget) -> CollectionBatch: ...
```

- [ ] **Step 4: Run contract test GREEN**

```bash
pytest tests/test_collector_contract.py -v
```
Expected: `1 passed`.

- [ ] **Step 5: Run V1 regression suite**

```bash
pytest -q
```
Expected: existing tests plus contract test all pass.

- [ ] **Step 6: Commit**

```bash
git add -- onejob/collectors/__init__.py onejob/collectors/base.py onejob/ingestion/__init__.py onejob/ingestion/models.py tests/test_collector_contract.py
git commit -m "feat: add universal collector observation contract"
```

---

### Task 2: SQLite Persistence and Focused Repositories

**Files:**
- Create: `onejob/persistence/__init__.py`
- Create: `onejob/persistence/schema.sql`
- Create: `onejob/persistence/db.py`
- Create: `onejob/persistence/repositories.py`
- Test: `tests/test_persistence.py`

**Interfaces:**
- Consumes: `RawJobObservation`, `SourceType`, `CollectionBatch` from Task 1.
- Produces: `Database`, `ObservationRepository`, `SourceRepository`, `JobRepository`, `JobHistoryRepository`, `EvidenceRepository`, `CollectionRunRepository`.
- All repository methods accept a `sqlite3.Connection` owned by `Database.transaction()`; intelligence modules never issue SQL.

- [ ] **Step 1: Write failing persistence test**

```python
# tests/test_persistence.py
from datetime import datetime, timezone
from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.persistence.db import Database
from onejob.persistence.repositories import ObservationRepository


def observation():
    return RawJobObservation(
        observation_id="obs-1", source_key="fixture", source_type=SourceType.ATS,
        collector_version="v1", external_id="job-1", source_url="https://example.test/1",
        observed_at=datetime.now(timezone.utc), title="Operator", company_name="PT Example",
        location_text="Bekasi", description="Operate machines", source_payload_hash="hash-1"
    )


def test_observation_repository_is_idempotent_by_observation_id(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    repo = ObservationRepository()
    with db.transaction() as conn:
        assert repo.insert(conn, observation()) is True
        assert repo.insert(conn, observation()) is False
    with db.connection() as conn:
        rows = repo.list_by_source(conn, "fixture")
    assert [row.observation_id for row in rows] == ["obs-1"]
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_persistence.py -v
```
Expected: import failure for `onejob.persistence.db`.

- [ ] **Step 3: Add schema**

`onejob/persistence/schema.sql` must create these tables with foreign keys enabled:

```sql
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
```

- [ ] **Step 4: Implement `Database` transaction boundaries**

```python
# onejob/persistence/db.py
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self):
        schema = (Path(__file__).with_name("schema.sql")).read_text()
        with self._connect() as conn:
            conn.executescript(schema)

    @contextmanager
    def connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
```

- [ ] **Step 5: Implement observation repository serialization with `INSERT OR IGNORE` and row->Pydantic conversion**

Use `json.dumps(observation.skills)` for `skills_json`, `datetime.isoformat()` for timestamps, and `RawJobObservation.model_validate(...)` for reconstructed rows. `insert()` returns `cursor.rowcount == 1`.

- [ ] **Step 6: Run persistence test GREEN and full regression**

```bash
pytest tests/test_persistence.py -v
pytest -q
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add -- onejob/persistence tests/test_persistence.py
git commit -m "feat: add sqlite persistence foundation"
```

---

### Task 3: Provenance, Evidence Families, Identity, and Consensus

**Files:**
- Create: `onejob/provenance/__init__.py`
- Create: `onejob/provenance/lineage.py`
- Create: `onejob/provenance/evidence.py`
- Create: `onejob/ingestion/identity.py`
- Create: `onejob/ingestion/consensus.py`
- Test: `tests/test_evidence_lineage.py`
- Test: `tests/test_identity_consensus.py`

**Interfaces:**
- Consumes: `RawJobObservation`.
- Produces: `EvidenceRecord`, `ConsensusValue`, `SourceConflict`, `company_id_for()`, `job_identity_key()`, `identity_score()`, `build_field_evidence()`, `resolve_field_consensus()`.

- [ ] **Step 1: Write failing lineage test**

```python
from datetime import datetime, timezone
from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.provenance.evidence import build_field_evidence


def test_same_upstream_family_is_not_counted_as_independent():
    now = datetime.now(timezone.utc)
    a = RawJobObservation(observation_id="a", source_key="company-ats", source_type=SourceType.ATS,
        collector_version="1", external_id="x", source_url="https://ats/x", observed_at=now,
        title="Operator", company_name="Example", location_text="Bekasi", description="Operate machines",
        source_payload_hash="1")
    b = a.model_copy(update={"observation_id":"b", "source_key":"linkedin", "source_url":"https://linkedin/x", "source_payload_hash":"2"})
    evidence = build_field_evidence("job-1", [a, b], upstream_family={"linkedin":"company-ats"})
    title_evidence = [e for e in evidence if e.field_name == "title"]
    assert len({e.evidence_family_id for e in title_evidence}) == 1
```

- [ ] **Step 2: Write failing consensus test**

```python
from onejob.ingestion.consensus import resolve_field_consensus


def test_official_current_evidence_wins_salary_but_conflict_is_retained():
    evidence = [
        {"evidence_id":"ats", "value": [6500000, 8000000], "confidence":0.98, "evidence_family_id":"ats"},
        {"evidence_id":"portal", "value": [5000000, 7000000], "confidence":0.78, "evidence_family_id":"portal"},
    ]
    result = resolve_field_consensus("salary", evidence)
    assert result.selected_value == [6500000, 8000000]
    assert result.conflicting_evidence_ids == ["portal"]
    assert result.confidence >= 0.90
```

- [ ] **Step 3: Verify RED**

```bash
pytest tests/test_evidence_lineage.py tests/test_identity_consensus.py -v
```

- [ ] **Step 4: Implement deterministic identity functions**

`company_id_for(display_name)` uses the same company normalization behavior as V1 and SHA-1 prefix `cmp-<16hex>`. `job_identity_key(company_id, normalized_title, normalized_location)` returns `job-<16hex>`. `identity_score()` returns `1.0` for matching external requisition identities, otherwise weighted deterministic agreement over company/title/location/description.

- [ ] **Step 5: Implement evidence models and lineage**

`EvidenceRecord` fields: `evidence_id`, `canonical_job_id`, `observation_id`, `field_name`, `value`, `value_fingerprint`, `evidence_family_id`, `independence_status`, `observed_at`, `confidence`.

`build_field_evidence()` emits at minimum evidence for `title`, `company`, `location`, `description`, `salary`, `published_at`, and `active_status`. If `upstream_family[source_key]` exists, derive the family from that upstream key; otherwise default to `source_key` and set `independence_status="independence_unknown"` for non-canonical mirrors.

- [ ] **Step 6: Implement consensus arbitration**

Rules for V2.0:
1. sort by confidence descending;
2. do not increase confidence merely because multiple rows share one `evidence_family_id`;
3. select highest-confidence value;
4. every materially different non-null value becomes conflict evidence;
5. selected confidence is capped at `0.99`;
6. exact agreement from a second independent family adds `0.04`, capped at `0.99`;
7. disagreement subtracts `0.04` per independent conflicting family, floor `0.10`.

- [ ] **Step 7: Run targeted and regression tests**

```bash
pytest tests/test_evidence_lineage.py tests/test_identity_consensus.py -v
pytest -q
```

- [ ] **Step 8: Commit**

```bash
git add -- onejob/provenance onejob/ingestion/identity.py onejob/ingestion/consensus.py tests/test_evidence_lineage.py tests/test_identity_consensus.py
git commit -m "feat: add provenance identity and consensus"
```

---

### Task 4: Temporal Versions, Events, Lifecycle, and Source Health

**Files:**
- Create: `onejob/ingestion/lifecycle.py`
- Create: `onejob/source_health.py`
- Extend: `onejob/ingestion/models.py`
- Extend: `onejob/persistence/repositories.py`
- Test: `tests/test_version_lifecycle.py`

**Interfaces:**
- Produces: `JobLifecycleState`, `JobEventType`, `JobVersion`, `JobEvent`, `material_snapshot()`, `diff_material_fields()`, `next_lifecycle_state()`, `SourceHealthStatus`, `transition_source_health()`.

- [ ] **Step 1: Write failing version/lifecycle tests**

```python
from onejob.ingestion.lifecycle import diff_material_fields, next_lifecycle_state
from onejob.ingestion.models import JobLifecycleState


def test_salary_change_creates_material_diff():
    old = {"title":"Operator", "salary_min":5500000, "salary_max":6500000}
    new = {"title":"Operator", "salary_min":6000000, "salary_max":7000000}
    assert diff_material_fields(old, new) == ["salary_max", "salary_min"]


def test_reappearance_after_closed_is_reopened():
    assert next_lifecycle_state(JobLifecycleState.CLOSED, observed_now=True, materially_changed=False) == JobLifecycleState.REOPENED
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_version_lifecycle.py -v
```

- [ ] **Step 3: Implement lifecycle enums and pure transition logic**

Rules:
- first canonical observation -> `DISCOVERED` event then persisted state `ACTIVE`;
- current observation, no material diff -> `ACTIVE` + `JOB_SEEN`;
- material diff -> `UPDATED` + `JOB_CHANGED` then current state remains `UPDATED` until a subsequent unchanged observation returns it to `ACTIVE`;
- observed after `CLOSED` -> `REOPENED` + `JOB_REOPENED`;
- temporary collector failure never produces `CLOSED`;
- stale inference uses a supplied `now` and threshold; no wall-clock reads inside pure tests.

- [ ] **Step 4: Implement source-health transitions**

`HEALTHY`, `DEGRADED`, `RATE_LIMITED`, `BROKEN`, `DISABLED`, `UNKNOWN`.

Rules:
- successful complete batch -> `HEALTHY`, consecutive failures `0`;
- partial/parsing warnings -> `DEGRADED`;
- 429/rate limited -> `RATE_LIMITED`;
- failed batch increments failures; third consecutive non-rate-limit failure -> `BROKEN`, earlier failures -> `DEGRADED`;
- first success after a degraded/broken state emits recovery state `HEALTHY`.

- [ ] **Step 5: Implement job version/history repository operations**

`JobHistoryRepository` methods:
- `latest_version(conn, canonical_job_id) -> JobVersion | None`
- `append_version(conn, version: JobVersion) -> None`
- `close_previous_version(conn, canonical_job_id, valid_to) -> None`
- `append_event(conn, event: JobEvent) -> None`
- `list_versions(conn, canonical_job_id) -> list[JobVersion]`
- `list_events(conn, canonical_job_id) -> list[JobEvent]`

- [ ] **Step 6: Run GREEN + regression**

```bash
pytest tests/test_version_lifecycle.py -v
pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add -- onejob/ingestion/models.py onejob/ingestion/lifecycle.py onejob/source_health.py onejob/persistence/repositories.py tests/test_version_lifecycle.py
git commit -m "feat: add temporal job lifecycle and source health"
```

---

### Task 5: ATS Connectors with Injected HTTP Clients

**Files:**
- Create: `onejob/collectors/greenhouse.py`
- Create: `onejob/collectors/lever.py`
- Create: `onejob/collectors/ashby.py`
- Create fixtures: `tests/fixtures/greenhouse_jobs.json`, `tests/fixtures/lever_jobs.json`, `tests/fixtures/ashby_jobs.json`
- Test: `tests/test_collectors_greenhouse.py`
- Test: `tests/test_collectors_lever.py`
- Test: `tests/test_collectors_ashby.py`

**Interfaces:**
- Consumes: `Collector`, `CollectionTarget`, `CollectionBatch`, `RawJobObservation`.
- Each connector constructor accepts `http_client` with `.get(url, **kwargs)` so tests never call live networks.
- Each connector returns `CollectionBatch`; malformed individual entries are skipped with a warning rather than aborting valid observations.

- [ ] **Step 1: Add one deterministic fixture and failing parser test per connector**

Example Greenhouse test:

```python
import json
from pathlib import Path
from onejob.collectors.base import CollectionTarget
from onejob.collectors.greenhouse import GreenhouseCollector


class FixtureResponse:
    def __init__(self, payload): self._payload = payload; self.status_code = 200
    def json(self): return self._payload
    def raise_for_status(self): return None

class FixtureClient:
    def __init__(self, payload): self.payload = payload
    def get(self, *args, **kwargs): return FixtureResponse(self.payload)


def test_greenhouse_maps_payload_to_universal_observation():
    payload = json.loads(Path("tests/fixtures/greenhouse_jobs.json").read_text())
    batch = GreenhouseCollector(FixtureClient(payload)).collect(CollectionTarget(tenant="example"))
    assert batch.status.value == "SUCCESS"
    assert batch.observations[0].source_type.value == "ats"
    assert batch.observations[0].external_id == "1001"
    assert batch.observations[0].company_name == "Example"
```

Equivalent tests must assert Lever and Ashby produce the same universal fields from their own source shapes.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_collectors_greenhouse.py tests/test_collectors_lever.py tests/test_collectors_ashby.py -v
```

- [ ] **Step 3: Implement payload hashing**

Use canonical JSON serialization:

```python
payload_bytes = json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
source_payload_hash = hashlib.sha256(payload_bytes).hexdigest()
```

Observation IDs use stable source/external/payload identity:

```python
sha256(f"{source_key}|{external_id}|{source_payload_hash}".encode()).hexdigest()
```

- [ ] **Step 4: Implement Greenhouse, Lever, and Ashby mappers**

All source-specific date parsing stays inside the connector. HTML descriptions are converted to plain text with a minimal safe standard-library stripper or an explicitly added dependency only if its need is justified by tests. The core never imports ATS-specific schemas.

- [ ] **Step 5: Test malformed-entry isolation**

For each connector include one fixture entry missing `id` or `title`; assert the batch remains `PARTIAL`, valid observations remain present, and warnings identify the skipped entry without exposing raw HTML.

- [ ] **Step 6: Run targeted + full regression**

```bash
pytest tests/test_collectors_greenhouse.py tests/test_collectors_lever.py tests/test_collectors_ashby.py -v
pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add -- onejob/collectors/greenhouse.py onejob/collectors/lever.py onejob/collectors/ashby.py tests/fixtures tests/test_collectors_greenhouse.py tests/test_collectors_lever.py tests/test_collectors_ashby.py
git commit -m "feat: add structured ATS collectors"
```

---

### Task 6: Collection + Canonicalization Pipeline

**Files:**
- Create: `onejob/ingestion/pipeline.py`
- Extend: `onejob/persistence/repositories.py`
- Test: `tests/test_ingestion_pipeline.py`

**Interfaces:**
- Produces: `IngestionPipeline.collect_one(collector, target) -> CollectionRunSummary` and `collect_many(requests) -> list[CollectionRunSummary]`.
- One source transaction persists observations, evidence, consensus, canonical job/source links, versions, events, source state, and run counters atomically.

- [ ] **Step 1: Write failing repeated-collection integration test**

```python

def test_repeated_same_collection_does_not_duplicate_job_or_material_version(tmp_path, fixture_collector):
    pipeline = make_pipeline(tmp_path)
    first = pipeline.collect_one(fixture_collector, CollectionTarget(tenant="example"))
    second = pipeline.collect_one(fixture_collector, CollectionTarget(tenant="example"))
    assert first.new_count == 1
    assert second.new_count == 0
    assert second.unchanged_count == 1
    assert pipeline.jobs.count() == 1
    assert len(pipeline.history.list_versions(first.canonical_job_ids[0])) == 1
    assert [e.event_type for e in pipeline.history.list_events(first.canonical_job_ids[0])][-1] == "JOB_SEEN"
```

- [ ] **Step 2: Write failing material-change test**

Same source/external job returns a changed salary/description payload on the second collection; assert exactly one canonical job, two versions, `changed_count == 1`, and final event `JOB_CHANGED`.

- [ ] **Step 3: Verify RED**

```bash
pytest tests/test_ingestion_pipeline.py -v
```

- [ ] **Step 4: Implement pipeline transaction**

For each valid observation:
1. upsert source profile;
2. insert immutable observation if new;
3. resolve company ID;
4. calculate candidate canonical identity;
5. create or load canonical job;
6. link observation to canonical job;
7. build/persist field evidence;
8. resolve/persist field consensus and conflicts;
9. build material canonical snapshot;
10. compare with latest version;
11. append version/event only when required;
12. update canonical current row and `last_seen_at`;
13. update collection counters.

Any exception in steps 2–12 rolls back that source batch transaction and records the collection run failure separately; it must not mutate previous history.

- [ ] **Step 5: Implement `collect_many` failure isolation**

`collect_many` loops collectors independently. A failed collector yields a failed summary and source-health update; later collectors still execute.

- [ ] **Step 6: Test cross-source merge**

Two independent fixture collectors emit same company/title/location with similar description but distinct source IDs; assert one canonical job, two `canonical_job_sources`, evidence from two families, and consensus confidence reflects corroboration.

- [ ] **Step 7: Run integration + regression**

```bash
pytest tests/test_ingestion_pipeline.py -v
pytest -q
```

- [ ] **Step 8: Commit**

```bash
git add -- onejob/ingestion/pipeline.py onejob/persistence/repositories.py tests/test_ingestion_pipeline.py
git commit -m "feat: add persistent canonicalization pipeline"
```

---

### Task 7: Persisted Service Compatibility and Temporal Trust Inputs

**Files:**
- Modify: `onejob/models.py`
- Modify: `onejob/service.py`
- Modify: `onejob/trust.py`
- Modify: `onejob/repository.py`
- Test: `tests/test_service_persisted.py`
- Update regression tests only where constructor injection is needed; public V1 response fields stay compatible.

**Interfaces:**
- `OneJobService.persisted(db: Database, profile_repo: DemoRepository | ProfileRepository)` creates service over persistent canonical jobs.
- Existing `OneJobService.demo()` remains functional.
- Existing `list_jobs()`, `get_job()`, `suggest_answer()`, `profile_view()` signatures remain.

- [ ] **Step 1: Write failing persisted-service test**

```python

def test_persisted_service_runs_existing_matching_policy_trust_and_decision(tmp_path, seeded_pipeline):
    service = OneJobService.persisted(seeded_pipeline.db, seeded_pipeline.profile_repo)
    jobs = service.list_jobs()
    assert jobs
    assert {"match_score", "trust_score", "decision", "sources"} <= jobs[0].keys()
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_service_persisted.py -v
```

- [ ] **Step 3: Extend `CanonicalJob` compatibly**

Add optional/defaulted fields so V1 callers do not break:

```python
lifecycle_state: str = "ACTIVE"
first_seen_at: datetime | None = None
last_seen_at: datetime | None = None
active_status_confidence: float = 1.0
independent_evidence_families: int = 1
field_conflicts: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Map persisted canonical rows to `CanonicalJob`**

`JobRepository.list_canonical()` and `get_canonical()` reconstruct the existing domain model, including all linked sources. The matching/answer engines remain unchanged.

- [ ] **Step 5: Add temporal/provenance trust signals without categorical accusations**

Rules layered on top of V1 trust:
- current official/canonical evidence: positive reason;
- >=2 independent evidence families: positive reason;
- `STALE` or `CLOSED`: risk reason and score penalty;
- unresolved high-value field conflicts: small penalty and explanation;
- degraded/broken source alone is not a hard block;
- existing payment request remains hard block.

- [ ] **Step 6: Run persisted test + all V1 tests**

```bash
pytest tests/test_service_persisted.py -v
pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add -- onejob/models.py onejob/repository.py onejob/service.py onejob/trust.py tests/test_service_persisted.py tests
git commit -m "feat: serve persisted temporal jobs through domain engine"
```

---

### Task 8: V2 API and CLI Surfaces

**Files:**
- Modify: `onejob/api.py`
- Modify: `onejob/cli.py`
- Test: `tests/test_api_v2.py`
- Test: `tests/test_cli_v2.py`

**Interfaces:**
- New API: `GET /api/sources`, `GET /api/sources/{source_key}`, `POST /api/collect`, `GET /api/collections/{run_id}`, `GET /api/jobs/{job_id}/history`, `GET /api/jobs/{job_id}/evidence`, `GET /api/jobs/{job_id}/conflicts`.
- New CLI: `collect`, `sources`, `source`, `history`, `evidence`.

- [ ] **Step 1: Write failing API tests**

```python

def test_sources_and_job_history_endpoints(v2_client, seeded_job_id):
    sources = v2_client.get("/api/sources")
    assert sources.status_code == 200
    history = v2_client.get(f"/api/jobs/{seeded_job_id}/history")
    assert history.status_code == 200
    assert "versions" in history.json()
    assert "events" in history.json()
```

`POST /api/collect` test injects fixture collectors into an application factory; it must never hit a live network during tests.

- [ ] **Step 2: Refactor API module to an application factory before adding routes**

```python
def create_app(service=None, collection_service=None) -> FastAPI:
    ...

app = create_app()
```

The default app uses the configured local database when present and may fall back to demo mode only when explicitly configured for demo/development.

- [ ] **Step 3: Implement route handlers with sanitized errors**

404 for unknown jobs/sources/runs. Collection errors return run status/details without raw response bodies or credentials.

- [ ] **Step 4: Write failing CLI tests around `main(argv=None)`**

Refactor:

```python
def main(argv=None):
    args = parser.parse_args(argv)
    return args.func(args)
```

Then test `main(["sources"])`, `main(["history", job_id])`, and a fixture-backed `collect` command through injected service factory or monkeypatched constructor.

- [ ] **Step 5: Implement concise V2 CLI output**

`collect` output prints checked sources, raw observations, new, canonical, merged, changed, closed, and warnings from actual run summaries. Never hard-code illustrative numbers from the spec.

- [ ] **Step 6: Run API/CLI tests + full regression**

```bash
pytest tests/test_api_v2.py tests/test_cli_v2.py -v
pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add -- onejob/api.py onejob/cli.py tests/test_api_v2.py tests/test_cli_v2.py
git commit -m "feat: expose collection provenance and history APIs"
```

---

### Task 9: End-to-End Verification and Termux Documentation

**Files:**
- Modify: `README.md`
- Modify: `requirements.txt` only if implementation added an explicitly justified runtime dependency.
- Test: all tests.

**Interfaces:**
- Documents one local SQLite workflow and fixture/offline verification workflow.
- Does not claim LinkedIn/JobStreet/Indeed live coverage in V2.0.

- [ ] **Step 1: Run the full suite from a clean temporary DB**

```bash
pytest -q
```
Expected: zero failures.

- [ ] **Step 2: Run database initialization smoke test**

```bash
python - <<'PY'
from tempfile import TemporaryDirectory
from pathlib import Path
from onejob.persistence.db import Database
with TemporaryDirectory() as d:
    db = Database(Path(d) / "gaweyuk.db")
    db.initialize()
    print("sqlite-ok")
PY
```
Expected: `sqlite-ok`.

- [ ] **Step 3: Run fixture-backed ingestion smoke test**

Provide a checked-in or test utility command that runs one connector fixture through `IngestionPipeline` and prints a nonzero canonical job count without internet access. This is the reproducible Termux verification path.

- [ ] **Step 4: Run API smoke test**

```bash
python -m uvicorn onejob.api:app --host 127.0.0.1 --port 8000
```
In a second shell:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/sources
```
Expected: health JSON and valid source JSON.

- [ ] **Step 5: Update README with exact Termux commands**

Document:

```bash
pkg install python git -y
pip install -r requirements.txt
export GAWEYUK_DB="$HOME/.gaweyuk/gaweyuk.db"
python -m onejob.cli sources
python -m onejob.cli collect
python -m onejob.cli jobs
uvicorn onejob.api:app --host 0.0.0.0 --port 8000
```

Also document that actual connector targets/tenants must be configured; secrets never belong in the repo.

- [ ] **Step 6: Review spec coverage**

Confirm evidence exists for all V2.0 success criteria:
- persistence;
- three structured collectors;
- repeated collection idempotence;
- material versions;
- cross-source merge with retained lineage;
- visible conflicts/confidence;
- source health;
- lifecycle/history;
- domain compatibility;
- API/CLI surfaces;
- green full suite;
- failed collection preserves prior history.

- [ ] **Step 7: Commit final docs**

```bash
git add -- README.md requirements.txt
git commit -m "docs: add GaweYuk V2 Termux workflow"
```

---

## Plan Self-Review Result

- **Spec coverage:** Tasks 1–9 cover every V2.0 success criterion in section 37 of the approved spec. Portal live scraping, auto-apply, ML fraud, forecasting, and multi-user auth remain explicit non-goals.
- **Placeholder scan:** No implementation step relies on `TBD`, `TODO`, “implement later”, or an undefined behavior requirement. Deferred milestones are named non-goals rather than placeholders.
- **Type consistency:** `RawJobObservation`, `CollectionTarget`, `CollectionBatch`, repository names, lifecycle/version/event names, and service/API/CLI contracts are consistent across tasks.
- **Isolation:** Collectors depend on universal ingestion models only; matching/trust/answer/decision do not import ATS source schemas.
- **Safety:** No arbitrary URL collector, credential storage, or auto-submit behavior is introduced.

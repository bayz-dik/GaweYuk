# GaweYuk Slice 4A — Job Source & Verification Network Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn GaweYuk's existing collector/ingestion MVP into a production-oriented, evidence-first job source and verification network where source discovery never equals publication, only publishable jobs reach the public catalog, and every trust/publication outcome is auditable.

**Architecture:** Extend the existing `collectors/` and `ingestion/` foundations rather than replacing them. Data flows one way: source registry/adapters → immutable observations/provenance → canonicalization and company identity → verification snapshots using the existing Trust Engine → publication decision → public catalog, with review/quarantine/rejection kept outside the public boundary. SQLite remains the transaction owner; repositories remain stateless and receive caller-owned `sqlite3.Connection` objects.

**Tech Stack:** Python 3.x, FastAPI, Pydantic v2, SQLite, pytest, httpx/FastAPI TestClient, existing GaweYuk Trust Engine and ingestion primitives.

**Spec:** `docs/superpowers/specs/2026-08-21-gaweyuk-slice-4a-job-source-verification-network-design.md`

## Global Constraints

- Architecture is **Indonesia-first, global-ready**; core contracts must not hard-code Indonesia.
- `COLLECTED != TRUSTED`; adapters observe and never self-declare a job verified.
- `CanonicalJob exists != user can see it`; canonical storage and publication authority are separate.
- `ListingLifecycle != PublicationState`; `ACTIVE` is never permission to publish.
- Public catalog endpoints return only currently `PUBLISHABLE` jobs.
- Tier 3 discovery sources start in shadow and cannot self-authorize publication.
- A single authoritative Tier 1 source may be sufficient when company identity, destination, freshness, and Trust Engine evidence satisfy policy.
- Raw source count is never treated as independent evidence count; evidence-family lineage is first-class.
- Dedup resolution is three-way: `SAME`, `DISTINCT`, `AMBIGUOUS`; ambiguous identity never silently merges.
- `UNKNOWN` is first-class and is never silently converted to safe/verified.
- Confirmed hard-risk conditions such as recruitment payment, credential harvesting, confirmed impersonation, or malicious apply destination cannot be cleared by AI.
- AI may summarize or propose signals; AI may not create official company relationships, clear hard gates, or publish jobs.
- Verification snapshots and publication decisions are immutable; changed inputs create a new snapshot/decision.
- Verification/system failure fails closed for publication while preserving already-committed raw evidence.
- Official closure evidence withdraws a job from active catalog visibility without deleting history.
- Source acquisition methods are explicit; unsupported/unknown acquisition policy does not become enabled merely to increase coverage.
- External fetches must enforce SSRF protection and safe redirect handling.
- Secrets, raw credentials, reviewer-only notes, and raw evidence payloads must never appear in public catalog responses.
- Reviewer commands require authorization, idempotency, and optimistic/stale-context protection.
- Existing `/api/jobs`, Career Twin, Career Intent, Career Targets, Career Context, Trust Engine, and existing collector behavior must remain regression-safe unless this plan explicitly changes a boundary.
- Existing Greenhouse, Lever, and Ashby collectors are the first shadow-compatible adapters; do not rewrite them unnecessarily.
- The current migration sequence ends at `006_career_intent_context.sql`; Slice 4A uses `007_job_source_verification_network.sql`.
- TDD is mandatory: red test → minimal implementation → focused green test → relevant regression → commit.
- Anti-Slop mode is **DURING**. For 4A specifically, apply `antislop` + `antislop-code`; UI/copy/mobile skills are installed for later product slices but 4A must not invent UI or `DESIGN.md`.
- Do not add generic “enterprise” abstractions, empty service layers, decorative comments, fake metrics, or speculative dependencies.
- Do not introduce Kafka, Celery, Redis, PostgreSQL, a browser automation stack, or a new ML dependency in Slice 4A.
- Do not silently fall back to legacy/public job behavior after a contextual verification pipeline failure.
- Fresh completion claims require a fresh full-suite run, `git diff --check`, and clean working tree.

---

## Locked File Structure

Create or evolve these units. Keep each file focused on one authority.

```text
AGENTS.md
antislop.md
skills/
├── antislop/SKILL.md
├── antislop-code/SKILL.md
├── antislop-copywriting/SKILL.md
├── antislop-human/SKILL.md
├── antislop-human/contrast-check.py
├── antislop-human/contrast-mcp.py
├── antislop-layoutmobile/SKILL.md
└── antislop-ui/SKILL.md

onejob/
├── collectors/
│   ├── base.py                         # shared collector contract
│   ├── greenhouse.py                  # existing adapter
│   ├── lever.py                       # existing adapter
│   └── ashby.py                       # existing adapter
├── ingestion/
│   ├── models.py                       # raw observation + lifecycle models
│   ├── provenance.py                   # source appearance/evidence-family derivation
│   ├── entity_resolution.py            # tri-state canonical job resolution
│   ├── evidence_store.py               # field evidence persistence/consensus input
│   ├── consensus.py                    # evidence-family-aware field consensus
│   ├── lifecycle.py                    # listing lifecycle transitions
│   └── pipeline.py                     # observation/canonicalization transaction only
├── job_sources/
│   ├── __init__.py
│   ├── models.py                       # registry/policy/rollout/health domain types
│   ├── repository.py                   # stateless source persistence
│   ├── policy.py                       # acquisition + rollout eligibility
│   ├── health.py                       # health transitions/circuit breaker
│   └── service.py                      # registry command/query orchestration
├── company_identity/
│   ├── __init__.py
│   ├── models.py                       # graph node/relationship/snapshot types
│   ├── repository.py                   # graph persistence
│   └── resolver.py                     # deterministic identity resolution
├── job_verification/
│   ├── __init__.py
│   ├── models.py                       # snapshot/publication/review/freshness types
│   ├── destination.py                  # apply URL/redirect/domain safety
│   ├── corroboration.py                # independent-family evidence summary
│   ├── freshness.py                    # validity/reverification calculations
│   ├── repository.py                   # immutable verification/publication persistence
│   ├── policy.py                       # publication decision matrix
│   ├── review.py                       # review commands + stale-context protection
│   ├── service.py                      # verification orchestrator / Trust Engine bridge
│   └── reverification.py               # persistent due-work runner
├── catalog/
│   ├── __init__.py
│   ├── models.py                       # public-safe response models
│   ├── repository.py                   # PUBLISHABLE-only queries
│   ├── service.py                      # catalog read boundary
│   └── api.py                          # public catalog router
├── persistence/
│   └── migrations/
│       └── 007_job_source_verification_network.sql
└── api.py                               # mount new catalog/internal routers safely

tests/
├── test_job_source_registry.py
├── test_collector_contract.py
├── test_ingestion_provenance.py
├── test_company_identity_graph.py
├── test_job_entity_resolution.py
├── test_evidence_authority.py
├── test_apply_destination.py
├── test_job_verification_service.py
├── test_publication_policy.py
├── test_verification_review.py
├── test_reverification.py
├── test_catalog_api.py
├── test_job_source_security.py
├── test_job_source_failures.py
├── test_slice4a_acceptance.py
└── security_cases/
    └── job_source_verification_cases.json
```

Do not split a file further unless it grows beyond a single clear responsibility during implementation. Do not move existing unrelated code.

---

### Task 0: Preflight, branch, approved docs, and Anti-Slop routing

**Files:**
- Add: `docs/superpowers/specs/2026-08-21-gaweyuk-slice-4a-job-source-verification-network-design.md`
- Add: `docs/superpowers/plans/2026-08-21-gaweyuk-slice-4a-job-source-verification-network.md`
- Create or append: `AGENTS.md`
- Add: `antislop.md`
- Add: `skills/antislop/SKILL.md`
- Add: `skills/antislop-ui/SKILL.md`
- Add: `skills/antislop-copywriting/SKILL.md`
- Add: `skills/antislop-human/SKILL.md`
- Add: `skills/antislop-human/contrast-check.py`
- Add: `skills/antislop-human/contrast-mcp.py`
- Add: `skills/antislop-layoutmobile/SKILL.md`
- Add: `skills/antislop-code/SKILL.md`

**Interfaces:**
- Consumes: merged `main` after Career Twin v2 Slice 3, expected fresh baseline `513 passed, 1 warning`.
- Produces: branch `feature/job-source-verification-network-4a`, committed approved design/plan, repository-local Anti-Slop routing for subsequent sessions.
- Preconditions: the approved spec and this plan are present in their target `docs/superpowers/...` paths before execution; the user-supplied `anti-slop-3.1.3.zip` is available locally and must not be downloaded by the agent.

- [ ] **Step 1: Verify baseline and allowed untracked files**

Run:

```bash
git switch main
git pull --ff-only
git status --short
python -m pytest -q
git diff --check
```

Expected:
- current branch is `main`;
- test suite exits 0; baseline should be 513 passing tests unless newer approved work legitimately increased it;
- `git diff --check` prints nothing;
- no unrelated modified files.

If unrelated changes exist, stop instead of stashing/deleting them.

- [ ] **Step 2: Create the feature branch**

Run:

```bash
git switch -c feature/job-source-verification-network-4a
```

Expected: branch creation succeeds from current `main`.

- [ ] **Step 3: Install the user-supplied Anti-Slop release without network access**

Resolve the local archive explicitly:

```bash
ANTISLOP_ZIP="$(find . /root /sdcard/Download /storage/emulated/0/Download \
  -maxdepth 3 -type f -name 'anti-slop-3.1.3*.zip' 2>/dev/null | head -n 1)"
test -n "$ANTISLOP_ZIP"
rm -rf .tmp-antislop
mkdir -p .tmp-antislop
unzip -q "$ANTISLOP_ZIP" -d .tmp-antislop
test -f .tmp-antislop/anti-slop-3.1.3/antislop.md
```

If `test -n "$ANTISLOP_ZIP"` fails, stop and ask the user to place their already-provided archive locally. Do not download a replacement.

Copy the approved release:

```bash
cp .tmp-antislop/anti-slop-3.1.3/antislop.md ./antislop.md
mkdir -p skills
cp -R .tmp-antislop/anti-slop-3.1.3/skills/antislop skills/
cp -R .tmp-antislop/anti-slop-3.1.3/skills/antislop-ui skills/
cp -R .tmp-antislop/anti-slop-3.1.3/skills/antislop-copywriting skills/
cp -R .tmp-antislop/anti-slop-3.1.3/skills/antislop-human skills/
cp -R .tmp-antislop/anti-slop-3.1.3/skills/antislop-layoutmobile skills/
cp -R .tmp-antislop/anti-slop-3.1.3/skills/antislop-code skills/
rm -rf .tmp-antislop
```

- [ ] **Step 4: Add the Anti-Slop pointer block without overwriting existing agent instructions**

If `AGENTS.md` does not exist, create it. Append exactly one marked block:

```md
<!-- antislop:start -->
## antislop
For UI, copy, people, mobile layout, or code comments work, read `antislop.md` (core) and then the skill for the task:
- UI / visual: `skills/antislop-ui/SKILL.md`
- Copy & text: `skills/antislop-copywriting/SKILL.md`
- People: `skills/antislop-human/SKILL.md`
- Mobile / responsive: `skills/antislop-layoutmobile/SKILL.md`
- Code comments: `skills/antislop-code/SKILL.md`
The project owner selected Anti-Slop mode **DURING** for this work.
<!-- antislop:end -->
```

Before appending, verify no `<!-- antislop:start -->` block already exists. If it exists, replace only that block; preserve all unrelated `AGENTS.md` content.

- [ ] **Step 5: Verify the approved docs and Anti-Slop files are complete**

Run:

```bash
test -s docs/superpowers/specs/2026-08-21-gaweyuk-slice-4a-job-source-verification-network-design.md
test -s docs/superpowers/plans/2026-08-21-gaweyuk-slice-4a-job-source-verification-network.md
test -s antislop.md
test -s skills/antislop/SKILL.md
test -s skills/antislop-code/SKILL.md
grep -q '<!-- antislop:start -->' AGENTS.md
grep -q 'DURING' AGENTS.md
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit only the approved docs/routing**

Run:

```bash
git add \
  AGENTS.md \
  antislop.md \
  skills/antislop \
  skills/antislop-ui \
  skills/antislop-copywriting \
  skills/antislop-human \
  skills/antislop-layoutmobile \
  skills/antislop-code \
  docs/superpowers/specs/2026-08-21-gaweyuk-slice-4a-job-source-verification-network-design.md \
  docs/superpowers/plans/2026-08-21-gaweyuk-slice-4a-job-source-verification-network.md

git diff --cached --check
git commit -m "docs: define Slice 4A verification network"
```

Expected: one focused docs/agent-routing commit; no unrelated files staged.

---

### Task 1: Source Registry domain model and migration

**Files:**
- Create: `onejob/job_sources/__init__.py`
- Create: `onejob/job_sources/models.py`
- Create: `onejob/job_sources/repository.py`
- Create: `onejob/persistence/migrations/007_job_source_verification_network.sql`
- Test: `tests/test_job_source_registry.py`

**Interfaces:**
- Consumes: existing `SourceType` from `onejob.ingestion.models`.
- Produces:
  - `SourceTrustTier`
  - `AcquisitionMethod`
  - `ComplianceStatus`
  - `SourceRolloutState`
  - `SourceHealthState`
  - `JobSource`
  - `SourceRepository.get_by_id(conn, source_id) -> JobSource | None`
  - `SourceRepository.get_by_key(conn, source_key) -> JobSource | None`
  - `SourceRepository.insert(conn, source: JobSource) -> None`
  - `SourceRepository.update_state(...)`
- Persistence: `job_sources` table and foundational Slice 4A tables created by migration `007`.

- [ ] **Step 1: Write failing enum/model tests**

Create `tests/test_job_source_registry.py` with:

```python
from datetime import datetime, timezone

import pytest

from onejob.ingestion.models import SourceType
from onejob.job_sources.models import (
    AcquisitionMethod,
    ComplianceStatus,
    JobSource,
    SourceHealthState,
    SourceRolloutState,
    SourceTrustTier,
)


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def test_job_source_has_explicit_policy_and_rollout_state():
    source = JobSource(
        source_id="src-greenhouse",
        source_key="greenhouse",
        source_type=SourceType.ATS,
        trust_tier=SourceTrustTier.TIER_1_OFFICIAL,
        acquisition_method=AcquisitionMethod.OFFICIAL_API,
        primary_domain="greenhouse.io",
        country_scope=(),
        compliance_status=ComplianceStatus.ALLOWED,
        rollout_state=SourceRolloutState.SHADOW,
        health_state=SourceHealthState.UNKNOWN,
        verification_policy_version="source-policy-v1",
        created_at=NOW,
        updated_at=NOW,
    )

    assert source.rollout_state is SourceRolloutState.SHADOW
    assert source.country_scope == ()


def test_job_source_rejects_active_when_compliance_is_unknown():
    with pytest.raises(ValueError, match="compliance"):
        JobSource(
            source_id="src-bad",
            source_key="bad",
            source_type=SourceType.OPEN_WEB,
            trust_tier=SourceTrustTier.TIER_3_DISCOVERY,
            acquisition_method=AcquisitionMethod.PERMITTED_HTML,
            primary_domain="example.test",
            country_scope=("ID",),
            compliance_status=ComplianceStatus.UNKNOWN,
            rollout_state=SourceRolloutState.ACTIVE,
            health_state=SourceHealthState.HEALTHY,
            verification_policy_version="source-policy-v1",
            created_at=NOW,
            updated_at=NOW,
        )
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```bash
python -m pytest tests/test_job_source_registry.py -q
```

Expected: import failure for `onejob.job_sources.models`.

- [ ] **Step 3: Implement the closed/versioned source domain types**

Create `onejob/job_sources/models.py`:

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from onejob.ingestion.models import SourceType


class SourceTrustTier(str, Enum):
    TIER_1_OFFICIAL = "TIER_1_OFFICIAL"
    TIER_2_AUTHORIZED = "TIER_2_AUTHORIZED"
    TIER_3_DISCOVERY = "TIER_3_DISCOVERY"


class AcquisitionMethod(str, Enum):
    OFFICIAL_API = "OFFICIAL_API"
    PARTNER_API = "PARTNER_API"
    PUBLIC_FEED = "PUBLIC_FEED"
    STRUCTURED_PUBLIC_PAGE = "STRUCTURED_PUBLIC_PAGE"
    PERMITTED_HTML = "PERMITTED_HTML"
    MANUAL_IMPORT = "MANUAL_IMPORT"
    USER_SUPPLIED = "USER_SUPPLIED"


class ComplianceStatus(str, Enum):
    ALLOWED = "ALLOWED"
    UNKNOWN = "UNKNOWN"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class SourceRolloutState(str, Enum):
    REGISTERED = "REGISTERED"
    SHADOW = "SHADOW"
    OBSERVED = "OBSERVED"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class SourceHealthState(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    DISABLED = "DISABLED"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class JobSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    source_key: str
    source_type: SourceType
    trust_tier: SourceTrustTier
    acquisition_method: AcquisitionMethod
    primary_domain: str | None = None
    country_scope: tuple[str, ...] = ()
    compliance_status: ComplianceStatus
    rollout_state: SourceRolloutState
    health_state: SourceHealthState
    verification_policy_version: str
    created_at: datetime
    updated_at: datetime

    @field_validator("country_scope")
    @classmethod
    def normalize_countries(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({country.upper() for country in value}))

    @model_validator(mode="after")
    def enforce_activation_policy(self):
        if (
            self.rollout_state is SourceRolloutState.ACTIVE
            and self.compliance_status is not ComplianceStatus.ALLOWED
        ):
            raise ValueError("ACTIVE source requires allowed compliance")
        return self
```

- [ ] **Step 4: Add migration tables**

Create `onejob/persistence/migrations/007_job_source_verification_network.sql` with the Slice 4A tables in dependency order. At minimum this migration must create:

```sql
CREATE TABLE job_sources (
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

CREATE TABLE job_source_state_events (
    event_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_state TEXT,
    new_state TEXT,
    reason_code TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY(source_id) REFERENCES job_sources(source_id)
);
```

Also reserve the rest of the 007 migration in this same file for later Task 3/4/8/9/10/11 tables. Add those later by editing this migration only while the feature branch is unmerged; do not create 008 for unfinished parts of the same Slice 4A migration.

- [ ] **Step 5: Implement stateless SourceRepository**

`onejob/job_sources/repository.py` must serialize `country_scope` as JSON and reconstruct `JobSource` via `model_validate`.

Required method skeleton:

```python
class SourceRepository:
    def insert(self, conn, source: JobSource) -> None: ...
    def get_by_id(self, conn, source_id: str) -> JobSource | None: ...
    def get_by_key(self, conn, source_key: str) -> JobSource | None: ...
    def list_all(self, conn) -> list[JobSource]: ...
    def update_state(
        self,
        conn,
        *,
        source_id: str,
        rollout_state: SourceRolloutState | None = None,
        health_state: SourceHealthState | None = None,
        updated_at: datetime,
    ) -> JobSource:
        ...
```

Do not store a database connection on the repository object.

- [ ] **Step 6: Add persistence round-trip test**

Add:

```python
def test_source_repository_round_trips(tmp_path):
    from onejob.job_sources.repository import SourceRepository
    from onejob.persistence.db import Database

    db = Database(tmp_path / "sources.db")
    db.initialize()
    repo = SourceRepository()

    source = JobSource(
        source_id="src-greenhouse",
        source_key="greenhouse",
        source_type=SourceType.ATS,
        trust_tier=SourceTrustTier.TIER_1_OFFICIAL,
        acquisition_method=AcquisitionMethod.OFFICIAL_API,
        primary_domain="greenhouse.io",
        country_scope=("ID", "SG"),
        compliance_status=ComplianceStatus.ALLOWED,
        rollout_state=SourceRolloutState.SHADOW,
        health_state=SourceHealthState.UNKNOWN,
        verification_policy_version="source-policy-v1",
        created_at=NOW,
        updated_at=NOW,
    )

    with db.transaction() as conn:
        repo.insert(conn, source)

    with db.connection() as conn:
        loaded = repo.get_by_key(conn, "greenhouse")

    assert loaded == source
```

- [ ] **Step 7: Run migration and model tests**

Run:

```bash
python -m pytest tests/test_job_source_registry.py -q
python -m pytest tests/test_persistence.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add \
  onejob/job_sources \
  onejob/persistence/migrations/007_job_source_verification_network.sql \
  tests/test_job_source_registry.py

git diff --cached --check
git commit -m "feat: add job source registry foundation"
```

---

### Task 2: Source acquisition policy, rollout state machine, and health circuit breaker

**Files:**
- Create: `onejob/job_sources/policy.py`
- Create: `onejob/job_sources/health.py`
- Create: `onejob/job_sources/service.py`
- Modify: `onejob/job_sources/models.py`
- Modify: `onejob/job_sources/repository.py`
- Test: `tests/test_job_source_registry.py`

**Interfaces:**
- Produces:
  - `SourcePolicyDecision`
  - `SourcePolicy.evaluate(source: JobSource) -> SourcePolicyDecision`
  - `SourceHealthSignal`
  - `SourceHealthEvaluator.evaluate(current, signal) -> SourceHealthState`
  - `JobSourceService.register(...)`
  - `JobSourceService.promote(...)`
  - `JobSourceService.record_health(...)`
- Invariant: no direct `REGISTERED -> ACTIVE`; compliance `UNKNOWN/POLICY_BLOCKED` never yields ingestion/publication eligibility.

- [ ] **Step 1: Add failing transition tests**

```python
def test_new_source_cannot_skip_shadow(tmp_path):
    from onejob.job_sources.service import InvalidSourceTransition

    service, source = _registered_source_service(tmp_path)

    with pytest.raises(InvalidSourceTransition):
        service.promote(
            source_id=source.source_id,
            expected_state=SourceRolloutState.REGISTERED,
            target_state=SourceRolloutState.ACTIVE,
            reason_code="manual_skip",
            now=NOW,
        )


def test_policy_blocked_source_is_never_collection_eligible():
    from onejob.job_sources.policy import SourcePolicy

    blocked = _source(
        compliance_status=ComplianceStatus.POLICY_BLOCKED,
        rollout_state=SourceRolloutState.POLICY_BLOCKED,
    )

    decision = SourcePolicy().evaluate(blocked)

    assert decision.collection_allowed is False
    assert decision.publication_evidence_allowed is False
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_job_source_registry.py -q
```

Expected: missing service/policy symbols.

- [ ] **Step 3: Implement deterministic policy and allowed rollout edges**

Define:

```python
ALLOWED_ROLLOUT_TRANSITIONS = {
    SourceRolloutState.REGISTERED: {SourceRolloutState.SHADOW},
    SourceRolloutState.SHADOW: {
        SourceRolloutState.OBSERVED,
        SourceRolloutState.DISABLED,
        SourceRolloutState.POLICY_BLOCKED,
    },
    SourceRolloutState.OBSERVED: {
        SourceRolloutState.VALIDATED,
        SourceRolloutState.SHADOW,
        SourceRolloutState.DISABLED,
    },
    SourceRolloutState.VALIDATED: {
        SourceRolloutState.ACTIVE,
        SourceRolloutState.SHADOW,
        SourceRolloutState.DISABLED,
    },
    SourceRolloutState.ACTIVE: {
        SourceRolloutState.SHADOW,
        SourceRolloutState.DISABLED,
        SourceRolloutState.POLICY_BLOCKED,
    },
    SourceRolloutState.DISABLED: {SourceRolloutState.SHADOW},
    SourceRolloutState.POLICY_BLOCKED: set(),
}
```

`SourcePolicyDecision` must expose:

```python
@dataclass(frozen=True)
class SourcePolicyDecision:
    collection_allowed: bool
    publication_evidence_allowed: bool
    reason_codes: tuple[str, ...]
```

Tier 3 in `SHADOW/OBSERVED/VALIDATED` may collect but `publication_evidence_allowed=False`.

- [ ] **Step 4: Implement health circuit-breaker semantics**

Define `SourceHealthSignal` values at least:

```python
SUCCESS
TRANSIENT_FAILURE
RATE_LIMIT
AUTH_FAILURE
SCHEMA_MISMATCH
POLICY_VIOLATION
```

Rules:
- `POLICY_VIOLATION -> POLICY_BLOCKED`
- `SCHEMA_MISMATCH -> SCHEMA_CHANGED`
- `RATE_LIMIT -> RATE_LIMITED`
- repeated transient failures may yield `DEGRADED`;
- one success after `RATE_LIMITED` may return `HEALTHY`;
- health never silently changes compliance status.

Keep retry counters in persisted source-health state/event rows, not module globals.

- [ ] **Step 5: Add stale expected-state protection**

`JobSourceService.promote` must require `expected_state`. If stored state differs, raise `StaleSourceState` and make no write.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_job_source_registry.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add \
  onejob/job_sources/models.py \
  onejob/job_sources/repository.py \
  onejob/job_sources/policy.py \
  onejob/job_sources/health.py \
  onejob/job_sources/service.py \
  tests/test_job_source_registry.py \
  onejob/persistence/migrations/007_job_source_verification_network.sql

git diff --cached --check
git commit -m "feat: add source rollout and health policy"
```

---

### Task 3: Shared collector contract and existing ATS adapters in shadow-compatible form

**Files:**
- Modify: `onejob/collectors/base.py`
- Modify: `onejob/collectors/greenhouse.py`
- Modify: `onejob/collectors/lever.py`
- Modify: `onejob/collectors/ashby.py`
- Modify: `onejob/ingestion/models.py`
- Test: `tests/test_collector_contract.py`
- Reuse fixtures: `tests/fixtures/greenhouse_jobs.json`, `lever_jobs.json`, `ashby_jobs.json`

**Interfaces:**
- Keeps `Collector.collect(target) -> CollectionBatch`.
- Adds `apply_url: str | None` to `RawJobObservation`.
- Adds adapter metadata:
  - `source_key`
  - `source_type`
  - `collector_version`
  - `acquisition_method`
- Collectors remain observation producers; they do not query source registry DB or Trust Engine.

- [ ] **Step 1: Write shared contract tests**

Create a parametrized test using existing fixture-backed transport seams. For every collector assert:

```python
def assert_observation_contract(observation):
    assert observation.observation_id
    assert observation.source_key
    assert observation.external_id
    assert observation.source_url.startswith(("http://", "https://"))
    assert observation.title.strip()
    assert observation.company_name.strip()
    assert observation.source_payload_hash
    assert observation.observed_at.tzinfo is not None
```

Also assert:
- `apply_url` is either `None` or HTTP(S);
- adapters do not expose `verified`, `trusted`, `publication_state`, or `trust_score` fields.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_collector_contract.py -q
```

Expected: failure because contract metadata/apply URL is incomplete.

- [ ] **Step 3: Extend `RawJobObservation` compatibly**

Add:

```python
apply_url: Optional[str] = None
```

Do not make source-registry persistence IDs required on the adapter model; registry resolution belongs to ingestion, not the external adapter.

- [ ] **Step 4: Add acquisition metadata to Collector protocol**

In `collectors/base.py`:

```python
from onejob.job_sources.models import AcquisitionMethod

class Collector(Protocol):
    source_key: str
    source_type: SourceType
    collector_version: str
    acquisition_method: AcquisitionMethod

    def collect(self, target: CollectionTarget) -> CollectionBatch: ...
```

Set existing ATS adapters to `AcquisitionMethod.OFFICIAL_API`.

- [ ] **Step 5: Map apply destinations without changing collector authority**

Greenhouse/Lever/Ashby collectors should map their canonical apply/job URLs into `apply_url` where fixture payloads support it. Do not perform trust checks inside adapter code.

- [ ] **Step 6: Run collector-specific and full collector tests**

```bash
python -m pytest tests/test_collector_contract.py -q
python -m pytest -q -k 'greenhouse or lever or ashby or collector'
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add \
  onejob/collectors/base.py \
  onejob/collectors/greenhouse.py \
  onejob/collectors/lever.py \
  onejob/collectors/ashby.py \
  onejob/ingestion/models.py \
  tests/test_collector_contract.py

git diff --cached --check
git commit -m "feat: standardize source adapter contract"
```

---

### Task 4: Immutable provenance, source appearances, and evidence-family lineage

**Files:**
- Create: `onejob/ingestion/provenance.py`
- Modify: `onejob/ingestion/evidence_store.py`
- Modify: `onejob/persistence/repositories.py`
- Modify: `onejob/persistence/migrations/007_job_source_verification_network.sql`
- Test: `tests/test_ingestion_provenance.py`

**Interfaces:**
- Produces:
  - `EvidenceFamily`
  - `JobSourceAppearance`
  - `derive_evidence_family_id(...) -> str`
  - `AppearanceRepository.upsert_seen(...) -> JobSourceAppearance`
- Invariant: multiple observations may update `last_seen_at/latest_observation_id` of an appearance but never rewrite raw observations.
- Lineage can explicitly mark mirrors as sharing one upstream family.

- [ ] **Step 1: Write failing provenance tests**

```python
def test_same_upstream_listing_reuses_evidence_family():
    first = derive_evidence_family_id(
        source_id="src-greenhouse",
        external_id="req-123",
        upstream_family_hint=None,
    )
    second = derive_evidence_family_id(
        source_id="src-greenhouse",
        external_id="req-123",
        upstream_family_hint=None,
    )

    assert first == second


def test_mirror_can_share_upstream_family():
    origin = derive_evidence_family_id(
        source_id="src-ats",
        external_id="123",
        upstream_family_hint=None,
    )
    mirror = derive_evidence_family_id(
        source_id="src-board",
        external_id="mirror-9",
        upstream_family_hint=origin,
    )

    assert mirror == origin
```

Add a DB test where two observations for the same source/external ID leave two immutable raw rows but one appearance with advanced `last_seen_at`.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_ingestion_provenance.py -q
```

- [ ] **Step 3: Add migration schema**

Add:

```sql
CREATE TABLE evidence_families (
    evidence_family_id TEXT PRIMARY KEY,
    origin_source_id TEXT NOT NULL,
    origin_external_id TEXT NOT NULL,
    lineage_kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(origin_source_id) REFERENCES job_sources(source_id)
);

CREATE TABLE job_source_appearances (
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
    FOREIGN KEY(source_id) REFERENCES job_sources(source_id),
    FOREIGN KEY(evidence_family_id) REFERENCES evidence_families(evidence_family_id),
    FOREIGN KEY(latest_observation_id) REFERENCES raw_job_observations(observation_id)
);
```

Add `source_id`, `evidence_family_id`, and `apply_url` columns to the raw observation persistence path through safe migration-compatible tables/columns. If SQLite column-add constraints make FK backfill unsafe, use a normalized `observation_provenance` table keyed by `observation_id` rather than destructive table rebuild.

- [ ] **Step 4: Replace type-only source confidence with registry-aware evidence metadata**

`EvidenceConsensusStore.record_observation` must receive source/evidence-family context explicitly:

```python
def record_observation(
    self,
    conn: sqlite3.Connection,
    canonical_job_id: str,
    observation: RawJobObservation,
    *,
    evidence_family_id: str,
    source_confidence: float,
) -> dict[str, ConsensusValue]:
    ...
```

Delete the assumption that `source_key:external_id` is always an independent family. Do not delete historical evidence.

- [ ] **Step 5: Run provenance + existing ingestion tests**

```bash
python -m pytest tests/test_ingestion_provenance.py -q
python -m pytest -q -k 'ingestion or evidence or consensus'
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add \
  onejob/ingestion/provenance.py \
  onejob/ingestion/evidence_store.py \
  onejob/persistence/repositories.py \
  onejob/persistence/migrations/007_job_source_verification_network.sql \
  tests/test_ingestion_provenance.py

git diff --cached --check
git commit -m "feat: preserve source appearance provenance"
```

---

### Task 5: Company Identity Graph and deterministic relationship resolution

**Files:**
- Create: `onejob/company_identity/__init__.py`
- Create: `onejob/company_identity/models.py`
- Create: `onejob/company_identity/repository.py`
- Create: `onejob/company_identity/resolver.py`
- Modify: `onejob/persistence/migrations/007_job_source_verification_network.sql`
- Test: `tests/test_company_identity_graph.py`

**Interfaces:**
- Produces:
  - `IdentityNodeType`
  - `IdentityRelationshipType`
  - `IdentityRelationshipStatus`
  - `CompanyIdentityResolutionState`
  - `IdentityNode`
  - `IdentityRelationship`
  - `CompanyIdentitySnapshot`
  - `CompanyIdentityResolver.resolve(...) -> CompanyIdentityResolution`
- Existing `companies.company_id` stays the stable company anchor.
- Name similarity alone cannot return `VERIFIED`.

- [ ] **Step 1: Write identity authority tests**

```python
def test_name_match_alone_is_not_verified():
    resolver = CompanyIdentityResolver()

    result = resolver.resolve(
        company_id="cmp-1",
        claimed_name="PT Contoh Indonesia",
        source_domain="contoh-careers.example",
        relationships=(),
    )

    assert result.state in {
        CompanyIdentityResolutionState.UNKNOWN,
        CompanyIdentityResolutionState.PROBABLE,
    }
    assert result.state is not CompanyIdentityResolutionState.VERIFIED


def test_verified_career_domain_relationship_can_verify_identity():
    relationship = IdentityRelationship(
        relationship_id="rel-1",
        company_id="cmp-1",
        node_id="node-careers",
        relationship_type=IdentityRelationshipType.CAREER_SITE_FOR,
        status=IdentityRelationshipStatus.VERIFIED,
        confidence=0.99,
        verification_method="MANUAL_EVIDENCE",
        evidence_refs=("evidence-1",),
        first_verified_at=NOW,
        last_verified_at=NOW,
    )

    result = CompanyIdentityResolver().resolve(
        company_id="cmp-1",
        claimed_name="PT Contoh Indonesia",
        source_domain="careers.contoh.co.id",
        relationships=(relationship,),
    )

    assert result.state is CompanyIdentityResolutionState.VERIFIED
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_company_identity_graph.py -q
```

- [ ] **Step 3: Implement immutable graph models**

Node types:

```python
COMPANY
DOMAIN
CAREER_DOMAIN
ATS_TENANT
BRAND
LEGAL_ENTITY
```

Relationship types:

```python
OWNED_BY
CAREER_SITE_FOR
ATS_FOR
BRAND_OF
SUBSIDIARY_OF
ALIAS_OF
```

Resolution states:

```python
VERIFIED
PROBABLE
AMBIGUOUS
CONFLICTING
UNKNOWN
```

Store confidence as `0.0..1.0`; reject out-of-range values.

- [ ] **Step 4: Add graph tables**

Add:

```sql
CREATE TABLE company_identity_nodes (...);
CREATE TABLE company_identity_relationships (...);
CREATE TABLE company_identity_snapshots (...);
```

Every relationship row must include evidence refs JSON, verification method, first/last verified timestamps, and status. Snapshot rows must be immutable and content-addressed.

- [ ] **Step 5: Implement deterministic resolver precedence**

Resolver precedence:
1. conflicting verified relationships -> `CONFLICTING`;
2. verified domain/ATS relationship for expected company -> `VERIFIED`;
3. strong but unverified relationship evidence -> `PROBABLE`;
4. close competing candidate companies -> `AMBIGUOUS`;
5. no relationship evidence -> `UNKNOWN`.

Do not call an LLM.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_company_identity_graph.py -q
```

- [ ] **Step 7: Commit**

```bash
git add \
  onejob/company_identity \
  onejob/persistence/migrations/007_job_source_verification_network.sql \
  tests/test_company_identity_graph.py

git diff --cached --check
git commit -m "feat: add company identity graph"
```

---

### Task 6: Three-way canonical job entity resolution

**Files:**
- Create: `onejob/ingestion/entity_resolution.py`
- Modify: `onejob/ingestion/pipeline.py`
- Keep compatibility: `onejob/ingestion/identity.py`
- Test: `tests/test_job_entity_resolution.py`

**Interfaces:**
- Produces:
  - `JobIdentityDisposition = SAME | DISTINCT | AMBIGUOUS`
  - `JobIdentityCandidate`
  - `JobIdentityDecision`
  - `JobEntityResolver.resolve(...) -> JobIdentityDecision`
- Strong keys (same verified company + authoritative requisition identity) outrank fuzzy similarity.
- Ambiguous result does not merge.

- [ ] **Step 1: Write RED tests for all three outcomes**

```python
def test_same_authoritative_requisition_is_same():
    decision = resolver.resolve(
        incoming=_candidate(
            company_id="cmp-1",
            source_id="src-ats",
            external_id="req-7",
            authoritative_external_id=True,
        ),
        existing=(
            _candidate(
                canonical_job_id="job-1",
                company_id="cmp-1",
                source_id="src-ats",
                external_id="req-7",
                authoritative_external_id=True,
            ),
        ),
    )

    assert decision.disposition is JobIdentityDisposition.SAME
    assert decision.canonical_job_id == "job-1"


def test_close_but_uncertain_candidates_are_ambiguous():
    decision = resolver.resolve(
        incoming=_candidate(
            company_id="cmp-1",
            title="Operator Produksi",
            location="Bekasi",
            description="Production line operator",
        ),
        existing=(
            _candidate(
                canonical_job_id="job-a",
                company_id="cmp-1",
                title="Operator Production",
                location="Bekasi",
                description="Production line operator day shift",
            ),
            _candidate(
                canonical_job_id="job-b",
                company_id="cmp-1",
                title="Operator Produksi",
                location="Cikarang",
                description="Production line operator night shift",
            ),
        ),
    )

    assert decision.disposition is JobIdentityDisposition.AMBIGUOUS
    assert decision.canonical_job_id is None
```

Also add a clearly different requisition test -> `DISTINCT`.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_job_entity_resolution.py -q
```

- [ ] **Step 3: Implement resolver with explicit thresholds and reason codes**

Use deterministic scoring signals:
- verified `company_id`;
- authoritative source/external ID equality;
- normalized title;
- normalized location;
- description similarity;
- employment type;
- apply-domain/requisition hints;
- publication window.

Do not use one magic score alone. Return reason codes such as:
- `AUTHORITATIVE_REQUISITION_MATCH`
- `COMPANY_MISMATCH`
- `CLOSE_MULTIPLE_CANDIDATES`
- `LOW_SIMILARITY_DISTINCT`.

- [ ] **Step 4: Integrate pipeline without deleting current compatibility helper**

`IngestionPipeline` may continue using `job_identity_key` as a fallback only when resolver has no candidate ambiguity. It must not merge an `AMBIGUOUS` incoming observation. Create an internal unresolved/possible-duplicate record for Task 10 review instead.

- [ ] **Step 5: Run focused + ingestion regression**

```bash
python -m pytest tests/test_job_entity_resolution.py -q
python -m pytest -q -k 'ingestion or dedupe or identity'
```

- [ ] **Step 6: Commit**

```bash
git add \
  onejob/ingestion/entity_resolution.py \
  onejob/ingestion/pipeline.py \
  tests/test_job_entity_resolution.py

git diff --cached --check
git commit -m "feat: add ambiguity-safe job entity resolution"
```

---

### Task 7: Evidence authority and independent-family consensus

**Files:**
- Modify: `onejob/ingestion/consensus.py`
- Modify: `onejob/ingestion/evidence_store.py`
- Create: `onejob/job_verification/corroboration.py`
- Test: `tests/test_evidence_authority.py`

**Interfaces:**
- Produces:
  - `EvidenceAuthority`
  - `CorroborationSummary`
  - `summarize_corroboration(evidence) -> CorroborationSummary`
- Source authority comes from registry policy/identity evidence, not hard-coded platform fame.
- Independent family count is separate from appearance count.

- [ ] **Step 1: Write mirror-amplification RED test**

```python
def test_three_mirrors_from_one_family_count_as_one_independent_source():
    summary = summarize_corroboration(
        (
            _evidence("e1", family="family-ats", source="src-ats"),
            _evidence("e2", family="family-ats", source="src-board-a"),
            _evidence("e3", family="family-ats", source="src-board-b"),
        )
    )

    assert summary.appearance_count == 3
    assert summary.independent_family_count == 1
```

Add:

```python
def test_one_authoritative_family_can_outrank_many_low_authority_mirrors():
    consensus = resolve_field_consensus(
        "location_text",
        [
            _row("official", "Bekasi", "official-family", confidence=0.98),
            _row("mirror-1", "Jakarta", "mirror-family", confidence=0.55),
            _row("mirror-2", "Jakarta", "mirror-family", confidence=0.55),
        ],
    )
    assert consensus.selected_value == "Bekasi"
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_evidence_authority.py -q
```

- [ ] **Step 3: Replace static source-type confidence lookup**

Remove `SOURCE_CONFIDENCE` as the final authority. Keep a conservative compatibility default only for legacy rows that predate source registry enrollment. New evidence must receive an explicit authority confidence calculated from:
- source trust tier;
- compliance/rollout state;
- company relationship evidence;
- acquisition method;
- source health.

- [ ] **Step 4: Implement corroboration summary**

`CorroborationSummary`:

```python
@dataclass(frozen=True)
class CorroborationSummary:
    appearance_count: int
    independent_family_count: int
    authoritative_family_count: int
    conflicting_family_count: int
    reason_codes: tuple[str, ...]
```

- [ ] **Step 5: Run consensus regression**

```bash
python -m pytest tests/test_evidence_authority.py -q
python -m pytest -q -k 'consensus or evidence'
```

- [ ] **Step 6: Commit**

```bash
git add \
  onejob/ingestion/consensus.py \
  onejob/ingestion/evidence_store.py \
  onejob/job_verification/corroboration.py \
  tests/test_evidence_authority.py

git diff --cached --check
git commit -m "feat: make job evidence authority lineage-aware"
```

---

### Task 8: Safe apply-destination verification and SSRF-resistant fetch policy

**Files:**
- Create: `onejob/job_verification/__init__.py`
- Create: `onejob/job_verification/destination.py`
- Create: `onejob/job_verification/models.py`
- Test: `tests/test_apply_destination.py`
- Test: `tests/test_job_source_security.py`

**Interfaces:**
- Produces:
  - `ApplyDestinationStatus`
  - `ApplyDestinationAssessment`
  - `DestinationVerifier.verify(url, *, allowed_relationships, fetcher) -> ApplyDestinationAssessment`
  - `SafeFetchPolicy.validate_url(url) -> None`
  - `UnsafeFetchTarget`
- No external HTTP is performed by unit tests; inject resolver/fetcher functions.

- [ ] **Step 1: Write RED URL safety tests**

```python
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/private",
        "http://192.168.1.1/private",
        "file:///etc/passwd",
        "ftp://example.com/jobs",
    ],
)
def test_fetch_policy_rejects_private_or_non_http_targets(url):
    with pytest.raises(UnsafeFetchTarget):
        SafeFetchPolicy().validate_url(url)
```

Add a redirect test where public URL redirects to private IP and must fail.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_apply_destination.py tests/test_job_source_security.py -q
```

- [ ] **Step 3: Implement URL validation**

Use `urllib.parse`, `ipaddress`, and injected DNS resolution. Reject:
- non-http/https;
- userinfo credentials in URL;
- loopback;
- private;
- link-local;
- multicast/reserved/unspecified;
- redirects whose new target fails the same policy.

Do not add a network library.

- [ ] **Step 4: Implement destination assessment**

Statuses:

```python
VERIFIED
ALLOWED_EXTERNAL
UNKNOWN
SUSPICIOUS
BLOCKED
```

Persist/return:
- original URL;
- final resolved URL;
- final domain;
- redirect chain fingerprint;
- checked time;
- reason codes.

A verified company/ATS relationship can yield `VERIFIED`. Unknown unrelated redirect cannot.

- [ ] **Step 5: Add credential-leak test**

Ensure destination/public models never serialize collector tokens, Authorization headers, cookies, or URL userinfo.

- [ ] **Step 6: Run security tests**

```bash
python -m pytest tests/test_apply_destination.py tests/test_job_source_security.py -q
```

- [ ] **Step 7: Commit**

```bash
git add \
  onejob/job_verification/__init__.py \
  onejob/job_verification/models.py \
  onejob/job_verification/destination.py \
  tests/test_apply_destination.py \
  tests/test_job_source_security.py

git diff --cached --check
git commit -m "feat: verify safe job apply destinations"
```

---

### Task 9: Freshness model and immutable verification snapshots with Trust Engine bridge

**Files:**
- Modify: `onejob/job_verification/models.py`
- Create: `onejob/job_verification/freshness.py`
- Create: `onejob/job_verification/repository.py`
- Create: `onejob/job_verification/service.py`
- Modify: `onejob/persistence/migrations/007_job_source_verification_network.sql`
- Test: `tests/test_job_verification_service.py`

**Interfaces:**
- Produces:
  - `FreshnessState`
  - `FreshnessAssessment`
  - `JobVerificationSnapshot`
  - `JobVerificationService.evaluate(canonical_job_id, *, now) -> JobVerificationSnapshot`
  - content-addressed snapshot reuse when semantic inputs match.
- Consumes:
  - company identity resolution/snapshot;
  - corroboration summary;
  - apply destination assessment;
  - existing `TrustEngineService`;
  - latest canonical version.

- [ ] **Step 1: Write RED snapshot immutability/reuse tests**

```python
def test_identical_verification_inputs_reuse_snapshot_id(service):
    first = service.evaluate("job-1", now=NOW)
    second = service.evaluate("job-1", now=NOW)

    assert first.input_fingerprint == second.input_fingerprint
    assert first.verification_id == second.verification_id


def test_changed_evidence_creates_new_verification_snapshot(service):
    first = service.evaluate("job-1", now=NOW)
    service.fixture_store.add_independent_evidence("job-1", "evidence-2")
    second = service.evaluate("job-1", now=NOW)

    assert first.verification_id != second.verification_id
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_job_verification_service.py -q
```

- [ ] **Step 3: Define freshness states**

```python
class FreshnessState(str, Enum):
    CURRENT = "CURRENT"
    DUE_SOON = "DUE_SOON"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"
```

`FreshnessAssessment` contains:
- state;
- last_authoritative_seen_at;
- evaluated_at;
- valid_until;
- reason codes.

- [ ] **Step 4: Add immutable verification tables**

Migration must create:

```sql
CREATE TABLE job_verification_snapshots (...);
CREATE UNIQUE INDEX idx_job_verification_fingerprint
ON job_verification_snapshots(canonical_job_id, input_fingerprint);

CREATE TABLE job_verification_snapshot_evidence (...);
```

Snapshot row fields must include:
- verification ID;
- canonical job/version;
- identity snapshot;
- Trust Engine evaluation ID;
- destination assessment JSON/ref;
- corroboration JSON/ref;
- freshness JSON/ref;
- hard gates JSON;
- unknowns JSON;
- evaluated/valid-until;
- input fingerprint;
- verification policy version.

- [ ] **Step 5: Implement Trust Engine bridge without reverse dependency**

`job_verification.service` imports/calls `TrustEngineService`. No Trust Engine file imports `job_verification`, publication, or catalog.

If Trust Engine throws an unexpected system exception:
- do not fabricate a trust result;
- raise `VerificationSystemFailure`;
- preserve previously committed ingestion;
- publication task will fail closed.

- [ ] **Step 6: Run service + Trust Engine regression**

```bash
python -m pytest tests/test_job_verification_service.py -q
python -m pytest -q -k 'trust_engine or trust'
```

- [ ] **Step 7: Commit**

```bash
git add \
  onejob/job_verification/models.py \
  onejob/job_verification/freshness.py \
  onejob/job_verification/repository.py \
  onejob/job_verification/service.py \
  onejob/persistence/migrations/007_job_source_verification_network.sql \
  tests/test_job_verification_service.py

git diff --cached --check
git commit -m "feat: add immutable job verification snapshots"
```

---

### Task 10: Publication policy and atomic publication decisions

**Files:**
- Create: `onejob/job_verification/policy.py`
- Modify: `onejob/job_verification/models.py`
- Modify: `onejob/job_verification/repository.py`
- Modify: `onejob/persistence/migrations/007_job_source_verification_network.sql`
- Test: `tests/test_publication_policy.py`

**Interfaces:**
- Produces:
  - `PublicationState`
  - `PublicationDecision`
  - `PublicationPolicy.evaluate(snapshot, source_policy) -> PublicationDecisionDraft`
  - `VerificationRepository.append_publication_decision(...)`
- Publication states:
  - `NOT_EVALUATED`
  - `VERIFYING`
  - `PUBLISHABLE`
  - `REVIEW_REQUIRED`
  - `QUARANTINED`
  - `REJECTED`
  - `WITHDRAWN`.

- [ ] **Step 1: Write exact publication-matrix RED tests**

```python
def test_authoritative_current_safe_job_is_publishable():
    draft = PublicationPolicy().evaluate(
        _snapshot(
            trust_classification="AUTOPILOT_ELIGIBLE",
            identity_state="VERIFIED",
            destination_status="VERIFIED",
            freshness_state="CURRENT",
            hard_gates=(),
            critical_unknowns=(),
        ),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )

    assert draft.state is PublicationState.PUBLISHABLE


def test_review_required_trust_never_becomes_publishable():
    draft = PublicationPolicy().evaluate(
        _snapshot(trust_classification="REVIEW_REQUIRED"),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.state is PublicationState.REVIEW_REQUIRED


def test_absolute_block_is_rejected():
    draft = PublicationPolicy().evaluate(
        _snapshot(trust_classification="ABSOLUTE_BLOCK"),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.state is PublicationState.REJECTED


def test_policy_blocked_source_cannot_publish_even_with_high_trust():
    draft = PublicationPolicy().evaluate(
        _snapshot(
            trust_classification="AUTOPILOT_ELIGIBLE",
            identity_state="VERIFIED",
            destination_status="VERIFIED",
            freshness_state="CURRENT",
        ),
        source_policy=_source_policy(publication_evidence_allowed=False),
    )
    assert draft.state is not PublicationState.PUBLISHABLE
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_publication_policy.py -q
```

- [ ] **Step 3: Implement deterministic matrix**

Hard precedence:
1. confirmed hard block / `ABSOLUTE_BLOCK` -> `REJECTED`;
2. `AUTOMATION_BLOCKED` -> `QUARANTINED`;
3. source policy disallows publication evidence -> `REVIEW_REQUIRED` or non-public internal state, never `PUBLISHABLE`;
4. critical identity/destination unknown -> `REVIEW_REQUIRED`;
5. expired/closed -> `WITHDRAWN`;
6. `REVIEW_REQUIRED` trust -> `REVIEW_REQUIRED`;
7. eligible high/assisted trust + sufficient identity/destination/freshness -> `PUBLISHABLE`.

Reason codes are required for every decision.

- [ ] **Step 4: Add publication persistence tables**

```sql
CREATE TABLE publication_decisions (...);
CREATE INDEX idx_publication_job_time
ON publication_decisions(canonical_job_id, decided_at DESC);

CREATE TABLE job_publication_heads (
    canonical_job_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    state TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(decision_id) REFERENCES publication_decisions(decision_id)
);
```

The immutable decision history is append-only. Only the head pointer/state is updated transactionally.

- [ ] **Step 5: Add atomicity test**

Simulate exception after immutable decision insert but before head update inside one DB transaction. Assert neither write commits.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_publication_policy.py -q
```

- [ ] **Step 7: Commit**

```bash
git add \
  onejob/job_verification/models.py \
  onejob/job_verification/policy.py \
  onejob/job_verification/repository.py \
  onejob/persistence/migrations/007_job_source_verification_network.sql \
  tests/test_publication_policy.py

git diff --cached --check
git commit -m "feat: add fail-closed publication policy"
```

---

### Task 11: Human verification queue, authorization, idempotency, and stale-context protection

**Files:**
- Create: `onejob/job_verification/review.py`
- Modify: `onejob/job_verification/models.py`
- Modify: `onejob/job_verification/repository.py`
- Modify: `onejob/persistence/migrations/007_job_source_verification_network.sql`
- Test: `tests/test_verification_review.py`

**Interfaces:**
- Produces:
  - `VerificationCaseState`
  - `VerificationCase`
  - `VerificationResolution`
  - `ReviewActor`
  - `ReviewCommandService.resolve_case(...)`
- Requires:
  - actor role/permission;
  - `expected_verification_id`;
  - idempotency key;
  - case must still be open/current.
- Human resolution cannot clear absolute hard gates.

- [ ] **Step 1: Write RED authorization/stale tests**

```python
def test_non_reviewer_cannot_resolve_case(service, open_case):
    with pytest.raises(ReviewAuthorizationDenied):
        service.resolve_case(
            actor=ReviewActor(actor_id="user-1", roles=("candidate",)),
            case_id=open_case.case_id,
            expected_verification_id=open_case.verification_id,
            idempotency_key="idem-1",
            decision=ReviewDecision.VERIFY,
            reason_codes=("MANUAL_CORROBORATION",),
            now=NOW,
        )


def test_stale_verification_context_cannot_be_resolved(service, open_case):
    service.fixture_store.supersede_verification(open_case.canonical_job_id)

    with pytest.raises(StaleReviewContext):
        service.resolve_case(
            actor=ReviewActor(actor_id="reviewer-1", roles=("job_verifier",)),
            case_id=open_case.case_id,
            expected_verification_id=open_case.verification_id,
            idempotency_key="idem-2",
            decision=ReviewDecision.VERIFY,
            reason_codes=("MANUAL_CORROBORATION",),
            now=NOW,
        )
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_verification_review.py -q
```

- [ ] **Step 3: Add review tables**

```sql
CREATE TABLE verification_cases (...);
CREATE TABLE verification_resolutions (...);
CREATE TABLE verification_review_idempotency (...);
```

Case states:

```python
OPEN
IN_REVIEW
DEFERRED
RESOLVED
SUPERSEDED
```

- [ ] **Step 4: Implement command semantics**

Review `VERIFY` does not directly mutate public catalog state. It writes resolution evidence, closes/supersedes the case, triggers a fresh verification/publication evaluation, and lets policy decide the new state.

If current verification contains an absolute non-overridable hard gate, reject `VERIFY` with `HardGateNotReviewOverrideable`.

- [ ] **Step 5: Add idempotency test**

Same idempotency key + identical payload returns the original resolution. Same key + different payload raises `IdempotencyConflict`.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_verification_review.py -q
```

- [ ] **Step 7: Commit**

```bash
git add \
  onejob/job_verification/models.py \
  onejob/job_verification/repository.py \
  onejob/job_verification/review.py \
  onejob/persistence/migrations/007_job_source_verification_network.sql \
  tests/test_verification_review.py

git diff --cached --check
git commit -m "feat: add auditable verification review queue"
```

---

### Task 12: Reverification scheduler, official closure, and source circuit-breaker integration

**Files:**
- Create: `onejob/job_verification/reverification.py`
- Modify: `onejob/job_verification/freshness.py`
- Modify: `onejob/ingestion/lifecycle.py`
- Modify: `onejob/job_sources/health.py`
- Modify: `onejob/persistence/migrations/007_job_source_verification_network.sql`
- Test: `tests/test_reverification.py`

**Interfaces:**
- Produces:
  - `ReverificationWorkItem`
  - `ReverificationRepository.claim_due(...)`
  - `ReverificationRunner.run_due(limit, now) -> ReverificationRunSummary`
- Persistent due work; process restart does not lose schedule.
- `429`/rate-limit is source health evidence, not job closure evidence.
- Authoritative `404/closed` must be explicitly mapped by the adapter/source semantics before lifecycle moves toward `CLOSED`.

- [ ] **Step 1: Write RED lifecycle distinction tests**

```python
def test_rate_limit_does_not_close_job():
    result = apply_reverification_observation(
        current=JobLifecycleState.ACTIVE,
        source_result=SourceRefreshResult.RATE_LIMITED,
        authoritative=True,
    )
    assert result.lifecycle_state is JobLifecycleState.ACTIVE


def test_authoritative_closed_result_withdraws_active_listing():
    result = apply_reverification_observation(
        current=JobLifecycleState.ACTIVE,
        source_result=SourceRefreshResult.CONFIRMED_CLOSED,
        authoritative=True,
    )
    assert result.lifecycle_state is JobLifecycleState.CLOSED
    assert result.requires_publication_reevaluation is True
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_reverification.py -q
```

- [ ] **Step 3: Add persistent queue table**

```sql
CREATE TABLE reverification_work (
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
```

- [ ] **Step 4: Implement adaptive next-check calculation**

Inputs:
- source tier;
- source health;
- job age;
- explicit `expires_at`;
- last authoritative sighting;
- previous change frequency;
- snapshot confidence/valid-until.

Return deterministic `next_verification_at`. Do not use random jitter in domain tests.

- [ ] **Step 5: Implement bounded retry classification**

Error classes:
- `RATE_LIMITED`;
- `TRANSIENT_NETWORK`;
- `AUTH_FAILURE`;
- `SCHEMA_CHANGED`;
- `PERMANENT_POLICY_BLOCK`;
- `SYSTEM_FAILURE`.

Retry transient/rate-limit with bounded backoff; do not retry policy block as if transient.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_reverification.py -q
```

- [ ] **Step 7: Commit**

```bash
git add \
  onejob/job_verification/reverification.py \
  onejob/job_verification/freshness.py \
  onejob/ingestion/lifecycle.py \
  onejob/job_sources/health.py \
  onejob/persistence/migrations/007_job_source_verification_network.sql \
  tests/test_reverification.py

git diff --cached --check
git commit -m "feat: add adaptive job reverification"
```

---

### Task 13: Public catalog read boundary and website-safe API

**Files:**
- Create: `onejob/catalog/__init__.py`
- Create: `onejob/catalog/models.py`
- Create: `onejob/catalog/repository.py`
- Create: `onejob/catalog/service.py`
- Create: `onejob/catalog/api.py`
- Modify: `onejob/api.py`
- Test: `tests/test_catalog_api.py`

**Interfaces:**
- Produces:
  - `PublicJob`
  - `PublicVerificationSummary`
  - `CatalogRepository.list_publishable(...)`
  - `CatalogRepository.get_publishable(...)`
  - `CatalogService`
  - router endpoints:
    - `GET /api/catalog/jobs`
    - `GET /api/catalog/jobs/{job_id}`
    - `GET /api/catalog/jobs/{job_id}/verification`
- No public endpoint can query review/quarantine/rejected jobs.

- [ ] **Step 1: Write RED visibility tests**

```python
def test_catalog_lists_only_publishable_jobs(client, seeded_catalog):
    response = client.get("/api/catalog/jobs")

    assert response.status_code == 200
    ids = {item["canonical_job_id"] for item in response.json()}
    assert seeded_catalog.publishable_job_id in ids
    assert seeded_catalog.review_job_id not in ids
    assert seeded_catalog.rejected_job_id not in ids


def test_rejected_job_returns_404_from_public_catalog(client, seeded_catalog):
    response = client.get(
        f"/api/catalog/jobs/{seeded_catalog.rejected_job_id}"
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_catalog_api.py -q
```

- [ ] **Step 3: Define allowlisted public models**

`PublicJob` may expose:
- canonical job ID;
- title/company/location/employment type;
- salary/currency when available;
- safe apply destination;
- listing lifecycle;
- verification summary;
- source attribution safe labels.

`PublicVerificationSummary` may expose:
- confidence;
- checked_at;
- source appearance count;
- independent evidence family count;
- primary public reason codes.

Do not expose:
- raw payload reference/content;
- internal evidence IDs if they reveal private paths;
- reviewer ID/notes;
- source API credentials;
- stack traces;
- internal hard-gate implementation text.

- [ ] **Step 4: Implement PUBLISHABLE-only SQL at repository level**

The SQL itself must join `job_publication_heads` with `state='PUBLISHABLE'`; do not fetch all jobs then filter in Python.

- [ ] **Step 5: Mount router only when DB is configured**

Follow the existing `GAWEYUK_DB_PATH` pattern in `onejob/api.py`. A catalog initialization failure must not leak internals; if DB is configured and catalog subsystem is expected but cannot initialize, prefer explicit service-unavailable behavior over silently serving unverified legacy data from the catalog route.

Keep existing `/api/jobs` unchanged in Slice 4A for compatibility; 4C can migrate consumers later.

- [ ] **Step 6: Add response leak test**

Seed raw evidence with marker `"SECRET_INTERNAL_EVIDENCE_MARKER"` and reviewer note `"PRIVATE_REVIEW_NOTE"`. Assert neither string appears in JSON from any `/api/catalog/*` endpoint.

- [ ] **Step 7: Run API tests**

```bash
python -m pytest tests/test_catalog_api.py -q
python -m pytest tests/test_api.py -q
```

- [ ] **Step 8: Commit**

```bash
git add \
  onejob/catalog \
  onejob/api.py \
  tests/test_catalog_api.py

git diff --cached --check
git commit -m "feat: expose verified public job catalog"
```

---

### Task 14: Internal source/review API boundary with explicit authorization

**Files:**
- Create: `onejob/job_verification/api.py`
- Create: `onejob/job_sources/api.py`
- Modify: `onejob/api.py`
- Test: `tests/test_catalog_api.py`
- Test: `tests/test_verification_review.py`

**Interfaces:**
- Internal routes are separate from candidate-facing catalog.
- Minimum endpoints for Slice 4A:
  - `GET /internal/sources`
  - `GET /internal/sources/{source_id}`
  - `GET /internal/verification/cases`
  - `GET /internal/verification/cases/{case_id}`
  - `POST /internal/verification/cases/{case_id}/resolve`
- Internal actor resolver must be injected; no hard-coded “always owner/admin” behavior for production path.

- [ ] **Step 1: Write unauthorized API RED test**

```python
def test_internal_review_endpoint_rejects_candidate_actor(client):
    response = client.get("/internal/verification/cases")
    assert response.status_code in {401, 403}
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_verification_review.py tests/test_catalog_api.py -q
```

- [ ] **Step 3: Implement minimal internal routers**

Translate domain exceptions explicitly:
- authorization denied -> 403;
- not found -> 404;
- stale context -> 409;
- idempotency conflict -> 409;
- hard gate not overrideable -> 422;
- system failure -> 503.

Do not return raw exception strings.

- [ ] **Step 4: Add stale review HTTP test**

POST with old `expected_verification_id` must return 409 and stable error code `STALE_REVIEW_CONTEXT`.

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_verification_review.py tests/test_catalog_api.py -q
```

- [ ] **Step 6: Commit**

```bash
git add \
  onejob/job_verification/api.py \
  onejob/job_sources/api.py \
  onejob/api.py \
  tests/test_verification_review.py \
  tests/test_catalog_api.py

git diff --cached --check
git commit -m "feat: add protected verification operations API"
```

---

### Task 15: Integrate ingestion with registry/provenance/verification without coupling publication into collector transaction

**Files:**
- Modify: `onejob/ingestion/pipeline.py`
- Modify: `onejob/persistence/repositories.py`
- Modify: `onejob/job_verification/service.py`
- Test: `tests/test_ingestion_provenance.py`
- Test: `tests/test_job_verification_service.py`
- Test: `tests/test_job_source_failures.py`

**Interfaces:**
- `IngestionPipeline.collect_one` sequence:
  1. collect batch;
  2. resolve registered source and source policy;
  3. persist immutable observations/provenance/canonical data in DB transaction;
  4. commit;
  5. trigger verification for affected canonical IDs;
  6. verification/publication failure does not roll back raw ingestion.
- No collector imports publication policy.
- No catalog mutation occurs directly in ingestion transaction.

- [ ] **Step 1: Write RED durability test**

```python
def test_verification_crash_does_not_rollback_ingestion(
    db,
    collector,
    monkeypatch,
):
    pipeline = build_pipeline(db)

    def crash(*args, **kwargs):
        raise RuntimeError("verification crashed")

    monkeypatch.setattr(
        pipeline.verification,
        "evaluate_and_publish",
        crash,
    )

    with pytest.raises(RuntimeError, match="verification crashed"):
        pipeline.collect_one(collector, collector.target)

    with db.connection() as conn:
        observation_count = conn.execute(
            "SELECT COUNT(*) FROM raw_job_observations"
        ).fetchone()[0]

    assert observation_count > 0
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_job_source_failures.py -q
```

- [ ] **Step 3: Refactor pipeline dependency injection**

Constructor should accept/reuse focused collaborators:

```python
class IngestionPipeline:
    def __init__(
        self,
        db,
        *,
        source_service=None,
        entity_resolver=None,
        verification_service=None,
    ):
        ...
```

Defaults may instantiate production implementations for compatibility, but tests can inject deterministic fakes.

- [ ] **Step 4: Resolve source before treating evidence as authoritative**

Unknown unregistered source:
- may be recorded only if explicitly allowed by migration/compatibility policy;
- cannot become publication-authoritative;
- should produce a source-policy reason that keeps downstream publication closed.

Existing Greenhouse/Lever/Ashby source records should be seeded/registered in shadow-compatible state by explicit bootstrap code or test fixtures, not magic inside every observation insert.

- [ ] **Step 5: Keep post-commit verification**

Use:

```python
result = _commit_ingestion(...)
for canonical_job_id in result.canonical_job_ids:
    verification.evaluate_and_publish(
        canonical_job_id,
        now=clock(),
    )
```

If verification raises a system failure, surface/log the failure; do not convert it into successful publication or silently call legacy feed behavior.

- [ ] **Step 6: Run ingestion + failure tests**

```bash
python -m pytest \
  tests/test_ingestion_provenance.py \
  tests/test_job_verification_service.py \
  tests/test_job_source_failures.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add \
  onejob/ingestion/pipeline.py \
  onejob/persistence/repositories.py \
  onejob/job_verification/service.py \
  tests/test_ingestion_provenance.py \
  tests/test_job_verification_service.py \
  tests/test_job_source_failures.py

git diff --cached --check
git commit -m "feat: connect ingestion to fail-closed verification"
```

---

### Task 16: Security/adversarial corpus and hard-risk publication invariants

**Files:**
- Create: `tests/security_cases/job_source_verification_cases.json`
- Modify: `tests/test_job_source_security.py`
- Modify: `tests/test_publication_policy.py`
- Test: existing Trust Engine security corpus/tests

**Interfaces:**
- Adversarial fixtures have stable IDs, inputs, and expected publication result/reason family.
- Any regression that previously escaped must become a permanent fixture.

- [ ] **Step 1: Create adversarial corpus**

Create JSON cases for at least:

```json
[
  {"id":"lookalike-domain","expected":"REVIEW_REQUIRED"},
  {"id":"punycode-impersonation","expected":"REVIEW_REQUIRED"},
  {"id":"redirect-private-network","expected":"REJECTED"},
  {"id":"mirror-amplification","expected":"REVIEW_REQUIRED"},
  {"id":"salary-bait-discovery-only","expected":"REVIEW_REQUIRED"},
  {"id":"fake-ats-tenant","expected":"REVIEW_REQUIRED"},
  {"id":"official-job-closed-mirror-stale","expected":"WITHDRAWN"},
  {"id":"payment-negated","expected":"NOT_HARD_BLOCKED"},
  {"id":"payment-required","expected":"REJECTED"},
  {"id":"otp-request","expected":"REJECTED"},
  {"id":"conflicting-company-identity","expected":"REVIEW_REQUIRED"},
  {"id":"collector-schema-change","expected":"SOURCE_DEGRADED"}
]
```

The full fixture objects must include concrete URLs/text/evidence required by the test harness, not just IDs.

- [ ] **Step 2: Add parameterized corpus test**

```python
@pytest.mark.parametrize("case", load_security_cases())
def test_job_source_security_case(case, harness):
    result = harness.evaluate(case)
    assert result.outcome == case["expected"]
```

- [ ] **Step 3: Add negation regression**

Explicitly prove `"Tidak ada biaya rekrutmen"` does not trigger the same hard gate as `"Transfer biaya administrasi Rp150.000"`.

Reuse existing Trust Engine signal extractor rather than creating a second payment detector.

- [ ] **Step 4: Add hard-gate non-override invariant**

Try:
- AI suggestion;
- human `VERIFY`;
- high source confidence.

None may turn confirmed credential/payment/impersonation absolute block into `PUBLISHABLE`.

- [ ] **Step 5: Run security corpus**

```bash
python -m pytest \
  tests/test_job_source_security.py \
  tests/test_publication_policy.py \
  -q

python -m pytest -q -k 'security or trust'
```

- [ ] **Step 6: Commit**

```bash
git add \
  tests/security_cases/job_source_verification_cases.json \
  tests/test_job_source_security.py \
  tests/test_publication_policy.py

git diff --cached --check
git commit -m "test: add job verification adversarial corpus"
```

---

### Task 17: Failure injection, transaction invariants, and system-failure semantics

**Files:**
- Modify: `tests/test_job_source_failures.py`
- Modify: `onejob/job_verification/repository.py`
- Modify: `onejob/job_verification/service.py`
- Modify: `onejob/job_verification/reverification.py`

**Interfaces:**
- Domain uncertainty and system failure remain distinct.
- No partial publication state survives transaction failure.
- Previous consistent publication decision remains the head if a new decision transaction fails.

- [ ] **Step 1: Add failure matrix tests**

Cover:
- DB error during source registration;
- DB error after verification snapshot insert;
- DB error before publication head update;
- Trust Engine crash;
- identity resolver crash;
- source timeout;
- rate limit;
- malformed adapter payload;
- review concurrency conflict;
- reverification worker restart.

Example:

```python
def test_publication_transaction_failure_preserves_old_head(
    seeded_publishable_job,
    monkeypatch,
):
    old_head = seeded_publishable_job.current_decision_id

    monkeypatch.setattr(
        seeded_publishable_job.repository,
        "_update_head",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("head write failed")
        ),
    )

    with pytest.raises(RuntimeError, match="head write failed"):
        seeded_publishable_job.publish_new_decision()

    assert seeded_publishable_job.reload_head() == old_head
```

- [ ] **Step 2: Add UNKNOWN-vs-crash test**

```python
def test_unknown_identity_is_domain_result_not_system_failure(service):
    result = service.evaluate("job-unknown-identity", now=NOW)
    assert "COMPANY_IDENTITY" in result.unknowns


def test_identity_resolver_exception_is_system_failure(service, monkeypatch):
    monkeypatch.setattr(
        service.identity_resolver,
        "resolve",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("resolver down")
        ),
    )
    with pytest.raises(VerificationSystemFailure):
        service.evaluate("job-1", now=NOW)
```

- [ ] **Step 3: Run failure suite**

```bash
python -m pytest tests/test_job_source_failures.py -q
```

- [ ] **Step 4: Run focused relevant regression**

```bash
python -m pytest -q -k 'failure or ingestion or trust or publication'
```

- [ ] **Step 5: Commit**

```bash
git add \
  onejob/job_verification/repository.py \
  onejob/job_verification/service.py \
  onejob/job_verification/reverification.py \
  tests/test_job_source_failures.py

git diff --cached --check
git commit -m "test: harden Slice 4A failure semantics"
```

---

### Task 18: End-to-end Slice 4A acceptance scenarios and legacy compatibility

**Files:**
- Create: `tests/test_slice4a_acceptance.py`
- Modify only if required: `onejob/api.py`
- Modify only if required: `onejob/service.py`

**Interfaces:**
- Acceptance harness uses real SQLite repositories/services with deterministic fake external fetchers; no live internet required.
- Existing `/api/jobs` remains available and unchanged in Slice 4A.
- New catalog proves verification gate is actually in the data path.

- [ ] **Step 1: Write authoritative publish E2E**

Test flow:
1. register authoritative ATS in validated/active-eligible state;
2. seed verified ATS↔company relationship;
3. collector produces active requisition;
4. ingestion commits observation/canonical version;
5. Trust Engine returns eligible classification using real service path/fixtures;
6. verification snapshot persists;
7. publication becomes `PUBLISHABLE`;
8. `/api/catalog/jobs` contains job.

Use concrete assertions:

```python
assert catalog_job["canonical_job_id"] == canonical_job_id
assert catalog_job["verification_summary"]["independent_evidence_family_count"] == 1
assert catalog_job["apply_destination"]["status"] == "VERIFIED"
```

- [ ] **Step 2: Write official closure E2E**

Refresh authoritative source with confirmed closure semantics. Assert:
- lifecycle becomes `CLOSED`;
- a new verification/publication decision exists;
- publication head is `WITHDRAWN`;
- catalog endpoint returns 404 for that job;
- historical decisions/snapshots remain queryable internally.

- [ ] **Step 3: Write scam/impersonation E2E**

Discovery source + lookalike domain + explicit payment request:
- raw observation persists;
- canonical/internal evidence may persist;
- hard gate is present;
- final state is `REJECTED`;
- public catalog never contains the job.

- [ ] **Step 4: Write mirror-lineage E2E**

Three appearances sharing one upstream family:
- appearance count = 3;
- independent family count = 1;
- no confidence amplification as if three independent sources.

- [ ] **Step 5: Write ambiguous-duplicate E2E**

Two plausible existing requisitions produce `AMBIGUOUS`:
- no silent merge;
- possible-duplicate review case opens;
- neither receives evidence from the ambiguous observation until resolution policy assigns it.

- [ ] **Step 6: Verify legacy API compatibility**

Run:

```bash
python -m pytest tests/test_api.py -q
```

Add a focused assertion only if missing that `/api/jobs` still returns the legacy service feed while `/api/catalog/jobs` is the new verified boundary.

- [ ] **Step 7: Run acceptance tests**

```bash
python -m pytest tests/test_slice4a_acceptance.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add \
  tests/test_slice4a_acceptance.py \
  onejob/api.py \
  onejob/service.py

git diff --cached --check
git commit -m "test: verify Slice 4A end-to-end behavior"
```

If `onejob/api.py` or `onejob/service.py` did not change, do not stage them.

---

### Task 19: Anti-Slop code-quality gate, release verification, and branch handoff

**Files:**
- Review all Slice 4A modified Python files.
- No new feature files unless a verified defect requires a focused fix.

**Interfaces:**
- Produces a clean, push-ready feature branch.
- Requires fresh full regression evidence.
- Does not merge.

- [ ] **Step 1: Run Anti-Slop code-comment audit**

Read:
- `antislop.md`
- `skills/antislop-code/SKILL.md`

Inspect only changed code:

```bash
git diff main...HEAD -- '*.py'
```

Remove comments that merely narrate obvious syntax or use generic AI scaffolding such as:
- `# Step 1`;
- `# Initialize`;
- `# Handle error`;
- banner comments;
- prose that restates the next line.

Keep comments that explain:
- policy invariant;
- security constraint;
- non-obvious SQLite transaction reason;
- why uncertainty differs from failure;
- why a mirror is not independent evidence.

Do not change working code merely to make comments stylistically uniform.

- [ ] **Step 2: Scan plan/spec requirements against implementation**

Run searches:

```bash
grep -R "TODO\|TBD\|FIXME" \
  onejob/job_sources \
  onejob/company_identity \
  onejob/job_verification \
  onejob/catalog \
  onejob/ingestion \
  tests/test_job_source_* \
  tests/test_slice4a_acceptance.py || true
```

Any hit must be evaluated. Remove placeholders; keep only legitimate test fixture text if a test explicitly needs those tokens.

- [ ] **Step 3: Run targeted Slice 4A suite**

```bash
python -m pytest \
  tests/test_job_source_registry.py \
  tests/test_collector_contract.py \
  tests/test_ingestion_provenance.py \
  tests/test_company_identity_graph.py \
  tests/test_job_entity_resolution.py \
  tests/test_evidence_authority.py \
  tests/test_apply_destination.py \
  tests/test_job_verification_service.py \
  tests/test_publication_policy.py \
  tests/test_verification_review.py \
  tests/test_reverification.py \
  tests/test_catalog_api.py \
  tests/test_job_source_security.py \
  tests/test_job_source_failures.py \
  tests/test_slice4a_acceptance.py \
  -q
```

Expected: 0 failures.

- [ ] **Step 4: Run fresh full regression**

```bash
python -m pytest -q
```

Expected:
- exit code 0;
- no regressions from the preflight baseline;
- the pre-existing Starlette/TestClient deprecation warning may remain if unchanged, but new warnings introduced by Slice 4A must be investigated.

Record the exact fresh result in the release report; do not reuse counts from earlier tasks.

- [ ] **Step 5: Run repository hygiene checks**

```bash
git diff --check
git status --short
git log --oneline --decorate main..HEAD
git diff --stat main...HEAD
```

Expected:
- `git diff --check` prints nothing;
- working tree is clean;
- commits are task-focused;
- only Slice 4A docs/skills/code/tests/migration changed.

- [ ] **Step 6: Verify architectural invariants by search/review**

Confirm:
- no collector imports `job_verification.policy` or `catalog`;
- Trust Engine imports no `catalog` or publication module;
- public catalog repository SQL filters `PUBLISHABLE`;
- no `except Exception: pass` around verification that silently exposes legacy data;
- no live internet requirement in tests;
- no secrets committed;
- no country hard-code in core model decisions.

Useful checks:

```bash
grep -R "from onejob.catalog\|import onejob.catalog" onejob/collectors onejob/trust_engine || true
grep -R "from onejob.job_verification.policy" onejob/collectors || true
grep -R "POLICY_BLOCKED\|PUBLISHABLE" onejob/catalog onejob/job_verification
```

- [ ] **Step 7: Commit final audit fixes if needed**

Only if Step 1–6 required real changes:

```bash
git add <exact-files-that-were-fixed>
git diff --cached --check
git commit -m "chore: finalize Slice 4A verification network"
```

Do not create an empty commit.

- [ ] **Step 8: Push feature branch**

Run:

```bash
git push -u origin feature/job-source-verification-network-4a
```

Expected: branch tracks `origin/feature/job-source-verification-network-4a`.

- [ ] **Step 9: Produce release report**

Report exactly:
- feature branch;
- HEAD SHA from `git rev-parse HEAD`;
- commit count from `git rev-list --count main..HEAD`;
- `git diff --stat main...HEAD`;
- fresh full pytest result;
- warning count/summary;
- `git diff --check` result;
- working-tree cleanliness;
- whether push succeeded;
- any intentionally deferred work, which should only be Slice 4B+ items explicitly out of 4A scope.

Do not claim merged. Finishing/integration happens only after review.

---

## Plan Self-Review Checklist

The plan has been checked against the approved spec with these mappings:

- Tiered Source Network / Progressive Trust Rollout → Tasks 1–3.
- Source Registry / compliance / acquisition methods → Tasks 1–2.
- Existing Greenhouse/Lever/Ashby adapters → Task 3.
- Immutable observations / appearances / evidence families → Task 4.
- Company Identity Graph → Task 5.
- Canonical Job + ambiguity-safe dedup → Task 6.
- Evidence-family-aware consensus / 1 authoritative > many mirrors → Task 7.
- Safe apply destination / redirects / SSRF → Task 8.
- Freshness + immutable verification snapshots + Trust Engine bridge → Task 9.
- Publication state separate from lifecycle / fail-closed matrix → Task 10.
- Evidence-first human review / stale context / idempotency → Task 11.
- Reverification / official closure / source circuit breaker → Task 12.
- Public Catalog boundary / safe public schema → Task 13.
- Protected internal operations → Task 14.
- Observation → Verification integration with ingestion durability → Task 15.
- Hard scam/impersonation/mirror/security corpus → Task 16.
- Failure injection / UNKNOWN != system failure → Task 17.
- Acceptance scenarios / legacy compatibility → Task 18.
- Anti-Slop DURING, full regression, clean branch/push → Task 19.
- Indonesia-first/global-ready → global constraint applied to every task.
- No UI, auth product surface, PWA, full job-board rollout, or matching rewrite → deliberately excluded for Slice 4B/4C/4D.

No task requires a type/function that is not introduced in that task or an earlier task. No implementation step relies on live internet. No source is promoted merely because it is famous. No public response path can intentionally expose non-publishable jobs.

# Career Twin v2 Slice 3 — Career Intent, Saved Career Targets, and Contextual Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an immutable, user-authoritative Career Intent and Saved Career Target layer that deterministically resolves job-specific context, evaluates HARD/STRONG/SOFT policy before similarity, and feeds a stable `EvaluationContext` into the existing GaweYuk matching path.

**Architecture:** Implement three focused modules: `career_intent` owns typed intent versions and suggestions; `career_targets` owns stable targets, immutable target versions, compatibility, and routing; `career_context` owns deterministic resolution, immutable snapshots, three-valued policy evaluation, and the matching adapter. Authoritative writes use existing SQLite transaction/event/outbox patterns; consequential reads materialize content-addressed context snapshots. The existing matching engine is adapted, not rewritten.

**Tech Stack:** Python 3.x, FastAPI, Pydantic v2, SQLite via `sqlite3`, pytest, existing GaweYuk `Database`, Career Twin repositories/event-outbox patterns, existing `onejob.matching` / `onejob.service` compatibility path.

**Spec:** `docs/superpowers/specs/2026-08-21-career-twin-v2-slice-3-career-intent-target-context-design.md`

## Global Constraints

- Start from a clean branch based on `main` **after Career Twin v2 Slice 2 has been merged and freshly verified**. If Slice 2 is not on `main`, STOP; do not stack Slice 3 implementation on an unmerged Slice 2 feature branch.
- Preserve all Slice 1 and Slice 2 behavior and tests.
- Career Twin facts and Career Intent preferences are separate authorities.
- Saved Career Targets must not duplicate canonical Career Twin facts.
- Active pointers may move; immutable Intent versions, Target versions, and `ResolvedTargetView` snapshots may not mutate.
- HARD policy outranks verification requirements, STRONG/ SOFT preferences, and similarity.
- `UNKNOWN` is a first-class constraint result and must never be rewritten to `SATISFIED` or `VIOLATED`.
- Weakening/removing inherited HARD policy requires explicit authorized user exception semantics.
- AI/inference/system suggestions may not directly activate HARD authority or explicit HARD exceptions.
- Router may rank, abstain, and explain; it may not create/edit targets or intent.
- `NEEDS_REVIEW`, `UNSATISFIABLE`, stale, paused, and archived targets are not auto-routable.
- One official evaluation uses at most one target version. Alternative targets are counterfactual only.
- When Career Intent exists, contextual pipeline failure must not silently fall back to legacy matching.
- When no Career Intent exists, existing legacy matching behavior remains valid and unchanged.
- Internal decision context is not recruiter-facing disclosure authority.
- Use TDD for every behavior: RED → minimal GREEN → focused regression → commit.
- Do not perform unrelated refactors or introduce background workers, embeddings, arbitrary expression DSLs, a matching rewrite, or frontend redesign.
- Reuse existing repository conventions, transaction handling, event/outbox patterns, and error style from the merged Slice 2 baseline.
- The plan assumes Slice 2 occupies the next migration number after `004_career_twin_legacy_import.sql`; use `006_career_intent_context.sql` if Slice 2 merged as `005_*`. If merged `main` has a different latest migration number, rename only this planned migration to the next lexicographically ordered number before writing it.

---

## File Map

Create these focused modules:

```text
onejob/career_intent/
├── __init__.py
├── models.py          # enums + immutable intent/suggestion domain records
├── ontology.py        # typed predicate definitions and strictness semantics
├── validation.py      # temporal and contradiction validation
├── repositories.py    # intent/version/statement/suggestion persistence
├── commands.py        # version creation + suggestion decisions
└── query.py           # safe read models

onejob/career_targets/
├── __init__.py
├── models.py          # target/version/override/compatibility/routing records
├── repositories.py    # target persistence + compatibility/routing persistence
├── resolver.py        # typed inheritance and HARD exception semantics
├── compatibility.py   # target-vs-intent validation/revalidation
├── routing.py         # deterministic v1 applicability + ambiguity gate
└── commands.py        # create/revise/lifecycle commands

onejob/career_context/
├── __init__.py
├── models.py          # resolved view, assessments, policy gate, evaluation context
├── repositories.py    # snapshot + assessment persistence
├── policy.py          # three-valued constraint evaluation
├── service.py         # routing → resolve → materialize → evaluate orchestration
└── matching_adapter.py# stable bridge to existing matching

onejob/persistence/migrations/006_career_intent_context.sql
```

Modify only the integration surfaces required by the vertical slice:

```text
onejob/service.py
onejob/api.py
```

Add focused tests:

```text
tests/test_career_intent_ontology.py
tests/test_career_intent_validation.py
tests/test_career_intent_repositories.py
tests/test_career_intent_commands.py
tests/test_career_intent_suggestions.py
tests/test_career_targets_repositories.py
tests/test_career_target_resolution.py
tests/test_career_target_compatibility.py
tests/test_career_target_routing.py
tests/test_career_context_policy.py
tests/test_career_context_snapshots.py
tests/test_career_context_integration.py
tests/test_career_context_security.py
tests/test_career_context_api.py
tests/test_career_context_failures.py
```

Avoid adding Slice 3 behavior into `onejob/career_twin/repositories.py`; Slice 1 canonical claim writes must remain owned by the existing Career Twin repository layer.

---

### Task 0: Preflight the merged baseline and create the Slice 3 branch

**Files:**
- Read: `docs/superpowers/specs/2026-08-21-career-twin-v2-slice-3-career-intent-target-context-design.md`
- Read: `onejob/career_twin/`
- Read: `onejob/persistence/migrations/`
- Read: Slice 2 workflow files under `onejob/career_twin/` as merged
- No implementation files changed

**Interfaces:**
- Consumes: merged `main` containing Career Twin v2 Slice 1 + Slice 2
- Produces: clean branch `feature/career-twin-v2-slice-3` and a confirmed baseline test result

- [ ] **Step 1: Verify Slice 2 is actually merged into `main`**

Run:

```bash
git switch main
git pull --ff-only
git log --oneline --decorate -20
git status --short
```

Expected:
- `main` is checked out.
- Slice 2 commits/merge are visible in history.
- Working tree is clean **except** the two approved Slice 3 docs may be present as untracked files at their exact target paths:
  - `docs/superpowers/specs/2026-08-21-career-twin-v2-slice-3-career-intent-target-context-design.md`
  - `docs/superpowers/plans/2026-08-21-career-twin-v2-slice-3-career-intent-target-context.md`
- Any other modification/untracked file is a preflight failure and must be resolved before implementation.
- If Slice 2 is absent, STOP and finish Slice 2 push/PR/merge first.

- [ ] **Step 2: Run the full baseline suite before branching**

Run:

```bash
python -m pytest -q
```

Expected: zero failures. Record the exact baseline pass count in the eventual PR body; do not hard-code an expected count in implementation.

- [ ] **Step 3: Confirm migration numbering**

Run:

```bash
find onejob/persistence/migrations -maxdepth 1 -type f -name '*.sql' -printf '%f\n' | sort
```

Expected: identify the latest merged migration. If Slice 2 is `005_*`, use the planned `006_career_intent_context.sql`. If not, rename the planned migration filename to the next free number before Task 2.

- [ ] **Step 4: Create the feature branch**

Run:

```bash
git switch -c feature/career-twin-v2-slice-3
```

Expected: branch changes to `feature/career-twin-v2-slice-3`.

- [ ] **Step 5: Commit the approved Slice 3 spec and plan on the new branch**

Verify both exact files exist:

```bash
test -f docs/superpowers/specs/2026-08-21-career-twin-v2-slice-3-career-intent-target-context-design.md
test -f docs/superpowers/plans/2026-08-21-career-twin-v2-slice-3-career-intent-target-context.md
```

If either is missing, STOP and report the missing path; do not reconstruct the document from memory.

If the files are untracked, commit them:

```bash
git add   docs/superpowers/specs/2026-08-21-career-twin-v2-slice-3-career-intent-target-context-design.md   docs/superpowers/plans/2026-08-21-career-twin-v2-slice-3-career-intent-target-context.md
git commit -m "docs: add Career Twin v2 Slice 3 design and plan"
```

If the exact files are already tracked with identical approved content, do not create a duplicate/empty commit.

- [ ] **Step 6: Verify branch and cleanliness**

Run:

```bash
git status --short
git branch --show-current
```

Expected:
- no status output;
- branch is `feature/career-twin-v2-slice-3`.

Task 0 changes documentation only; no implementation code is allowed.

---

### Task 1: Add the typed Career Intent ontology and immutable domain models

**Files:**
- Create: `onejob/career_intent/__init__.py`
- Create: `onejob/career_intent/models.py`
- Create: `onejob/career_intent/ontology.py`
- Test: `tests/test_career_intent_ontology.py`
- Test: `tests/test_career_intent_validation.py` (only model-level temporal validation in this task)

**Interfaces:**
- Consumes: standard library `datetime`, `enum`; Pydantic v2
- Produces:
  - `IntentStrength`
  - `IntentCardinality`
  - `IntentValueType`
  - `IntentOperator`
  - `IntentMergePolicy`
  - `StrictnessDirection`
  - `UnknownPolicy`
  - `IntentPredicateDefinition`
  - `CareerIntentRecord`
  - `CareerIntentVersionRecord`
  - `IntentStatementRecord`
  - `get_intent_predicate_definition(predicate: str) -> IntentPredicateDefinition`
  - `compare_strictness(predicate: str, old_value: object, new_value: object) -> Literal["TIGHTER","EQUAL","WEAKER","UNKNOWN"]`
  - `temporal_state(statement, at: datetime) -> Literal["FUTURE","ACTIVE","EXPIRED"]`

- [ ] **Step 1: Write failing ontology tests**

Create `tests/test_career_intent_ontology.py` with tests equivalent to:

```python
import pytest

from onejob.career_intent.models import (
    IntentCardinality,
    IntentOperator,
    IntentStrength,
    StrictnessDirection,
)
from onejob.career_intent.ontology import (
    compare_strictness,
    get_intent_predicate_definition,
)


def test_min_salary_is_typed_as_higher_is_stricter():
    definition = get_intent_predicate_definition(
        "COMPENSATION.MIN_SALARY"
    )
    assert definition.cardinality is IntentCardinality.ONE
    assert definition.operator is IntentOperator.GTE
    assert (
        definition.strictness_direction
        is StrictnessDirection.HIGHER_IS_STRICTER
    )
    assert IntentStrength.HARD_CONSTRAINT in definition.allowed_strengths


def test_min_salary_strictness_is_semantic():
    assert compare_strictness(
        "COMPENSATION.MIN_SALARY", 6_000_000, 7_000_000
    ) == "TIGHTER"
    assert compare_strictness(
        "COMPENSATION.MIN_SALARY", 6_000_000, 5_000_000
    ) == "WEAKER"


def test_max_commute_inverts_numeric_strictness():
    assert compare_strictness(
        "COMMUTE.MAX_KM", 25, 15
    ) == "TIGHTER"
    assert compare_strictness(
        "COMMUTE.MAX_KM", 25, 40
    ) == "WEAKER"


def test_unknown_predicate_is_rejected():
    with pytest.raises(KeyError):
        get_intent_predicate_definition("ARBITRARY.EXPRESSION")
```

- [ ] **Step 2: Run the ontology tests and verify RED**

Run:

```bash
python -m pytest tests/test_career_intent_ontology.py -q
```

Expected: import/module failures because `career_intent` does not exist yet.

- [ ] **Step 3: Implement the minimal enums and record models**

In `onejob/career_intent/models.py`, implement these shapes using string enums and frozen Pydantic models where practical:

```python
class IntentStrength(str, Enum):
    HARD_CONSTRAINT = "HARD_CONSTRAINT"
    STRONG_PREFERENCE = "STRONG_PREFERENCE"
    SOFT_PREFERENCE = "SOFT_PREFERENCE"


class UnknownPolicy(str, Enum):
    REQUIRE_VERIFICATION = "REQUIRE_VERIFICATION"
    ALLOW_WITH_WARNING = "ALLOW_WITH_WARNING"
    BLOCK_IF_UNVERIFIED = "BLOCK_IF_UNVERIFIED"


class IntentCardinality(str, Enum):
    ONE = "ONE"
    MANY = "MANY"


class IntentOperator(str, Enum):
    EQ = "EQ"
    GTE = "GTE"
    LTE = "LTE"
    IN = "IN"
    NOT_IN = "NOT_IN"


class IntentMergePolicy(str, Enum):
    REPLACE = "REPLACE"
    SET = "SET"
    MIN = "MIN"
    MAX = "MAX"


class StrictnessDirection(str, Enum):
    HIGHER_IS_STRICTER = "HIGHER_IS_STRICTER"
    LOWER_IS_STRICTER = "LOWER_IS_STRICTER"
    NONE = "NONE"
```

Define immutable record models with the exact fields from the spec:

```python
class CareerIntentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    intent_id: str
    twin_id: str
    active_version_id: str | None
    created_at: datetime
    created_by_actor_id: str


class CareerIntentVersionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    intent_version_id: str
    intent_id: str
    version_number: int
    supersedes_version_id: str | None
    created_by_actor_id: str
    created_at: datetime
    input_fingerprint: str


class IntentStatementRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    statement_id: str
    intent_version_id: str
    predicate: str
    operator: IntentOperator
    value: object
    value_type: str
    strength: IntentStrength
    effective_from: datetime | None = None
    expires_at: datetime | None = None
    unknown_policy: UnknownPolicy | None = None
    provenance: dict[str, object] = Field(default_factory=dict)
```

Use a dedicated `IntentValueType` enum instead of leaving `value_type` as an unconstrained string if the existing project style favors enums.

- [ ] **Step 4: Implement a finite ontology registry**

In `onejob/career_intent/ontology.py`, define `IntentPredicateDefinition` and a registry with Slice 3 v1 predicates sufficient for the vertical path:

```python
"COMPENSATION.MIN_SALARY"
"COMPENSATION.MAX_SALARY"
"COMMUTE.MAX_KM"
"LOCATION.PREFERRED"
"WORK_MODE.ALLOWED"
"EMPLOYMENT_TYPE.PREFERRED"
"SHIFT.AVOID_NIGHT"
"ROLE.PREFERRED"
"AVAILABILITY.START_DATE"
```

Do not add arbitrary expressions. `get_intent_predicate_definition()` must fail closed on unknown predicates.

Implement strictness only where the ontology defines a direction. For `NONE`, return `"UNKNOWN"` unless values are equal.

- [ ] **Step 5: Write temporal-state tests**

Append to `tests/test_career_intent_validation.py`:

```python
from datetime import datetime, timezone

from onejob.career_intent.models import (
    IntentOperator,
    IntentStatementRecord,
    IntentStrength,
)
from onejob.career_intent.ontology import temporal_state


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


def make_statement(**overrides):
    data = dict(
        statement_id="s1",
        intent_version_id="iv1",
        predicate="COMMUTE.MAX_KM",
        operator=IntentOperator.LTE,
        value=25,
        value_type="DISTANCE",
        strength=IntentStrength.STRONG_PREFERENCE,
        provenance={},
    )
    data.update(overrides)
    return IntentStatementRecord(**data)


def test_temporal_state_future_active_expired():
    future = make_statement(
        effective_from=datetime(2026, 8, 22, tzinfo=timezone.utc)
    )
    active = make_statement(
        effective_from=datetime(2026, 8, 20, tzinfo=timezone.utc),
        expires_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    expired = make_statement(
        expires_at=datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
    )

    assert temporal_state(future, AT) == "FUTURE"
    assert temporal_state(active, AT) == "ACTIVE"
    assert temporal_state(expired, AT) == "EXPIRED"
```

- [ ] **Step 6: Run focused tests and make them GREEN**

Run:

```bash
python -m pytest \
  tests/test_career_intent_ontology.py \
  tests/test_career_intent_validation.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Run a focused legacy ontology regression**

Run:

```bash
python -m pytest tests/test_career_twin_ontology.py -q
```

Expected: all existing Career Twin ontology tests pass unchanged.

- [ ] **Step 8: Commit**

```bash
git add \
  onejob/career_intent \
  tests/test_career_intent_ontology.py \
  tests/test_career_intent_validation.py
git commit -m "feat: add typed career intent ontology"
```

---

### Task 2: Add Slice 3 persistence schema and focused repositories

**Files:**
- Create: `onejob/persistence/migrations/006_career_intent_context.sql` (or the next verified free migration number from Task 0)
- Create: `onejob/career_intent/repositories.py`
- Create: `onejob/career_targets/__init__.py`
- Create: `onejob/career_targets/models.py`
- Create: `onejob/career_targets/repositories.py`
- Create: `onejob/career_context/__init__.py`
- Create: `onejob/career_context/models.py`
- Create: `onejob/career_context/repositories.py`
- Test: `tests/test_career_intent_repositories.py`
- Test: `tests/test_career_targets_repositories.py`
- Test: `tests/test_career_context_snapshots.py`

**Interfaces:**
- Consumes: `onejob.persistence.db.Database`; existing SQLite transaction style
- Produces:
  - stateless `CareerIntentRepository`
  - stateless `SavedCareerTargetRepository`
  - stateless `CareerContextRepository`
  - repository methods that accept the caller-owned `sqlite3.Connection`, matching existing Career Twin repository conventions
  - persistence for immutable versions/statements/overrides/compatibility/routing/snapshots/assessments/suggestions
  - content-addressed snapshot lookup by `(twin_id, input_fingerprint)`

- [ ] **Step 1: Write repository tests for immutable Intent versions**

Create `tests/test_career_intent_repositories.py` with a temporary initialized `Database` and assert:

```python
def test_intent_repository_persists_version_and_moves_active_pointer_atomically(db):
    repo = CareerIntentRepository()
    version = CareerIntentVersionRecord(
        intent_version_id="iv-1",
        intent_id="intent-1",
        version_number=1,
        supersedes_version_id=None,
        created_by_actor_id="user-1",
        created_at=AT,
        input_fingerprint="fp-1",
    )
    statement = IntentStatementRecord(
        statement_id="is-1",
        intent_version_id="iv-1",
        predicate="COMPENSATION.MIN_SALARY",
        operator=IntentOperator.GTE,
        value=6_000_000,
        value_type="MONEY",
        strength=IntentStrength.HARD_CONSTRAINT,
        unknown_policy=UnknownPolicy.REQUIRE_VERIFICATION,
        provenance={"source": "USER_INPUT"},
    )

    with db.transaction() as conn:
        repo.create_intent(
            conn,
            twin_id="twin-1",
            actor_id="user-1",
            intent_id="intent-1",
        )
        repo.append_version(
            conn,
            version=version,
            statements=[statement],
        )
        repo.move_active_pointer(
            conn,
            intent_id="intent-1",
            expected_active_version_id=None,
            new_active_version_id="iv-1",
        )

    with db.connection() as conn:
        assert repo.get(conn, "intent-1").active_version_id == "iv-1"
        assert repo.get_version(conn, "iv-1") == version
```

Also assert a second version does not mutate the first row and stale expected-active input is rejected by a repository/domain exception rather than overwritten.

- [ ] **Step 2: Write repository tests for target identity/version persistence**

Create `tests/test_career_targets_repositories.py` proving:

- stable `target_id`;
- immutable `target_version_id`;
- active pointer movement;
- lifecycle values `ACTIVE`, `PAUSED`, `ARCHIVED`;
- overrides belong to target versions;
- compatibility records are keyed to exact `(target_version_id, intent_version_id, validator_version)`.

- [ ] **Step 3: Write snapshot dedupe repository test**

In `tests/test_career_context_snapshots.py`:

```python
def test_resolved_view_is_reused_by_twin_and_fingerprint(db):
    repo = CareerContextRepository()
    first_input = ResolvedTargetViewRecord(
        resolved_view_id="rv-1",
        twin_id="twin-1",
        intent_version_id="iv-1",
        target_version_id="tv-1",
        routing_decision_id="route-1",
        scope=ResolvedScope.TARGETED,
        resolved_statements=[],
        applied_overrides=[],
        explicit_exceptions=[],
        active_temporal_statements=[],
        tensions=[],
        validation_status="VALID",
        resolver_version="resolver-v1",
        evaluated_at=AT,
        input_fingerprint="same-fp",
    )
    second_input = first_input.model_copy(
        update={"resolved_view_id": "rv-2"}
    )

    with db.transaction() as conn:
        first = repo.get_or_create_resolved_view(
            conn, view=first_input
        )
        second = repo.get_or_create_resolved_view(
            conn, view=second_input
        )

    assert second.resolved_view_id == first.resolved_view_id
```

- [ ] **Step 4: Run the repository tests and verify RED**

Run:

```bash
python -m pytest \
  tests/test_career_intent_repositories.py \
  tests/test_career_targets_repositories.py \
  tests/test_career_context_snapshots.py -q
```

Expected: missing migration/modules/repositories.

- [ ] **Step 5: Write the migration**

Create tables with foreign keys and immutable-version constraints for:

```text
career_intents
career_intent_versions
career_intent_statements
career_intent_suggestions
career_intent_suppressions

saved_career_targets
saved_career_target_versions
target_intent_overrides
target_compatibility_assessments
target_applicability_assessments
target_routing_decisions

resolved_target_views
constraint_assessments
```

Required schema rules:

- `career_intents.twin_id` is unique for v1 unless existing product requirements explicitly support more than one aggregate per twin.
- `(intent_id, version_number)` unique.
- `(target_id, version_number)` unique.
- active pointers are nullable FKs to immutable version rows.
- `resolved_target_views` has unique `(twin_id, input_fingerprint)`.
- compatibility assessment includes exact intent + target version.
- routing/applicability records include algorithm version.
- payload-like structured fields use canonical JSON text, never Python repr.
- foreign keys point to existing Career Twin identity where the merged schema exposes a stable FK; if the current Slice 1 schema deliberately avoids a direct FK for twin IDs, follow that established convention rather than inventing an incompatible one.

Do **not** modify `Database._apply_migrations`; the current sorted migration runner already handles new SQL files.

- [ ] **Step 6: Implement frozen target/context record models**

In `onejob/career_targets/models.py`, define:

```python
class TargetLifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class OverrideOperation(str, Enum):
    INHERIT = "INHERIT"
    REPLACE = "REPLACE"
    ADD = "ADD"
    REMOVE = "REMOVE"
    CLEAR = "CLEAR"
    EXPLICIT_EXCEPTION = "EXPLICIT_EXCEPTION"


class TargetCompatibilityStatus(str, Enum):
    VALID = "VALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNSATISFIABLE = "UNSATISFIABLE"


class RoutingMethod(str, Enum):
    USER_SELECTED = "USER_SELECTED"
    AUTO_ROUTED = "AUTO_ROUTED"
    AMBIGUOUS = "AMBIGUOUS"
    UNSCOPED = "UNSCOPED"
```

Add frozen Pydantic records matching the spec for stable targets, target versions, overrides, compatibility, applicability, routing decisions, and:

```python
class AlternativeTargetAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    target_version_id: str
    applicability_score: float
    likely_policy_difference: list[str] = Field(default_factory=list)
    reason: str
```

Alternative assessments are informational only and never contribute statements or constraints to the primary resolved view.

In `onejob/career_context/models.py`, define:

```python
class ConstraintResult(str, Enum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"


class PolicyGateStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    INVALID_CONTEXT = "INVALID_CONTEXT"


class ResolvedScope(str, Enum):
    TARGETED = "TARGETED"
    UNSCOPED = "UNSCOPED"
```

and frozen models for `ResolvedTargetViewRecord`, `ConstraintAssessment`, `PolicyGateResult`, `EvaluationContext`.

- [ ] **Step 7: Implement focused repositories**

Repository responsibilities:

`CareerIntentRepository`
- `create_intent(conn, *, twin_id: str, actor_id: str, intent_id: str) -> CareerIntentRecord` / `get(conn, intent_id: str) -> CareerIntentRecord | None`;
- `append_version(conn, *, version: CareerIntentVersionRecord, statements: list[IntentStatementRecord]) -> None` / `get_version(conn, intent_version_id: str) -> CareerIntentVersionRecord | None`;
- `move_active_pointer(conn, intent_id, expected_active_version_id, new_active_version_id)`;
- persist/load statements through the same caller-owned connection;
- persist/read suggestions and suppression through the same caller-owned connection.

`SavedCareerTargetRepository`
- caller-owned-connection methods to create/get/list owned targets;
- append/get immutable target versions;
- lifecycle state transition with expected state/version checks;
- persist/load overrides;
- persist/load exact compatibility assessments;
- persist applicability and routing records.

`CareerContextRepository`
- `get_or_create_resolved_view(conn, *, view: ResolvedTargetViewRecord) -> ResolvedTargetViewRecord`;
- load resolved view by ID/twin through a supplied connection;
- append/list constraint assessments through a supplied connection.

Do not place cross-domain business logic such as hard exception validation inside repository methods.

- [ ] **Step 8: Run focused repository tests**

Run:

```bash
python -m pytest \
  tests/test_career_intent_repositories.py \
  tests/test_career_targets_repositories.py \
  tests/test_career_context_snapshots.py -q
```

Expected: all pass.

- [ ] **Step 9: Verify migration initialization from an empty DB**

Run:

```bash
python - <<'PY'
from tempfile import NamedTemporaryFile
from onejob.persistence.db import Database

with NamedTemporaryFile(suffix=".db") as f:
    db = Database(f.name)
    db.initialize()
    with db.connection() as conn:
        tables = {
            row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {
            "career_intents",
            "career_intent_versions",
            "career_intent_statements",
            "saved_career_targets",
            "saved_career_target_versions",
            "resolved_target_views",
        }
        assert required <= tables, required - tables
print("slice3 migration ok")
PY
```

Expected: `slice3 migration ok`.

- [ ] **Step 10: Commit**

```bash
git add \
  onejob/persistence/migrations \
  onejob/career_intent \
  onejob/career_targets \
  onejob/career_context \
  tests/test_career_intent_repositories.py \
  tests/test_career_targets_repositories.py \
  tests/test_career_context_snapshots.py
git commit -m "feat: add career intent and target persistence"
```

---

### Task 3: Implement deterministic Intent validation and contradiction detection

**Files:**
- Create: `onejob/career_intent/validation.py`
- Modify: `tests/test_career_intent_validation.py`
- Test: `tests/test_career_intent_validation.py`

**Interfaces:**
- Consumes: `IntentStatementRecord`, typed ontology
- Produces:
  - `IntentValidationStatus`
  - `IntentTension`
  - `IntentValidationResult`
  - `validate_statement(statement) -> None`
  - `validate_intent_statements(statements, at) -> IntentValidationResult`

- [ ] **Step 1: Add failing tests for invalid statement semantics**

Add tests proving:

```python
def test_unknown_predicate_is_invalid():
    statement = base_statement(
        predicate="ARBITRARY.EXPRESSION",
        value="anything",
    )
    with pytest.raises(UnknownIntentPredicate):
        validate_statement(statement)


def test_invalid_temporal_range_is_rejected():
    statement = base_statement(
        effective_from=datetime(2026, 9, 2, tzinfo=timezone.utc),
        expires_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(InvalidTemporalRange):
        validate_statement(statement)


def test_unknown_policy_is_rejected_when_predicate_does_not_allow_it():
    statement = base_statement(
        predicate="LOCATION.PREFERRED",
        operator=IntentOperator.IN,
        value=["Cikarang"],
        unknown_policy=UnknownPolicy.BLOCK_IF_UNVERIFIED,
    )
    with pytest.raises(InvalidIntentStatement):
        validate_statement(statement)
```

- [ ] **Step 2: Add failing contradiction tests**

Add deterministic cases:

```python
def test_impossible_hard_salary_range_is_unsatisfiable():
    statements = [
        hard("COMPENSATION.MIN_SALARY", "GTE", 7_000_000),
        hard("COMPENSATION.MAX_SALARY", "LTE", 6_000_000),
    ]
    result = validate_intent_statements(statements, at=AT)
    assert result.status == "UNSATISFIABLE"
    assert result.hard_conflicts


def test_hard_and_soft_tension_does_not_delete_soft_statement():
    statements = [
        hard("COMPENSATION.MIN_SALARY", "GTE", 7_000_000),
        soft("COMPENSATION.MAX_SALARY", "LTE", 6_000_000),
    ]
    result = validate_intent_statements(statements, at=AT)
    assert result.status == "VALID_WITH_TENSIONS"
    assert len(result.active_statements) == 2
    assert result.tensions
```

Task 1 must already include `COMPENSATION.MAX_SALARY` as a typed v1 predicate with `LOWER_IS_STRICTER`; this test verifies that definition participates in contradiction/tension analysis.

- [ ] **Step 3: Run and verify RED**

Run:

```bash
python -m pytest tests/test_career_intent_validation.py -q
```

Expected: missing validation API or failed contradiction assertions.

- [ ] **Step 4: Implement validation results**

Use explicit enums:

```python
class IntentValidationStatus(str, Enum):
    VALID = "VALID"
    VALID_WITH_TENSIONS = "VALID_WITH_TENSIONS"
    UNSATISFIABLE = "UNSATISFIABLE"
```

`validate_intent_statements()` must:
1. validate each statement against ontology;
2. exclude FUTURE/EXPIRED statements from the evaluated active set while retaining their temporal state in validation metadata;
3. detect known impossible HARD combinations;
4. retain SOFT/STRONG tensions as structured tension records;
5. never mutate input statements.

Do not attempt SAT/SMT solver generality. Implement only typed v1 contradiction rules supported by ontology.

- [ ] **Step 5: Run focused tests**

```bash
python -m pytest \
  tests/test_career_intent_ontology.py \
  tests/test_career_intent_validation.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add onejob/career_intent/validation.py \
  onejob/career_intent/ontology.py \
  tests/test_career_intent_validation.py
git commit -m "feat: add contradiction-aware intent validation"
```

---

### Task 4: Implement Career Intent commands with authorization, idempotency, concurrency, event/outbox

**Files:**
- Create: `onejob/career_intent/commands.py`
- Test: `tests/test_career_intent_commands.py`
- Modify if required by merged Slice 2 convention: shared command error/idempotency module already introduced by Slice 2
- Do not duplicate Slice 2 idempotency infrastructure if it already exists

**Interfaces:**
- Consumes:
  - `Database` as the transaction owner
  - stateless `CareerIntentRepository`
  - `validate_intent_statements`
  - merged Slice 2 actor authorization context
  - merged Slice 2 idempotency/error taxonomy
  - existing `CareerEventRepository.append_with_outbox(conn, event)` or the Slice 2 equivalent
- Produces:
  - `CreateCareerIntentVersionCommand`
  - `CareerIntentCommandService.create_version(command)`
  - stable domain errors: `STALE_VERSION`, `UNSATISFIABLE_INTENT`, `UNAUTHORIZED_ACTOR`, `IDEMPOTENCY_CONFLICT`

- [ ] **Step 1: Write RED test for first version creation**

Test command input:

```python
command = CreateCareerIntentVersionCommand(
    actor_id="user-1",
    twin_id="twin-1",
    idempotency_key="intent-create-1",
    expected_active_version_id=None,
    statements=[
        NewIntentStatement(
            predicate="COMPENSATION.MIN_SALARY",
            operator="GTE",
            value=6_000_000,
            strength="HARD_CONSTRAINT",
            unknown_policy="REQUIRE_VERIFICATION",
        )
    ],
)
```

Assert:
- stable intent exists;
- v1 is immutable;
- active pointer points to v1;
- event and outbox are committed;
- returned safe result includes IDs/version number, not raw internal rows.

- [ ] **Step 2: Add RED stale-version and unsatisfiable tests**

Prove:
- create v2 with correct expected v1 succeeds;
- a second request still expecting v1 after v2 exists raises `STALE_VERSION`;
- contradictory HARD statements are rejected before active pointer movement;
- failed command leaves no orphan active version/event/outbox.

- [ ] **Step 3: Add RED idempotency tests**

Prove:
- same idempotency key + same canonical payload returns same logical result;
- same key + different payload raises `IDEMPOTENCY_CONFLICT`.

- [ ] **Step 4: Add RED authorization test**

Use the merged Slice 2 actor authorization abstraction. Prove an actor not authorized for `twin-1` cannot create/activate Intent.

Do not invent a parallel security model.

- [ ] **Step 5: Run and verify RED**

```bash
python -m pytest tests/test_career_intent_commands.py -q
```

Expected: command service missing.

- [ ] **Step 6: Implement command transaction**

Required order:

```text
authorize actor for twin
→ canonicalize payload
→ idempotency check/reservation
→ load current active version
→ compare expected_active_version_id
→ materialize candidate statements
→ validate ontology + contradictions
→ BEGIN TRANSACTION
   create stable Intent if first version
   append immutable Intent version
   append statements
   move active pointer
   append audit event + outbox
   finalize idempotency result
→ COMMIT
```

Use the existing merged Slice 2 transaction/idempotency conventions exactly rather than creating a second framework.

- [ ] **Step 7: Run command tests**

```bash
python -m pytest tests/test_career_intent_commands.py -q
```

Expected: all pass.

- [ ] **Step 8: Run Slice 2 command regressions**

Discover the merged Slice 2 command tests and run them alongside:

```bash
python -m pytest \
  tests/test_career_intent_commands.py \
  tests/test_career_twin_approval.py -q
```

If Slice 2 added differently named workflow command tests, include those exact files as well.

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add onejob/career_intent/commands.py tests/test_career_intent_commands.py
git commit -m "feat: add transactional career intent commands"
```

---

### Task 5: Implement Saved Career Target commands and explicit HARD exception authority

**Files:**
- Create: `onejob/career_targets/commands.py`
- Create: `onejob/career_targets/resolver.py`
- Test: `tests/test_career_target_resolution.py`
- Extend: `tests/test_career_targets_repositories.py` only where command persistence needs repository coverage

**Interfaces:**
- Consumes:
  - `Database` as the transaction owner
  - stateless `SavedCareerTargetRepository`
  - stateless `CareerIntentRepository`
  - `compare_strictness`
  - actor authorization/idempotency primitives from merged Slice 2
- Produces:
  - `CreateSavedCareerTargetCommand`
  - `ReviseSavedCareerTargetCommand`
  - `SetTargetLifecycleCommand`
  - `TargetCommandService`
  - `resolve_target_policy(intent_statements, target_overrides, at) -> ResolvedPolicyDraft`
  - `HARD_CONSTRAINT_EXCEPTION_REQUIRED`

- [ ] **Step 1: Write failing tests for typed override merge**

In `tests/test_career_target_resolution.py`, prove:

```python
def test_many_value_remove_is_explicit_and_deterministic():
    global_statements = [
        preferred_locations(["Cikarang", "Bekasi", "Karawang"])
    ]
    override = remove_override(
        predicate="LOCATION.PREFERRED",
        value="Karawang",
    )
    resolved = resolve_target_policy(
        intent_statements=global_statements,
        target_overrides=[override],
        at=AT,
        exception_authority=None,
    )
    assert resolved.value_for("LOCATION.PREFERRED") == [
        "Cikarang", "Bekasi"
    ]


def test_target_can_tighten_hard_min_salary_without_exception():
    resolved = resolve_target_policy(
        intent_statements=[hard_min_salary(6_000_000)],
        target_overrides=[
            replace_override(
                predicate="COMPENSATION.MIN_SALARY",
                value=7_000_000,
            )
        ],
        at=AT,
        exception_authority=None,
    )
    assert resolved.value_for(
        "COMPENSATION.MIN_SALARY"
    ) == 7_000_000
    assert resolved.effect_for(
        "COMPENSATION.MIN_SALARY"
    ) == "TIGHTENED"


def test_target_cannot_weaken_hard_min_salary_with_plain_replace():
    with pytest.raises(HardConstraintExceptionRequired):
        resolve_target_policy(
            intent_statements=[hard_min_salary(6_000_000)],
            target_overrides=[
                replace_override(
                    predicate="COMPENSATION.MIN_SALARY",
                    value=5_000_000,
                )
            ],
            at=AT,
            exception_authority=None,
        )
```

- [ ] **Step 2: Add explicit exception authority test**

Prove:

```python
EXPLICIT_EXCEPTION
+ authorized user actor
+ exact inherited statement reference
→ resolves to weaker target-specific rule
```

Also prove:
- SYSTEM actor cannot authorize it;
- AI/inference actor cannot authorize it;
- exception lineage retains the overridden statement ID.

- [ ] **Step 3: Add strength-change tests**

Prove:
- explicit authorized user target command may strengthen local SOFT→STRONG or STRONG→HARD;
- inherited HARD→STRONG/SOFT requires `EXPLICIT_EXCEPTION`;
- inference cannot promote a target override to HARD on the user's behalf.

- [ ] **Step 4: Run and verify RED**

```bash
python -m pytest tests/test_career_target_resolution.py -q
```

Expected: resolver/commands missing.

- [ ] **Step 5: Implement `resolve_target_policy` as a pure function**

The pure resolver must:
1. filter temporal statements/overrides at `at`;
2. group by predicate;
3. obey ontology cardinality and merge operations;
4. compare semantic strictness for HARD inherited rules;
5. reject weakening without explicit exception authority;
6. retain structured provenance:
   - inherited statement ID;
   - override ID;
   - effect `TIGHTENED`, `EQUAL`, `WEAKENED_BY_EXPLICIT_EXCEPTION`, `ADDED`, `REMOVED`, `CLEARED`;
7. return a new immutable draft, never mutate source records.

No matching code belongs here.

- [ ] **Step 6: Write RED command tests for stable target identity and immutable revisions**

Prove:
- create target → version 1;
- revise same target → version 2, v1 unchanged;
- stale expected target version → `STALE_VERSION`;
- pause/resume/archive affect lifecycle only;
- archived target cannot be resumed unless spec/current lifecycle rules explicitly permit; default v1 behavior should make archive terminal.

- [ ] **Step 7: Implement `TargetCommandService`**

Use transactional pattern:

```text
authorize
→ idempotency
→ expected active target version
→ load active Intent context where override validation requires it
→ validate/resolve proposed overrides
→ transaction:
   append immutable target version
   move target active pointer
   append event/outbox
→ commit
```

Creating an explicit HARD exception must only succeed on a user-authorized command path.

- [ ] **Step 8: Run focused tests**

```bash
python -m pytest \
  tests/test_career_target_resolution.py \
  tests/test_career_targets_repositories.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add \
  onejob/career_targets/commands.py \
  onejob/career_targets/resolver.py \
  tests/test_career_target_resolution.py \
  tests/test_career_targets_repositories.py
git commit -m "feat: add immutable saved career target commands"
```

---

### Task 6: Implement target compatibility revalidation and quarantine

**Files:**
- Create: `onejob/career_targets/compatibility.py`
- Modify: `onejob/career_intent/commands.py`
- Test: `tests/test_career_target_compatibility.py`
- Modify: `tests/test_career_intent_commands.py`

**Interfaces:**
- Consumes:
  - `resolve_target_policy`
  - `validate_intent_statements`
  - repositories
- Produces:
  - `TargetCompatibilityService.assess(*, intent_version_id: str, target_version_id: str, at: datetime) -> TargetCompatibilityRecord`
  - `TargetCompatibilityService.revalidate_for_active_intent(*, twin_id: str, intent_version_id: str, at: datetime) -> list[TargetCompatibilityRecord]`
  - exact statuses `VALID`, `NEEDS_REVIEW`, `UNSATISFIABLE`
  - stale-assessment check for routing

- [ ] **Step 1: Write compatibility RED tests**

Create cases:

```python
def test_compatible_target_is_valid_for_exact_intent_version(scenario):
    intent_v1, target_v1 = scenario.valid_pair()
    result = scenario.compatibility.assess(
        intent_version_id=intent_v1,
        target_version_id=target_v1,
        at=AT,
    )
    assert result.status == TargetCompatibilityStatus.VALID
    assert result.against_intent_version_id == intent_v1


def test_new_global_hard_rule_can_put_target_into_needs_review(scenario):
    intent_v2, target_v1 = scenario.pair_requiring_explicit_exception()
    result = scenario.compatibility.assess(
        intent_version_id=intent_v2,
        target_version_id=target_v1,
        at=AT,
    )
    assert result.status == TargetCompatibilityStatus.NEEDS_REVIEW


def test_impossible_resolved_target_is_unsatisfiable(scenario):
    intent_v2, target_v1 = scenario.unsatisfiable_pair()
    result = scenario.compatibility.assess(
        intent_version_id=intent_v2,
        target_version_id=target_v1,
        at=AT,
    )
    assert result.status == TargetCompatibilityStatus.UNSATISFIABLE


def test_compatibility_assessment_for_old_intent_is_stale(scenario):
    old = scenario.persist_compatibility_for_intent("iv-1")
    assert scenario.compatibility.is_current(
        old, active_intent_version_id="iv-2"
    ) is False
```

The assessment must include exact `target_version_id`, `against_intent_version_id`, `validator_version`, reasons, and checked timestamp.

- [ ] **Step 2: Add activation-quarantine RED test**

Set up:
- active Intent v1;
- active Target v1 valid under v1;
- create/activate Intent v2;
- v2 is internally valid;
- Target v1 becomes incompatible.

Assert:
- v2 remains active;
- Target v1 record/version remains unchanged;
- compatibility becomes `NEEDS_REVIEW` or `UNSATISFIABLE`;
- no silent repair occurs.

- [ ] **Step 3: Run and verify RED**

```bash
python -m pytest \
  tests/test_career_target_compatibility.py \
  tests/test_career_intent_commands.py -q
```

Expected: compatibility service missing.

- [ ] **Step 4: Implement deterministic compatibility**

`TargetCompatibilityService.assess()` must resolve the exact target version against the exact Intent version, then classify:

- `VALID`: resolvable, no authority issue, internally valid;
- `NEEDS_REVIEW`: inherited active Intent changed such that existing target override needs explicit user choice/exception/revision;
- `UNSATISFIABLE`: resolved HARD policy cannot coexist.

Do not mutate Target version.

- [ ] **Step 5: Wire intent activation to dependent revalidation without a giant transaction**

Intent activation remains atomic for its own authoritative writes.

After activation, invoke deterministic target revalidation using the new exact active Intent version. If an individual revalidation fails technically:
- do not roll back a valid already committed Intent version;
- stale/missing compatibility makes that target ineligible for routing;
- surface/record the technical failure according to existing service conventions.

This preserves the spec's future async-readiness without requiring workers now.

- [ ] **Step 6: Run focused tests**

```bash
python -m pytest \
  tests/test_career_target_compatibility.py \
  tests/test_career_intent_commands.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add \
  onejob/career_targets/compatibility.py \
  onejob/career_intent/commands.py \
  tests/test_career_target_compatibility.py \
  tests/test_career_intent_commands.py
git commit -m "feat: add target compatibility quarantine"
```

---

### Task 7: Implement Intent Suggestion review and suppression without authority leakage

**Files:**
- Modify: `onejob/career_intent/models.py`
- Modify: `onejob/career_intent/repositories.py`
- Modify: `onejob/career_intent/commands.py`
- Test: `tests/test_career_intent_suggestions.py`

**Interfaces:**
- Consumes: existing Intent command service
- Produces:
  - `IntentSuggestionSource`
  - `IntentSuggestionDecision`
  - `IntentSuggestionRecord`
  - `create_suggestion(command: CreateIntentSuggestionCommand) -> IntentSuggestionRecord`
  - `accept_suggestion(command: AcceptIntentSuggestionCommand) -> CareerIntentVersionResult`
  - `edit_and_accept_suggestion(command: EditAndAcceptIntentSuggestionCommand) -> CareerIntentVersionResult`
  - `reject_suggestion(command: RejectIntentSuggestionCommand) -> IntentSuggestionRecord`
  - suppression check by stable fingerprint

- [ ] **Step 1: Write RED tests for suggestion authority**

Prove:

```python
def test_ai_suggestion_does_not_change_active_intent():
    suggestion = service.create_suggestion(
        CreateIntentSuggestionCommand(
            actor_id="system-1",
            twin_id="twin-1",
            intent_id="intent-1",
            idempotency_key="suggest-1",
            source="AI_INFERENCE",
            predicate="SHIFT.AVOID_NIGHT",
            operator="EQ",
            proposed_value=True,
            proposed_strength="SOFT_PREFERENCE",
            evidence=[{"kind": "behavior", "count": 5}],
        )
    )
    with db.connection() as conn:
        assert (
            intent_repo.get(conn, "intent-1").active_version_id
            == original_version
        )
    assert suggestion.decision_state == "PENDING"
```

- [ ] **Step 2: Write acceptance RED test**

Accepting a pending suggestion by authorized user must:
- create a new immutable Career Intent version;
- copy prior active statements plus the accepted change according to typed cardinality semantics;
- activate the new version;
- mark suggestion `ACCEPTED`;
- event/outbox all authoritative changes;
- be idempotent.

- [ ] **Step 3: Write edit-and-accept and HARD promotion tests**

Prove:
- user may edit suggestion value and strength before acceptance;
- AI suggestion proposed as SOFT may be explicitly promoted by user to HARD;
- no non-user actor may activate HARD.

- [ ] **Step 4: Write rejection/suppression RED tests**

Prove:
- rejection does not change active Intent;
- same fingerprint may be suppressed;
- suppression is separate from immutable Intent history;
- lifting suppression does not itself activate intent.

- [ ] **Step 5: Run RED**

```bash
python -m pytest tests/test_career_intent_suggestions.py -q
```

Expected: missing suggestion workflow.

- [ ] **Step 6: Implement suggestion workflow**

Use a stable canonical fingerprint over:

```text
intent_id
predicate
canonical proposed value
proposed strength
source family
```

Do not include volatile timestamps in the fingerprint.

All acceptance flows route through the same validated Career Intent version-creation authority path rather than writing statements directly.

- [ ] **Step 7: Run focused tests**

```bash
python -m pytest \
  tests/test_career_intent_suggestions.py \
  tests/test_career_intent_commands.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add \
  onejob/career_intent/models.py \
  onejob/career_intent/repositories.py \
  onejob/career_intent/commands.py \
  tests/test_career_intent_suggestions.py
git commit -m "feat: add user-controlled intent suggestions"
```

---

### Task 8: Implement deterministic target routing v1, ambiguity gate, and unscoped outcome

**Files:**
- Create: `onejob/career_targets/routing.py`
- Test: `tests/test_career_target_routing.py`

**Interfaces:**
- Consumes:
  - active target versions
  - exact current compatibility assessments
  - normalized job context from existing `CanonicalJob`
- Produces:
  - `RoutingConfig`
  - `TargetRoutingService.route(*, twin_id: str, intent_version_id: str, job: CanonicalJob, selected_target_id: str | None = None) -> TargetRoutingDecision`
  - `TargetApplicabilityAssessment`
  - deterministic `target-router-v1` provenance

- [ ] **Step 1: Write eligibility RED tests**

Prove each of these is excluded from AUTO routing:
- PAUSED;
- ARCHIVED;
- `NEEDS_REVIEW`;
- `UNSATISFIABLE`;
- compatibility record against an old Intent version;
- target without active version.

- [ ] **Step 2: Write deterministic signal tests**

Create fixtures with explicit target focus and job context. Assert stable signal names such as:

```text
ROLE_FAMILY_COMPATIBILITY
DOMAIN_COMPATIBILITY
LOCATION_RELEVANCE
EMPLOYMENT_TYPE_RELEVANCE
EXPLICIT_KEYWORD_MATCH
TARGET_SCOPE_MATCH
```

The exact initial scoring weights must live in `RoutingConfig(router_version="target-router-v1", minimum_threshold=0.60, ambiguity_margin=0.10, weights=ROUTER_V1_WEIGHTS)`, not module-level unnamed magic numbers.

- [ ] **Step 3: Write routing outcome tests**

```python
def test_clear_winner_auto_routes():
    # winner above minimum threshold and margin above ambiguity margin
    assert decision.method == "AUTO_ROUTED"


def test_close_top_scores_abstain_as_ambiguous():
    assert decision.method == "AMBIGUOUS"
    assert decision.selected_target_version_id is None


def test_low_scores_become_unscoped():
    assert decision.method == "UNSCOPED"
    assert decision.selected_target_version_id is None
```

- [ ] **Step 4: Write explicit user-selection and alternative-isolation tests**

Assert:
- valid explicitly selected target produces `USER_SELECTED` even if another target has a higher automatic score;
- explicitly selected `UNSATISFIABLE` target is rejected/invalid rather than forced through;
- non-primary routable targets may be returned as `AlternativeTargetAssessment` records;
- alternative target statements/overrides are never merged into the selected target's policy.

Use an assertion equivalent to:

```python
decision = router.route(
    twin_id="twin-1",
    intent_version_id="iv-1",
    job=job,
    selected_target_id="target-a",
)
assert decision.method == RoutingMethod.USER_SELECTED
assert decision.selected_target_version_id == "target-a-v1"
assert {
    item.target_version_id for item in decision.alternatives
} == {"target-b-v1"}
```

- [ ] **Step 5: Run RED**

```bash
python -m pytest tests/test_career_target_routing.py -q
```

Expected: router missing.

- [ ] **Step 6: Implement pure applicability scoring**

Use deterministic normalization. Do not call an LLM or embedding service.

For v1, derive role/domain/location/employment/keyword/scope signals from known normalized job/target fields. If a signal cannot be established, record it as absent/unknown rather than inventing semantic certainty.

Persist assessments and the final routing decision through `SavedCareerTargetRepository`.

- [ ] **Step 7: Implement ambiguity and no-target gates**

Required order:

```text
filter eligible targets
→ compute assessments
→ rank deterministically
→ if no target reaches minimum threshold: UNSCOPED
→ else if top-two margin < ambiguity margin: AMBIGUOUS
→ else AUTO_ROUTED
```

Tie-breaking may be deterministic for ordering/display but must not convert an ambiguous policy outcome into AUTO routing.

- [ ] **Step 8: Run focused tests**

```bash
python -m pytest tests/test_career_target_routing.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add onejob/career_targets/routing.py tests/test_career_target_routing.py
git commit -m "feat: add deterministic saved target routing"
```

---

### Task 9: Implement `ResolvedTargetView` materialization and canonical fingerprinting

**Files:**
- Create: `onejob/career_context/service.py`
- Modify: `onejob/career_context/repositories.py`
- Modify: `tests/test_career_context_snapshots.py`
- Test: `tests/test_career_context_integration.py` (resolution-only cases initially)

**Interfaces:**
- Consumes:
  - `CareerIntentRepository`
  - `SavedCareerTargetRepository`
  - `TargetRoutingService`
  - `resolve_target_policy`
  - `CareerContextRepository`
- Produces:
  - `CareerContextService.resolve(*, twin_id: str, job: CanonicalJob, evaluated_at: datetime, selected_target_id: str | None = None) -> ResolvedContextOutcome`
  - `CareerContextService.materialize(outcome: ResolvedContextOutcome) -> ResolvedTargetViewRecord`
  - canonical `resolved_context_fingerprint(canonical_input: ResolvedFingerprintInput) -> str`
  - TARGETED and UNSCOPED immutable snapshots

- [ ] **Step 1: Add RED test for targeted materialization**

Set up an active Intent and valid selected Target. Assert snapshot contains:
- exact `intent_version_id`;
- exact `target_version_id`;
- routing decision ID;
- `scope="TARGETED"`;
- resolved statements;
- override provenance;
- explicit exceptions;
- active temporal statement IDs/states;
- tensions;
- resolver version;
- evaluated timestamp;
- canonical input fingerprint.

- [ ] **Step 2: Add RED test for UNSCOPED resolution**

When router returns `UNSCOPED`:
- no dummy target is created;
- `target_version_id is None`;
- global active Intent still resolves;
- global HARD policy remains present.

- [ ] **Step 3: Add RED ambiguity test**

When router returns `AMBIGUOUS`:
- do not materialize a primary target-specific evaluation;
- return a domain outcome requiring user selection;
- preserve competing routing assessments.

- [ ] **Step 4: Add canonical fingerprint tests**

Prove same semantic inputs produce the same fingerprint even if:
- dictionary key order differs;
- input objects were built independently.

Prove new fingerprint when:
- Intent version changes;
- Target version changes;
- relevant temporal state changes;
- explicit exception state changes;
- relevant job context changes;
- resolver version changes.

- [ ] **Step 5: Run RED**

```bash
python -m pytest \
  tests/test_career_context_snapshots.py \
  tests/test_career_context_integration.py -q
```

Expected: context orchestration missing.

- [ ] **Step 6: Implement canonical fingerprinting**

Create a canonical JSON representation with:
- sorted keys;
- deterministic list ordering where domain order is not semantic;
- explicit version fields;
- exact temporal activation result at evaluation time;
- only relevant normalized job fields.

Hash with the project's established fingerprint algorithm; if Slice 1/2 already exposes a canonical fingerprint helper, reuse it instead of introducing a second convention.

- [ ] **Step 7: Implement resolution/materialization orchestration**

`CareerContextService` must distinguish:
- `USER_SELECTED`;
- `AUTO_ROUTED`;
- `AMBIGUOUS`;
- `UNSCOPED`;
- technical failure.

Do not translate exceptions into `UNSCOPED`.

- [ ] **Step 8: Run focused tests**

```bash
python -m pytest \
  tests/test_career_context_snapshots.py \
  tests/test_career_context_integration.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add \
  onejob/career_context/service.py \
  onejob/career_context/repositories.py \
  tests/test_career_context_snapshots.py \
  tests/test_career_context_integration.py
git commit -m "feat: add immutable resolved target views"
```

---

### Task 10: Implement three-valued policy evaluation and gate precedence

**Files:**
- Create: `onejob/career_context/policy.py`
- Test: `tests/test_career_context_policy.py`

**Interfaces:**
- Consumes: `ResolvedTargetViewRecord`, normalized job context, Intent ontology
- Produces:
  - `evaluate_constraint(statement, job) -> ConstraintAssessment`
  - `evaluate_policy_gate(view, job) -> PolicyGateResult`
  - stable reason codes including `HARD_VIOLATION`, `HARD_UNVERIFIED`, `HARD_REVIEW_REQUIRED`, `STRONG_TRADEOFF`, `SOFT_MISS`

- [ ] **Step 1: Write RED tests for the three states**

```python
def test_hard_min_salary_satisfied():
    assert assessment.result == "SATISFIED"


def test_hard_min_salary_known_violation():
    assert assessment.result == "VIOLATED"


def test_hard_min_salary_missing_job_salary_is_unknown():
    assert assessment.result == "UNKNOWN"
```

- [ ] **Step 2: Write unknown-policy RED tests**

Prove:

```text
UNKNOWN + REQUIRE_VERIFICATION
→ PolicyGateStatus.REVIEW_REQUIRED

UNKNOWN + ALLOW_WITH_WARNING
→ PolicyGateStatus.ELIGIBLE + warning/reason

UNKNOWN + BLOCK_IF_UNVERIFIED
→ PolicyGateStatus.BLOCKED + HARD_UNVERIFIED
```

Critically assert the underlying assessment still says `UNKNOWN`.

- [ ] **Step 3: Write precedence RED tests**

Prove:
- HARD `VIOLATED` → `BLOCKED`;
- STRONG miss alone does not block;
- SOFT miss alone does not block;
- HARD block is not changed by any similarity input because similarity is not accepted by this evaluator.

- [ ] **Step 4: Write invalid-context RED test**

An unsatisfiable/invalid resolved view must return `INVALID_CONTEXT` rather than a normal matchable policy state.

- [ ] **Step 5: Run RED**

```bash
python -m pytest tests/test_career_context_policy.py -q
```

Expected: policy evaluator missing.

- [ ] **Step 6: Implement evaluators only for typed v1 predicates**

Evaluate known job-comparable predicates such as:
- salary;
- location;
- work mode when normalized data exists;
- employment type when normalized data exists;
- commute only if a verified/explicit distance value is present in the job/evaluation input.

Do not fabricate commute distance from location names.

If a predicate lacks required observed job data:
- return `UNKNOWN`;
- set structured `unknown_reason`;
- let `unknown_policy` determine gate consequence.

- [ ] **Step 7: Aggregate policy gate deterministically**

Precedence:

```text
INVALID_CONTEXT
> known HARD violation
> HARD unknown with BLOCK_IF_UNVERIFIED
> HARD unknown with REQUIRE_VERIFICATION
> STRONG trade-offs
> SOFT signals
```

Return all relevant reasons even when blocked so explainability remains complete.

- [ ] **Step 8: Run focused tests**

```bash
python -m pytest \
  tests/test_career_context_policy.py \
  tests/test_career_intent_ontology.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add onejob/career_context/policy.py tests/test_career_context_policy.py
git commit -m "feat: add three-valued career policy evaluation"
```

---

### Task 11: Add the stable `EvaluationContext` and existing matching adapter

**Files:**
- Create: `onejob/career_context/matching_adapter.py`
- Modify: `onejob/career_context/service.py`
- Modify: `onejob/service.py` around current `_evaluate`, `list_jobs`, `get_job`
- Test: `tests/test_career_context_integration.py`
- Preserve: `tests/test_matching.py` if present, `tests/test_api.py`, `tests/test_answers.py`

**Interfaces:**
- Consumes:
  - `Career Twin` safe/projection data available in the merged baseline
  - `ResolvedTargetView`
  - `PolicyGateResult`
  - current `match_job(job: CanonicalJob, profile: CareerTwin)`
- Produces:
  - `build_evaluation_context(*, twin_projection: dict, view: ResolvedTargetViewRecord, assessments: list[ConstraintAssessment], policy_gate: PolicyGateResult) -> EvaluationContext`
  - `match_with_context(job, legacy_profile, context) -> ContextualMatchResult`
  - contextual branch in `OneJobService` without rewriting `onejob.matching.match_job`

- [ ] **Step 1: Write RED test proving HARD block outranks high similarity**

Build a job that would score highly under existing `match_job`, but violates a contextual HARD minimum salary.

Assert contextual evaluation result:
- policy gate is `BLOCKED`;
- final decision cannot become `APPLY`;
- match score may be retained for explanation if useful, but has no authority to bypass the block.

- [ ] **Step 2: Write RED no-intent compatibility test**

Construct `OneJobService` without Career Intent/context service configured.

Assert current job evaluation output remains behaviorally identical to baseline:
- current fields remain;
- current legacy matching/policy/decision path remains available.

- [ ] **Step 3: Write RED contextual-failure no-fallback test**

Configure an active Intent/context service whose resolver raises a technical `ContextResolutionFailed`.

Assert:
- service surfaces contextual failure/review according to the new boundary;
- it does **not** silently call the legacy policy path and return a normal contextual-looking success.

- [ ] **Step 4: Run RED**

```bash
python -m pytest \
  tests/test_career_context_integration.py \
  tests/test_api.py \
  tests/test_answers.py -q
```

Expected: contextual adapter path missing while legacy tests remain green.

- [ ] **Step 5: Implement `EvaluationContext` construction**

Include:
- Career Twin projection/reference;
- resolved target view;
- constraint assessments;
- hard gate status;
- strong preference signals;
- soft preference signals;
- provenance;
- `context_version="career-context-v1"`.

Do not expose persistence repositories to `onejob.matching`.

- [ ] **Step 6: Implement adapter without rewriting `match_job`**

The adapter may:
- call existing `match_job(job, legacy_profile)` for current similarity;
- attach contextual signals/explanations;
- enforce that policy-gate result controls downstream decision eligibility.

Do not change Career Twin facts or target policy to improve match score.

- [ ] **Step 7: Integrate into `OneJobService`**

Extend constructor with an optional contextual evaluation dependency, e.g.:

```python
def __init__(
    self,
    repo: DemoRepository,
    *,
    career_twin_query=None,
    career_context_service=None,
):
    self.repo = repo
    self.career_twin_query = career_twin_query
    self.career_context_service = career_context_service
    self.profile = repo.load_profile()
    self.jobs = deduplicate_jobs(
        [normalize_job(raw) for raw in repo.load_jobs()]
    )
```

Behavior:

```text
career_context_service is None / no Intent configured
→ existing legacy _evaluate behavior

active Intent configured
→ contextual evaluation path

contextual engine technical failure
→ explicit contextual failure
→ no silent legacy fallback
```

Keep existing response fields for compatibility; add contextual fields under a dedicated safe nested key rather than repurposing old fields ambiguously.

- [ ] **Step 8: Run focused integration + legacy regressions**

```bash
python -m pytest \
  tests/test_career_context_integration.py \
  tests/test_api.py \
  tests/test_answers.py \
  tests/test_matching.py -q
```

If `tests/test_matching.py` does not exist, omit it and run the repository's actual matching test file(s).

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add \
  onejob/career_context/matching_adapter.py \
  onejob/career_context/service.py \
  onejob/service.py \
  tests/test_career_context_integration.py
git commit -m "feat: integrate contextual policy with matching"
```

---

### Task 12: Add safe query services and website-ready command/read API

**Files:**
- Create: `onejob/career_intent/query.py`
- Modify: `onejob/api.py`
- Test: `tests/test_career_context_api.py`
- Modify if needed: API/service wiring used by merged Slice 2

**Interfaces:**
- Consumes:
  - Career Intent/Target/Context command and query services
  - existing FastAPI app
- Produces safe endpoints conceptually matching:
  - `GET /api/career-intent`
  - `POST /api/career-intent/versions`
  - `GET /api/career-targets`
  - `POST /api/career-targets`
  - `GET /api/career-targets/{target_id}`
  - `POST /api/career-targets/{target_id}/versions`
  - lifecycle commands
  - `POST /api/career-context/route`
  - `POST /api/career-context/evaluate`
  - `GET /api/career-context/evaluations/{evaluation_id}`
  - Intent suggestion read/accept/reject/edit-and-accept

- [ ] **Step 1: Write RED safe-read tests**

Assert `/api/career-intent` response includes only product-safe fields such as:
- active version;
- statements;
- temporal state;
- tensions;
- pending suggestion count.

Assert it does not expose:
- raw database row IDs beyond product resource IDs;
- outbox payloads;
- raw idempotency records;
- internal hashes not needed by clients.

- [ ] **Step 2: Write RED version-command API tests**

Using `TestClient`, prove:
- valid user Intent version command returns success;
- stale expected active version maps to `409` + machine code `STALE_VERSION`;
- unsatisfiable input maps to stable semantic error;
- unknown predicate maps to stable domain error.

- [ ] **Step 3: Write RED target API tests**

Prove:
- create target;
- revise target;
- lifecycle commands;
- explicit hard exception requires proper user authority;
- quarantined/unsatisfiable target is visible for review but not routable.

- [ ] **Step 4: Write RED routing/evaluation API tests**

Prove domain outcomes are not 500s:

```text
AUTO_ROUTED
AMBIGUOUS
UNSCOPED
REVIEW_REQUIRED
BLOCKED
```

For `AMBIGUOUS`, response must include competing candidates and required action `USER_SELECTION`.

- [ ] **Step 5: Write RED technical failure mapping test**

Make context resolver raise technical failure. Assert:
- API returns 503 or the established contextual-unavailable status;
- machine code `CONTEXT_RESOLUTION_FAILED`;
- response is not `UNSCOPED`.

- [ ] **Step 6: Run RED**

```bash
python -m pytest tests/test_career_context_api.py -q
```

Expected: endpoints/wiring missing.

- [ ] **Step 7: Implement safe query services**

Query service methods must explicitly allowlist fields.

Do not return model dumps of persistence objects wholesale.

- [ ] **Step 8: Add Pydantic request models and endpoints**

Follow existing `onejob/api.py` style while keeping command semantics explicit. Map stable domain errors consistently.

If merged Slice 2 added a shared error-to-HTTP helper, reuse it instead of creating a second mapping table.

- [ ] **Step 9: Preserve current API endpoints**

Run:

```bash
python -m pytest \
  tests/test_career_context_api.py \
  tests/test_api.py -q
```

Expected: all pass, including existing `/api/jobs`, `/api/profile`, trust, and Career Twin endpoints.

- [ ] **Step 10: Commit**

```bash
git add \
  onejob/career_intent/query.py \
  onejob/api.py \
  tests/test_career_context_api.py
git commit -m "feat: add website-ready career context API"
```

---

### Task 13: Enforce ownership, actor security, privacy, and disclosure separation

**Files:**
- Test: `tests/test_career_context_security.py`
- Modify only as tests expose gaps:
  - `onejob/career_intent/commands.py`
  - `onejob/career_targets/commands.py`
  - `onejob/career_intent/query.py`
  - `onejob/career_context/service.py`
  - `onejob/api.py`

**Interfaces:**
- Consumes: merged Slice 2 actor/twin authorization
- Produces: verified cross-user isolation and no authority escalation

- [ ] **Step 1: Write cross-user read/write RED tests**

Prove actor A cannot:
- read actor B's target by guessed ID;
- revise actor B's target;
- read actor B's resolved evaluation;
- accept actor B's Intent suggestion.

Use access-safe 404 behavior where the merged API convention uses it.

- [ ] **Step 2: Write authority-escalation RED tests**

Prove:
- AI actor cannot activate HARD Intent;
- SYSTEM actor cannot authorize explicit HARD exception;
- forged `actor_id` in payload does not bypass request authorization context;
- high confidence does not grant extra authority.

- [ ] **Step 3: Write disclosure-boundary RED test**

Given an internal minimum-salary statement, assert current public/profile/answer paths do not automatically expose it.

Specifically run an answer-generation or profile-view path and assert the new Intent statement does not appear unless an explicit disclosure feature already exists and authorizes it.

- [ ] **Step 4: Run RED**

```bash
python -m pytest tests/test_career_context_security.py -q
```

Expected: any missing security checks fail.

- [ ] **Step 5: Apply minimal security fixes**

Keep authorization at command/query boundaries and ownership lookups. Do not sprinkle actor checks inside pure resolver/policy functions.

- [ ] **Step 6: Run security + answer/profile regressions**

```bash
python -m pytest \
  tests/test_career_context_security.py \
  tests/test_answers.py \
  tests/test_api.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add \
  tests/test_career_context_security.py \
  onejob/career_intent \
  onejob/career_targets \
  onejob/career_context \
  onejob/api.py
git commit -m "test: harden career context authority boundaries"
```

Use `git diff --cached --name-only` before committing; if the broad `git add` would stage unrelated files, stage only the files actually changed for this task.

---

### Task 14: Add failure-injection tests for transactional and technical-failure semantics

**Files:**
- Test: `tests/test_career_context_failures.py`
- Modify only as failures expose atomicity gaps:
  - intent/target/context repositories or commands

**Interfaces:**
- Consumes: transaction boundaries from Tasks 4–12
- Produces: proof that partial state and fake domain uncertainty cannot escape

- [ ] **Step 1: Write failure-after-version-insert RED test**

Inject a deterministic exception after immutable Intent version insertion but before active pointer/event completion.

Assert after rollback:
- no new active pointer;
- no orphan authoritative version if transaction owns insertion;
- no event without authoritative state;
- no outbox without authoritative state;
- idempotency record is retryable according to merged Slice 2 semantics.

- [ ] **Step 2: Write failure-before-outbox RED test**

Force event/outbox append failure during an authoritative command.

Assert entire command transaction rolls back.

- [ ] **Step 3: Write target-revision rollback RED test**

Inject failure before target active pointer movement. Assert previous version remains active and proposed version is not partially authoritative.

- [ ] **Step 4: Write snapshot materialization failure RED test**

Force snapshot persistence error.

Assert service returns technical `CONTEXT_RESOLUTION_FAILED` / materialization failure, not:
- `UNSCOPED`;
- `UNKNOWN`;
- a successful legacy evaluation.

- [ ] **Step 5: Run RED**

```bash
python -m pytest tests/test_career_context_failures.py -q
```

Expected: injected failure cases expose any missing boundaries.

- [ ] **Step 6: Fix only real atomicity/failure-classification gaps**

Use existing `Database.transaction()` and event/outbox atomic methods. Avoid compensating writes that are unnecessary inside SQLite transactions.

- [ ] **Step 7: Run focused failure suite**

```bash
python -m pytest \
  tests/test_career_context_failures.py \
  tests/test_career_intent_commands.py \
  tests/test_career_target_resolution.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add \
  tests/test_career_context_failures.py \
  onejob/career_intent \
  onejob/career_targets \
  onejob/career_context
git commit -m "test: verify career context failure semantics"
```

Again inspect the staged file list before commit and avoid unrelated changes.

---

### Task 15: Prove the full Slice 3 acceptance scenario and complete release verification

**Files:**
- Modify: `tests/test_career_context_integration.py`
- Modify documentation only if implementation names differ from the approved spec without changing semantics
- No cleanup/refactor outside Slice 3

**Interfaces:**
- Consumes: all Slice 3 components
- Produces: one end-to-end acceptance test and a verified release-ready feature branch

- [ ] **Step 1: Add the acceptance scenario test**

Create one explicit end-to-end test that proves:

```text
Career Twin exists
→ user creates Intent v1
→ user creates Target v1
→ user creates Intent v2
→ target compatibility is revalidated
→ job is routed deterministically
→ Intent + Target resolve
→ explicit HARD exception rules are respected
→ consequential ResolvedTargetView materializes
→ HARD/STRONG/SOFT constraints evaluate
→ UNKNOWN remains UNKNOWN where data is missing
→ EvaluationContext reaches matching adapter
→ policy outranks similarity
→ later Intent/Target edits do not mutate past view
```

The test must assert exact version IDs/fingerprints/provenance at key boundaries rather than only asserting HTTP 200.

- [ ] **Step 2: Run the acceptance test alone**

```bash
python -m pytest \
  tests/test_career_context_integration.py \
  -q
```

Expected: all integration cases pass.

- [ ] **Step 3: Run all Slice 3 tests together**

Run:

```bash
python -m pytest \
  tests/test_career_intent_ontology.py \
  tests/test_career_intent_validation.py \
  tests/test_career_intent_repositories.py \
  tests/test_career_intent_commands.py \
  tests/test_career_intent_suggestions.py \
  tests/test_career_targets_repositories.py \
  tests/test_career_target_resolution.py \
  tests/test_career_target_compatibility.py \
  tests/test_career_target_routing.py \
  tests/test_career_context_policy.py \
  tests/test_career_context_snapshots.py \
  tests/test_career_context_integration.py \
  tests/test_career_context_security.py \
  tests/test_career_context_api.py \
  tests/test_career_context_failures.py -q
```

Expected: zero failures.

- [ ] **Step 4: Run the full regression suite**

Run:

```bash
python -m pytest -q
```

Expected: zero failures. Do not claim completion based on earlier focused test runs.

- [ ] **Step 5: Run diff hygiene**

```bash
git diff --check
git status --short
```

Expected:
- `git diff --check` has no output;
- only the planned acceptance-test/documentation changes remain if not committed yet.

- [ ] **Step 6: Commit final acceptance coverage**

If Task 15 changed tests/docs:

```bash
git add tests/test_career_context_integration.py
git commit -m "test: prove career context vertical slice"
```

If there are no changes because acceptance coverage already exists, do not create an empty commit.

- [ ] **Step 7: Run fresh post-commit release verification**

Run all four commands fresh:

```bash
python -m pytest -q
git diff --check
git status --short
git log --oneline --decorate -20
```

Required:
- pytest: zero failures;
- diff check: clean;
- working tree: clean;
- branch: `feature/career-twin-v2-slice-3`.

- [ ] **Step 8: Collect PR stats**

Run:

```bash
git rev-list --count main..HEAD
git diff --stat main...HEAD
git diff --shortstat main...HEAD
git rev-parse HEAD
```

Record exact:
- HEAD SHA;
- commit count vs `main`;
- changed files;
- insertions/deletions.

- [ ] **Step 9: Push only after verification passes**

Run:

```bash
git push -u origin feature/career-twin-v2-slice-3
```

If authentication fails, report the auth failure and STOP. Do not claim the branch is remotely ready.

- [ ] **Step 10: Use this PR title**

```text
feat: add Career Intent and contextual target evaluation
```

- [ ] **Step 11: Use a PR body covering these points**

```markdown
## Summary
- adds immutable versioned Career Intent with typed HARD/STRONG/SOFT statements
- adds stable Saved Career Targets with immutable versions and explicit HARD exception semantics
- adds target compatibility quarantine and deterministic explainable routing
- adds immutable content-addressed ResolvedTargetView snapshots
- adds three-valued policy evaluation where UNKNOWN remains first-class
- integrates contextual policy with existing matching through EvaluationContext instead of rewriting matching
- adds website-ready safe APIs, idempotency, optimistic concurrency, authorization, and failure semantics

## Safety / invariants
- facts remain separate from preferences
- AI/inference cannot create authoritative HARD policy
- matching cannot override HARD policy
- ambiguous routing abstains
- stale/incompatible targets do not auto-route
- contextual subsystem failure does not silently fall back to legacy matching
- past evaluations remain reproducible and immutable

## Compatibility
- legacy matching remains unchanged when no Career Intent is configured
- Career Twin Slice 1/2 behavior is preserved

## Verification
Insert the exact fresh final line produced by `python -m pytest -q`.
- `git diff --check`: clean
- working tree: clean
```

When composing the actual PR body, copy the exact fresh pytest result from Step 7 into the Verification section. Do not estimate or reuse an earlier pass count.

- [ ] **Step 12: Stop**

Do not begin Slice 4 in this branch.

---

## Plan Self-Review Checklist

The executor does not need to repeat this design review; it is included to make the implementation boundaries explicit.

**Spec coverage**
- Career Intent immutable versions: Tasks 1–4.
- Typed ontology/cardinality/operators/strictness: Tasks 1, 3, 5.
- Temporal scope: Tasks 1, 3, 5, 9.
- HARD/STRONG/SOFT: Tasks 1, 5, 10.
- Explicit HARD exceptions: Task 5.
- Contradiction-aware validation: Task 3.
- Stable target identity + immutable versions: Tasks 2, 5.
- Live inheritance + compatibility quarantine: Tasks 5–6.
- Intent suggestions + suppression: Task 7.
- Deterministic routing + ambiguity + UNSCOPED: Task 8.
- Primary target only / alternatives non-contaminating: Tasks 8–9.
- Immutable snapshots + content addressing: Task 9.
- Three-valued policy / unknown policy: Task 10.
- EvaluationContext + matching adapter: Task 11.
- Safe API / errors / concurrency / idempotency: Tasks 4, 5, 12.
- Ownership / actor authority / privacy: Task 13.
- Event/outbox and failure semantics: Tasks 4–7, 14.
- Legacy compatibility / no silent failure fallback: Tasks 11–12, 14.
- Full acceptance and regression: Task 15.

**Implementation discipline**
- No matching-engine rewrite.
- No arbitrary policy DSL.
- No Career Twin fact duplication.
- No hidden AI authority.
- No silent target selection under ambiguity.
- No silent fallback on contextual technical failure.
- No mutable historical versions.
- No claim of completion without fresh Task 15 verification.

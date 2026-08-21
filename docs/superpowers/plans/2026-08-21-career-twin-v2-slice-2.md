# Career Twin v2 — Slice 2 Implementation Plan

> **For agentic workers:** Implement task-by-task using TDD: RED -> GREEN -> focused regression -> full regression -> commit. Do not skip tasks or weaken architectural invariants. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn the Career Twin canonical core (Slice 1) into a controlled intake + review system: universal suggestion intake, staged candidate entities, atomic suggestions with a two-axis state machine, deterministic entity resolution, value-relationship classification, duplicate detection, conflict sets, suppression memory, direct fact entry, idempotency, optimistic concurrency, transactional approval/rejection, and a safe website-ready API.

**Spec:** `docs/superpowers/specs/2026-08-21-career-twin-v2-slice-2-design.md`

**Tech Stack:** Python 3.11+, Pydantic 2.8+, FastAPI 0.115+, sqlite3 stdlib, pytest 8+.

## Global Constraints / Invariants

- Sources may suggest; only explicit authorized user intent changes canonical truth.
- Canonical changes continue to pass through `CareerTwinCommandService` (or a transaction-safe extension of the same authority boundary). No second canonical write path.
- `APPROVED` is written only after the canonical claim operation succeeds inside the same transaction.
- Rejection/suppression are never projected as career facts and stay out of the Claim Ledger.
- Candidate ids are never treated as canonical entity ids.
- Unknown != false; unscored != low confidence; `INDEPENDENCE_UNKNOWN` != independent.
- Repositories MUST NOT expose a generic state mutator that allows invalid decision/disposition combinations.
- No raw sensitive payloads copied into suggestion tables.
- Forward-only migrations; existing migrations never edited; no historical claim rewritten.
- Existing Slice 1 / Trust Engine tests remain green.

## Module Layout (per spec §23)

```text
onejob/career_twin/
  intake.py         # source-agnostic intake requests + orchestration
  suggestions.py    # suggestion models / two-axis state machine / commands
  candidates.py     # candidate staging + promotion lifecycle
  resolution.py     # deterministic entity + value resolution / assessments
  conflicts.py      # conflict creation, clustering, resolution semantics
  suppression.py    # rejection/suppression matching + lifting
  service.py        # canonical authority, extended transaction-safely
  repositories.py   # focused persistence
  models.py / events.py / ontology.py / projection.py (existing)
```

---

### Task 1: Suggestion two-axis state machine + core suggestion/candidate/disposition enums and models

**Files:**
- Create: `onejob/career_twin/suggestions.py`
- Create: `onejob/career_twin/candidates.py`
- Test: `tests/test_suggestion_state_machine.py`

**Produces:** `DecisionState`, `Disposition`, `SuggestionAction`, `AtomicSuggestion`, `InvalidSuggestionTransition`, `transition()`; `CandidateLifecycle`, `CandidateEntity`, `InvalidCandidateTransition`, `candidate_transition()`.

**Invariants enforced here:**
- Decision and disposition are separate axes (spec §6.3, §7).
- `APPROVED` is only reachable via `APPROVE` / `ACCEPT_ALTERNATIVE` / `EDIT_AND_ACCEPT`.
- `KEEP_CURRENT` with suppression policy -> `REJECTED + SUPPRESSED`.
- `DEFER` leaves `PENDING + CONFLICT` unchanged.
- Duplicate classification -> `PENDING + SUPPRESSED` (not user-rejected).
- Materially-new evidence reopens `PENDING + SUPPRESSED` -> `PENDING + READY|CONFLICT`.
- Invalid combinations raise `InvalidSuggestionTransition`; no generic mutator.
- `candidate_id` is a distinct staging type from canonical `entity_id`.
- Candidate lifecycle: `STAGED -> LINKED|PROMOTED|REJECTED|SUPERSEDED` per spec §6.2.

**Steps:**
- [ ] Step 1: Write failing `tests/test_suggestion_state_machine.py` covering allowed + rejected transitions and candidate lifecycle.
- [ ] Step 2: Run tests -> RED (import failure).
- [ ] Step 3: Implement `suggestions.py` + `candidates.py` (pure domain, no persistence).
- [ ] Step 4: Run new test -> GREEN.
- [ ] Step 5: Focused regression on `tests/test_career_*` -> green.
- [ ] Step 6: Commit.

---

### Task 2: Slice 2 forward-only schema migration

**Files:**
- Create: `onejob/persistence/migrations/005_career_twin_suggestions.sql`
- Test: `tests/test_career_twin_slice2_migration.py`

**Produces tables:** `career_suggestion_batches`, `career_candidate_entities`, `career_atomic_suggestions`, `career_suggestion_evidence`, `career_entity_resolutions`, `career_conflict_sets`, `career_conflict_suggestions`, `career_suppression_records`, `career_idempotency_keys`.

**Invariants:** old DB migrates forward; fresh DB reaches same schema; idempotent under runner; no historical claim rewritten.

- [ ] RED migration test -> implement SQL -> GREEN -> focused regression -> commit.

---

### Task 3: Slice 2 repositories

**Files:** extend `onejob/career_twin/repositories.py`; Test: `tests/test_suggestion_repositories.py`.

Focused repositories for batches, candidates, suggestions, suggestion-evidence links, resolutions, conflicts, conflict-suggestion links, suppression, idempotency. No generic state mutator exposed. RED -> GREEN -> regression -> commit.

---

### Task 4: Deterministic entity resolution v1 (entity-type-aware, explainable, fail-safe)

**Files:** Create `onejob/career_twin/resolution.py`; Test: `tests/test_entity_resolution.py`.

`resolve(candidate, canonical_entities) -> EntityResolutionAssessment` with bands HIGH/MEDIUM/LOW/UNKNOWN, reasons/warnings, `algorithm_version`. Hard contradiction outranks aggregate similarity. Per-entity-type resolvers. HIGH links routing only, never approves. RED -> GREEN -> regression -> commit.

---

### Task 5: Value relationship classification + duplicate detection

**Files:** extend `resolution.py`; Test: `tests/test_value_relationship.py`.

Relationships IDENTICAL/EQUIVALENT/COMPATIBLE/MORE_SPECIFIC/LESS_SPECIFIC/CONFLICTING/UNRELATED/UNKNOWN consulting ontology cardinality. Duplicate = same resolved entity + predicate + normalized value. RED -> GREEN -> regression -> commit.

---

### Task 6: Universal intake contract + batch/candidate/suggestion creation

**Files:** Create `onejob/career_twin/intake.py`; Test: `tests/test_intake.py`.

`USER_INPUT` and `LEGACY_PROFILE` intake producing SuggestionBatch + CandidateEntity + AtomicSuggestion[] without writing canonical truth. Deterministic fingerprints. RED -> GREEN -> regression -> commit.

---

### Task 7: Suppression policy + fingerprints

**Files:** Create `onejob/career_twin/suppression.py`; Test: `tests/test_suppression.py`.

SOFT/STRONG semantics; deterministic fingerprint matching; materially-new independent evidence reopens SOFT. RED -> GREEN -> regression -> commit.

---

### Task 8: Conflict creation + candidate-value clustering

**Files:** Create `onejob/career_twin/conflicts.py`; Test: `tests/test_conflicts.py`.

ConflictSet only for genuinely incompatible cardinality-ONE alternatives; equivalent suggestions cluster preserving provenance; evidence-family counts preferred over raw source counts. RED -> GREEN -> regression -> commit.

---

### Task 9: Idempotency + optimistic concurrency infrastructure

**Files:** extend `service.py`/`repositories.py`; Test: `tests/test_idempotency_concurrency.py`.

Idempotency key store (key/request_fingerprint/result_reference); same key+same request returns original; same key+different request -> IdempotencyConflict. Stale version/claim rejection. RED -> GREEN -> regression -> commit.

---

### Task 10: ApproveSuggestion / RejectSuggestion commands (transactional)

**Files:** extend `service.py`; Test: `tests/test_suggestion_commands.py` + failure injection.

Atomic approval (entity resolve/link/promote -> canonical claim/supersession -> evidence link -> suggestion decision -> events/outbox -> idempotency) with full rollback on injected failure. edited_value keeps suggestion immutable. Rejection records suppression optionally, stays out of ledger. RED -> GREEN -> regression -> commit.

---

### Task 11: ResolveConflict / LiftSuppression / SubmitDirectFact commands

**Files:** extend `service.py`, `intake.py`; Test: `tests/test_conflict_directfact_commands.py`.

KEEP_CURRENT/ACCEPT_ALTERNATIVE/EDIT_AND_ACCEPT/DEFER; direct fact entry with `entity_intent=CREATE_NEW|EDIT_EXISTING`, owner-authorized actor context, atomic canonical write, no double confirmation. RED -> GREEN -> regression -> commit.

---

### Task 12: Safe website-ready API + error taxonomy + privacy tests

**Files:** extend `onejob/api.py`; Test: `tests/test_career_twin_slice2_api.py`.

Read/write endpoints per spec §20; error taxonomy -> HTTP mapping §21; responses expose safe explainability only, never raw payloads/secrets/stack traces. RED -> GREEN -> full regression -> commit.

---

### Task 13: Full regression + acceptance criteria verification

Run the whole suite; verify §25 acceptance criteria; commit any final fixes.

# Career Twin v2 Slice 3 — Career Intent, Saved Career Targets, and Contextual Evaluation Design

**Date:** 2026-08-21  
**Status:** Design approved; awaiting written-spec review  
**Repository target:** `bayz-dik/GaweYuk`  
**Intended spec path:** `docs/superpowers/specs/2026-08-21-career-twin-v2-slice-3-career-intent-target-context-design.md`

## 1. Purpose

Career Twin Slice 1 established the canonical immutable factual ledger. Slice 2 established candidate entities, atomic suggestions, conflict handling, explicit approval/rejection, suppression, and transactional workflow APIs.

Slice 3 adds the context layer that answers a different question:

- **Career Twin:** what is true about the candidate?
- **Career Intent:** what does the candidate want or require now?
- **Saved Career Target:** what specific career direction is the candidate pursuing?
- **ResolvedTargetView:** what intent and target rules apply to this particular evaluation?
- **EvaluationContext:** what stable contextual contract should matching consume?

The goal is to make GaweYuk capable of evaluating the same candidate differently for different career goals without duplicating candidate facts, silently modifying user intent, or allowing similarity scores to override user policy.

The core flow is:

```text
Career Twin facts
        +
Active Career Intent Version
        +
Saved Career Target Version
        ↓
Target Routing
        ↓
Intent + Target Resolution
        ↓
Contradiction / Compatibility Validation
        ↓
ResolvedTargetView
        ↓
Constraint Evaluation
        ↓
EvaluationContext Adapter
        ↓
Existing Matching Engine
```

This is a **vertical integration slice**: it implements the new intent/target/context foundations and proves them end-to-end through a controlled adapter into the existing matching system. It does not rewrite the entire matching engine.

---

## 2. Design Principles

Slice 3 is governed by these principles:

1. **Fact and intent are separate authorities.**
   A statement such as “I have forklift certification” belongs to Career Twin. A statement such as “I prefer warehouse work” belongs to Career Intent.

2. **User authority outranks inference.**
   AI, behavior, matching, and system processes may suggest preferences but may not silently activate them or create hard constraints.

3. **Hard policy outranks similarity.**
   A 99% skill match cannot override a known hard-policy violation.

4. **Uncertainty is first-class.**
   `UNKNOWN` is neither `SATISFIED` nor `VIOLATED`.

5. **History never mutates.**
   Intent versions, target versions, and consequential evaluation snapshots are immutable.

6. **Live definitions, immutable decisions.**
   Saved targets may inherit the current active Career Intent for future evaluations, while past evaluations retain the exact versions and resolved context used at the time.

7. **Explainability is generated from provenance, not reconstructed later.**
   Routing, overrides, exceptions, policy results, and algorithm versions must be recorded at the time the evaluation is produced.

8. **Deterministic core first.**
   Routing, resolution, strictness comparison, and policy evaluation are versioned and reproducible. AI may provide future semantic signals but may not become final decision authority.

9. **Fail safe rather than fabricate certainty.**
   Ambiguity, stale compatibility, unresolved context, and system failures are not silently converted into success.

10. **No silent legacy fallback when contextual policy exists.**
    Legacy matching remains a legitimate compatibility path only when no Career Intent is configured.

---

## 3. Scope

### 3.1 In scope

Slice 3 implements:

- stable Career Intent identity;
- immutable Career Intent versions;
- typed atomic Intent Statements;
- deterministic Intent Ontology;
- hard/strong/soft policy strengths;
- optional temporal scope;
- typed merge and strictness semantics;
- contradiction-aware validation;
- stable Saved Career Target identity;
- immutable Saved Career Target versions;
- target lifecycle;
- target overrides and explicit hard-policy exceptions;
- target compatibility assessments against the active Intent version;
- quarantine of stale/incompatible targets;
- intent suggestion contracts and user-controlled promotion;
- deterministic target routing;
- ambiguity gates and abstention;
- unscoped evaluation when no target is sufficiently relevant;
- primary target plus counterfactual alternatives;
- immutable `ResolvedTargetView` snapshots at consequential decision boundaries;
- content-addressed snapshot reuse;
- three-valued constraint evaluation;
- explicit strong-preference trade-offs and soft-preference signals;
- stable `EvaluationContext` contract;
- adapter-based integration with existing matching;
- command-oriented write APIs;
- idempotency, optimistic concurrency, ownership, audit events, and outbox;
- failure-injection, security, compatibility, and regression tests.

### 3.2 Explicit non-goals

Slice 3 does **not** implement:

- a full matching-engine rewrite;
- job ingestion redesign;
- recruiter-facing disclosure logic;
- automatic job applications;
- LLM/AI authority over hard policy;
- a full behavioral-learning engine;
- embedding or vector infrastructure;
- arbitrary user-authored expression languages;
- mandatory background workers;
- frontend visual redesign;
- duplication of Career Twin facts into targets;
- silent generation of new targets from jobs.

---

## 4. Architecture and Boundaries

### 4.1 Primary modules

The conceptual module boundaries are:

```text
career_intent/
├── ontology
├── models
├── repository
├── commands
├── validation
└── suggestions

career_targets/
├── models
├── repository
├── commands
├── compatibility
└── routing

career_context/
├── resolver
├── snapshots
├── policy_evaluator
└── matching_adapter
```

The implementation plan may adapt exact file locations to existing repository conventions, but the dependency direction must remain:

```text
Career Twin ─────┐
Career Intent ───┼──> Context Resolution ──> Matching
Career Target ───┘
```

Disallowed dependency directions:

```text
Matching ─X─> mutate Intent
Matching ─X─> mutate Target
Router   ─X─> mutate truth
AI       ─X─> authoritative HARD policy
```

### 4.2 Authoritative write path

All authoritative mutations pass through transactional commands:

```text
Command
  ↓
actor authorization
  ↓
idempotency reservation/check
  ↓
optimistic concurrency
  ↓
domain validation
  ↓
transaction
  ├─ immutable version/write
  ├─ active pointer/lifecycle change
  ├─ audit event
  └─ outbox
  ↓
commit
```

### 4.3 Evaluation path

```text
Job Context
  +
Career Twin projection
  +
Active Career Intent
  ↓
Eligible Saved Targets
  ↓
Deterministic Target Router
  ├─ clear winner → TARGETED
  ├─ ambiguous → USER_SELECTION / REVIEW
  └─ no relevant target → UNSCOPED
  ↓
Resolver
  ↓
Contradiction / compatibility validation
  ↓
ResolvedTargetView
  ↓
Constraint Evaluator
  ↓
EvaluationContext
  ↓
Existing Matching Adapter
```

### 4.4 Hard boundaries

- Career Intent must not write Career Twin facts.
- Saved Career Targets must not contain copied candidate skills, experiences, or other canonical facts.
- Target routing may rank, abstain, and explain; it may not edit targets or preferences.
- Resolution derives effective policy; it does not compute similarity.
- Constraint evaluation determines policy status; it does not compute matching score.
- Matching cannot override policy-gate results.
- AI/inference may suggest; it may not create hard authority.

---

## 5. Career Intent Aggregate

### 5.1 Stable identity

```text
CareerIntent
├── intent_id
├── twin_id
├── active_version_id
├── created_at
└── created_by_actor_id
```

A candidate has one logical Career Intent aggregate whose active pointer may move between immutable versions.

### 5.2 Immutable versions

```text
CareerIntentVersion
├── intent_version_id
├── intent_id
├── version_number
├── supersedes_version_id?
├── created_by_actor_id
├── created_at
└── input_fingerprint
```

Editing intent means:

```text
edit intent
→ create new version
→ validate
→ activate new version
→ preserve old version
```

No previous version is modified in place.

`CareerIntent.active_version_id` is the single authority for which immutable version is active. Slice 3 must not maintain a second mutable per-version "active" flag that could disagree with the aggregate pointer. A failed validation/activation transaction rolls back instead of leaving a partially active version.

### 5.3 Intent Statements

```text
IntentStatement
├── statement_id
├── intent_version_id
├── predicate
├── operator
├── value
├── value_type
├── strength
│   ├── HARD_CONSTRAINT
│   ├── STRONG_PREFERENCE
│   └── SOFT_PREFERENCE
├── effective_from?
├── expires_at?
├── unknown_policy?
└── provenance
```

Intent is represented as atomic typed statements rather than one large JSON blob or a fixed schema column for every preference.

---

## 6. Typed Intent Ontology

Slice 3 must not introduce an arbitrary expression DSL.

Each supported intent predicate is defined by a deterministic registry:

```text
IntentPredicateDefinition
├── predicate
├── value_type
├── cardinality
│   ├── ONE
│   └── MANY
├── allowed_strengths
├── allowed_operators
├── merge_policy
├── strictness_direction?
├── temporal_allowed
├── unknown_policy_allowed
└── validation_rules
```

Examples:

```text
COMPENSATION.MIN_SALARY
value_type = MONEY
cardinality = ONE
operator = GTE
strictness_direction = HIGHER_IS_STRICTER
```

```text
COMMUTE.MAX_KM
value_type = DISTANCE
cardinality = ONE
operator = LTE
strictness_direction = LOWER_IS_STRICTER
```

```text
LOCATION.PREFERRED
value_type = LOCATION_REF_OR_TEXT
cardinality = MANY
merge_policy = SET
```

The ontology exists so the resolver can understand semantics such as strictness, cardinality, valid merge operations, and contradiction rules instead of merely copying values.

---

## 7. Constraint Strength Semantics

### 7.1 HARD_CONSTRAINT

A hard constraint represents a user policy that may block or suspend a recommendation.

Known violation:

```text
HARD + VIOLATED
→ BLOCK
```

Unknown information follows the predicate/statement's `unknown_policy`.

### 7.2 STRONG_PREFERENCE

A strong preference may be violated only as an explicit trade-off:

```text
STRONG + VIOLATED
→ may continue
→ trade-off must be surfaced
```

It does not silently become a hard block.

### 7.3 SOFT_PREFERENCE

A soft preference affects ranking and explanation only:

```text
SOFT + VIOLATED
→ ranking signal / penalty
```

### 7.4 Precedence

```text
HARD policy
> hard verification requirements
> STRONG trade-offs
> SOFT ranking preferences
> similarity score
```

---

## 8. Temporal Intent

Temporal scope is optional.

Default behavior:

```text
effective_from = version activation time
expires_at = null
```

A statement may explicitly define:

```text
effective_from?
expires_at?
temporal_reason?
```

Evaluation-time semantics:

```text
effective_from > evaluated_at
→ FUTURE

expires_at <= evaluated_at
→ EXPIRED

otherwise
→ ACTIVE
```

Rules:

```text
EXPIRED ≠ DELETED
FUTURE ≠ ACTIVE
```

Historical statements remain available for audit.

Temporal activation is evaluated using the exact evaluation timestamp and is included in snapshot fingerprinting/provenance.

---

## 9. Saved Career Target Aggregate

### 9.1 Stable target identity

```text
SavedCareerTarget
├── target_id
├── twin_id
├── active_version_id
├── lifecycle
│   ├── ACTIVE
│   ├── PAUSED
│   └── ARCHIVED
├── created_at
└── created_by_actor_id
```

### 9.2 Immutable target versions

```text
SavedCareerTargetVersion
├── target_version_id
├── target_id
├── version_number
├── supersedes_version_id?
├── display_name
├── role_focus[]
├── domain_focus[]
├── explicit_keywords[]
├── scope_definition
├── created_at
└── input_fingerprint
```

Editing a target creates a new version and moves the active pointer.

### 9.3 Target does not copy facts

A target may refer to role/domain concepts and store target policy overrides, but it must never duplicate canonical facts such as candidate experience, skills, certifications, or education.

---

## 10. Layered Intent Inheritance and Overrides

A Saved Career Target is a declarative recipe:

```text
Active Career Intent
+
Target-specific overrides
=
Effective target policy
```

New evaluations use the current active Career Intent unless the target is incompatible with it.

### 10.1 Override operations

```text
INHERIT
REPLACE
ADD
REMOVE
CLEAR
EXPLICIT_EXCEPTION
```

A target override is stored atomically:

```text
TargetIntentOverride
├── override_id
├── target_version_id
├── predicate
├── operation
├── value?
├── strength?
├── effective_from?
├── expires_at?
├── overrides_statement_id?
└── explicit_exception_authority?
```

### 10.2 Cardinality and merge semantics

The ontology determines valid merge behavior.

For multi-value statements:

```text
Global preferred locations:
[Cikarang, Bekasi, Karawang]

Target:
REMOVE Karawang

Resolved:
[Cikarang, Bekasi]
```

For scalar constraints, the resolver compares semantic strictness rather than blindly replacing values.

---

## 11. Explicit Hard-Constraint Exceptions

Targets may tighten inherited hard constraints normally.

Examples:

```text
MIN_SALARY:
6M → 7M
= tighter
= allowed
```

```text
MAX_COMMUTE:
25km → 15km
= tighter
= allowed
```

Weakening or removing a global hard constraint requires an explicit user-authorized exception:

```text
MIN_SALARY:
6M → 5M
= weaker
→ EXPLICIT_EXCEPTION required
```

```text
MAX_COMMUTE:
25km → 40km
= weaker
→ EXPLICIT_EXCEPTION required
```

Normal `REPLACE`, `CLEAR`, or `REMOVE` must not weaken a hard constraint.

Changing strength is also semantic policy change. A target may explicitly strengthen a local rule (for example `SOFT → STRONG` or `STRONG → HARD`) through an authorized user target-version command. Weakening an inherited `HARD` strength or value requires `EXPLICIT_EXCEPTION`. Inference and background actors cannot perform either hard-policy promotion or hard-policy weakening on the user's behalf.

An explicit exception requires:

- authorized user actor;
- target-specific scope;
- exact inherited statement being overridden;
- expected target/intent version context;
- explicit exception operation.

AI, matching, background processes, and system inference may not authorize hard exceptions.

---

## 12. Contradiction-Aware Validation

The system must validate resolved policy for internal consistency.

Validation outcomes:

```text
VALID
VALID_WITH_TENSIONS
UNSATISFIABLE
```

Examples:

```text
MIN_SALARY >= 7M HARD
SALARY_CAP <= 6M HARD
→ UNSATISFIABLE
```

```text
REMOTE preferred STRONG
OFFICE_COLLABORATION preferred SOFT
→ VALID_WITH_TENSIONS
```

Rules:

- impossible HARD-vs-HARD combinations block activation/use;
- HARD outranks conflicting SOFT policy during evaluation without deleting the SOFT preference;
- incompatible STRONG preferences may create a reviewable tension;
- SOFT preferences may coexist as ranking trade-offs.

An internally unsatisfiable Career Intent version must not become active.

---

## 13. Intent Activation and Dependent Target Revalidation

A valid new Career Intent version may activate even if it makes existing targets stale or incompatible.

Activation flow:

```text
Create Intent vN
  ↓
validate intent itself
  ├─ invalid/unsatisfiable → activation rejected
  └─ valid
       ↓
       activate vN
       ↓
       revalidate dependent target versions
```

A stale dependent target must not veto a valid global user intent change.

Target compatibility outcomes:

```text
VALID
NEEDS_REVIEW
UNSATISFIABLE
```

### 13.1 Quarantine rule

- `VALID` targets may participate in auto-routing.
- `NEEDS_REVIEW` targets remain stored but are excluded from auto-routing.
- `UNSATISFIABLE` targets remain stored for audit/history but are excluded from new evaluations.

No target version is silently repaired.

A user can resolve a quarantined target by:

- accepting new inherited policy;
- creating an explicit exception;
- creating a revised target version;
- pausing or archiving the target.

---

## 14. Target Compatibility Assessment

Compatibility is an assessment of a target version against a specific Intent version:

```text
TargetCompatibility
├── compatibility_id
├── target_id
├── target_version_id
├── against_intent_version_id
├── status
├── reasons[]
├── checked_at
└── validator_version
```

Compatibility status is not a mutation of the target version.

Before routing, a target must have a valid compatibility assessment for the current active Intent version. A stale compatibility assessment makes the target ineligible until revalidated.

---

## 15. Intent Suggestions

Behavioral observations, AI inference, and outcome learning may produce suggestions, not authoritative intent changes.

```text
behavior / AI / outcomes
       ↓
IntentSuggestion
       ↓
user review
       ├─ ACCEPT
       ├─ EDIT_AND_ACCEPT
       └─ REJECT
       ↓
new CareerIntentVersion if accepted
```

Model:

```text
IntentSuggestion
├── suggestion_id
├── intent_id
├── predicate
├── proposed_value
├── proposed_strength
├── evidence[]
├── confidence?
├── source
├── decision_state
│   ├── PENDING
│   ├── ACCEPTED
│   ├── REJECTED
│   └── SUPERSEDED
├── created_at
└── fingerprint
```

Possible sources include:

```text
USER_PATTERN
OUTCOME_LEARNING
AI_INFERENCE
SYSTEM_INSIGHT
```

Rules:

- inference may suggest SOFT;
- inference may suggest STRONG for review;
- inference may never directly activate HARD;
- only explicit user authority may promote a preference to HARD;
- rejected repeated suggestions may use a separate suppression memory;
- intent suggestions remain separate from Slice 2 Career Fact suggestions.

---

## 16. Target Routing v1

Target routing answers:

> “Which user-defined career target is this job most relevant to?”

It does **not** answer:

> “How good is this job?”

Routing and matching are separate stages.

### 16.1 Eligibility gate

Auto-routing considers only targets that satisfy:

```text
lifecycle = ACTIVE
compatibility = VALID for active intent version
active target version exists
ownership valid
compatibility assessment not stale
```

`PAUSED`, `ARCHIVED`, `NEEDS_REVIEW`, `UNSATISFIABLE`, or stale targets are excluded from auto-routing.

### 16.2 Deterministic applicability assessment

Each eligible target receives a versioned assessment:

```text
TargetApplicabilityAssessment
├── assessment_id
├── twin_id
├── job_context_fingerprint
├── intent_version_id
├── target_version_id
├── eligibility
├── applicability_score
├── confidence_band
├── signals[]
├── reasons[]
├── router_version
└── created_at
```

Routing v1 may use deterministic signals such as:

- role-family compatibility;
- domain compatibility;
- location relevance;
- employment-type relevance;
- explicit target keywords;
- explicit target scope match.

Each signal records type, value, weight, reason, and source.

Thresholds and ambiguity margins must be versioned configuration, not hidden magic numbers.

### 16.3 Routing outcomes

```text
USER_SELECTED
AUTO_ROUTED
AMBIGUOUS
UNSCOPED
```

Auto-route requires:

```text
winner_score >= minimum_threshold
AND
winner_margin >= ambiguity_margin
```

Example:

```text
0.85 vs 0.51
→ AUTO_ROUTED
```

```text
0.85 vs 0.83
→ AMBIGUOUS
```

```text
0.31 vs 0.20
→ UNSCOPED
```

### 16.4 User selection precedence

Explicit user target selection wins over automatic routing.

The routing record uses:

```text
method = USER_SELECTED
```

However, user selection cannot make an unsatisfiable target valid. An invalid target must be repaired/revised first.

### 16.5 Ambiguity gate

When routing is ambiguous:

```text
AMBIGUOUS
→ USER_SELECTION / REVIEW
```

The system may explain the competing targets but must not secretly choose the highest score.

### 16.6 No-target behavior

If no target is sufficiently relevant:

```text
UNSCOPED
```

The system evaluates using the global active Career Intent only.

Hard global policy remains active.

The router must not force the nearest target merely because one has the highest low score.

---

## 17. Primary Evaluation and Counterfactual Alternatives

One official evaluation uses exactly one contextual target state:

```text
ONE evaluation
=
ONE intent version
+
ZERO OR ONE target version
+
ONE ResolvedTargetView
```

Alternative targets may be surfaced as counterfactual assessments:

```text
AlternativeTargetAssessment
├── target_version_id
├── applicability_score
├── likely_policy_difference
└── reason
```

Alternatives must never contaminate the primary evaluation.

Disallowed:

```text
salary policy from Target A
+
location policy from Target B
+
role preference from Target C
```

If the user explicitly chooses an alternative target, GaweYuk creates a separate evaluation with its own resolved context.

---

## 18. ResolvedTargetView

`ResolvedTargetView` is the immutable contextual snapshot used for consequential evaluation.

```text
ResolvedTargetView
├── resolved_view_id
├── twin_id
├── intent_version_id
├── target_version_id?
├── routing_decision_id?
├── scope
│   ├── TARGETED
│   └── UNSCOPED
├── resolved_statements[]
├── applied_overrides[]
├── explicit_exceptions[]
├── active_temporal_statements[]
├── tensions[]
├── validation_status
├── resolver_version
├── evaluated_at
└── input_fingerprint
```

Resolution order is fixed:

```text
Active Career Intent Version
  ↓
filter by evaluation-time temporal validity
  ↓
load selected target version if targeted
  ↓
apply typed overrides
  ↓
apply explicit exceptions
  ↓
validate contradictions
  ↓
produce ResolvedTargetView
```

For an unscoped evaluation:

```text
target_version_id = null
scope = UNSCOPED
```

No synthetic/dummy target is created.

---

## 19. Snapshot Materialization Boundary

Discovery and rough ranking may use ephemeral resolved context.

A permanent immutable `ResolvedTargetView` is materialized at consequential/user-visible boundaries, including at minimum:

- explicit user job evaluation;
- job-detail contextual evaluation;
- apply/skip/block decision;
- application-answer generation.

This avoids persisting a permanent snapshot for every speculative candidate while preserving reproducibility for decisions that matter.

---

## 20. Content-Addressed Snapshot Reuse

Resolved snapshots use a canonical semantic fingerprint.

Inputs include at minimum:

- intent version ID;
- target version ID, if any;
- active temporal state at evaluation time;
- resolved override/exception state;
- relevant job-context fingerprint;
- resolver version.

If canonical inputs are identical:

```text
same fingerprint
→ reuse existing immutable resolved context
```

If any consequential input changes:

```text
Intent version changes
Target version changes
temporal state changes
exception state changes
job context changes
resolver version changes
→ new fingerprint
→ new snapshot
```

Refreshes/retries must not create duplicate semantically identical snapshots.

---

## 21. Three-Valued Constraint Evaluation

Every evaluable constraint produces one of:

```text
SATISFIED
VIOLATED
UNKNOWN
```

`UNKNOWN` is explicitly not equivalent to pass or fail.

Assessment model:

```text
ConstraintAssessment
├── assessment_id
├── resolved_view_id
├── statement_id
├── result
├── observed_value?
├── evidence_status
├── unknown_reason?
├── required_action?
├── reasons[]
└── evaluator_version
```

### 21.1 Hard unknown policy

A hard statement may define:

```text
REQUIRE_VERIFICATION
ALLOW_WITH_WARNING
BLOCK_IF_UNVERIFIED
```

Examples:

```text
MIN_SALARY >= 6M
job salary = UNKNOWN
unknown_policy = REQUIRE_VERIFICATION

→ UNKNOWN
→ REVIEW_REQUIRED
```

A different predicate may require:

```text
UNKNOWN
+ unknown_policy = BLOCK_IF_UNVERIFIED
→ PolicyGateResult.status = BLOCKED
→ reason_code = HARD_UNVERIFIED
```

The underlying `ConstraintAssessment.result` remains `UNKNOWN`; it is not rewritten to `VIOLATED`. This preserves the distinction between a known policy violation and a safety policy that blocks action until verification exists.

---

## 22. Policy Gate Result

Constraint evaluation aggregates to:

```text
PolicyGateResult
├── status
│   ├── ELIGIBLE
│   ├── REVIEW_REQUIRED
│   ├── BLOCKED
│   └── INVALID_CONTEXT
├── hard_violations[]
├── hard_unknowns[]
├── strong_tradeoffs[]
├── soft_signals[]
└── reasons[]
```

Semantics:

```text
HARD + VIOLATED
→ BLOCKED
```

```text
HARD + UNKNOWN + REQUIRE_VERIFICATION
→ REVIEW_REQUIRED

HARD + UNKNOWN + BLOCK_IF_UNVERIFIED
→ BLOCKED with HARD_UNVERIFIED reason
```

```text
STRONG + VIOLATED
→ explicit trade-off
```

```text
SOFT + VIOLATED
→ ranking signal only
```

Full matching should only produce a final-fit recommendation when policy status permits it.

A `REVIEW_REQUIRED` context may expose limited analysis but must not masquerade as a final recommendation.

---

## 23. EvaluationContext Contract

Matching consumes a stable context contract rather than persistence internals:

```text
EvaluationContext
├── career_twin_projection
├── resolved_target_view
├── constraint_assessments[]
├── hard_gate_status
├── strong_preference_signals[]
├── soft_preference_signals[]
├── provenance
└── context_version
```

The adapter maps Slice 3 semantics to the current matching system.

This allows future matching upgrades without changing Career Intent or Saved Career Target persistence.

---

## 24. Existing Matching Integration

Slice 3 uses a controlled compatibility adapter.

### 24.1 No Career Intent configured

```text
No active Career Intent
→ legitimate legacy matching compatibility path
```

### 24.2 Career Intent configured

```text
Career Intent exists
→ contextual evaluation path is authoritative
```

A contextual pipeline failure must not silently fall back to legacy matching.

```text
Intent exists + resolver/router/policy subsystem fails
→ contextual error / review
→ NOT legacy success
```

This prevents infrastructure failure from silently bypassing hard user constraints.

---

## 25. API Design

Write APIs are command-oriented because the domain is versioned and immutable.

Conceptual endpoints:

```text
GET  /api/career-intent
POST /api/career-intent/versions

GET  /api/career-targets
POST /api/career-targets

GET  /api/career-targets/{target_id}
POST /api/career-targets/{target_id}/versions

POST /api/career-targets/{target_id}/pause
POST /api/career-targets/{target_id}/resume
POST /api/career-targets/{target_id}/archive

POST /api/career-context/route
POST /api/career-context/evaluate

GET  /api/career-context/evaluations/{evaluation_id}

GET  /api/career-intent/suggestions
POST /api/career-intent/suggestions/{id}/accept
POST /api/career-intent/suggestions/{id}/reject
POST /api/career-intent/suggestions/{id}/edit-and-accept
```

Exact endpoint names may be adjusted to existing API conventions in the implementation plan, but mutation semantics must remain command-oriented and immutable.

There is no generic endpoint that gives AI authority to set hard preferences or exceptions.

---

## 26. Command Model

Representative commands:

```text
CreateCareerIntentVersionCommand
CreateSavedCareerTargetCommand
ReviseSavedCareerTargetCommand
SetTargetLifecycleCommand
AcceptIntentSuggestionCommand
RejectIntentSuggestionCommand
LiftIntentSuppressionCommand
ResolveTargetCompatibilityCommand
```

Authoritative commands carry:

```text
actor_id
twin_id
idempotency_key
expected_active_version_id?
payload
```

This supports retries, ownership checks, and optimistic concurrency.

---

## 27. Optimistic Concurrency

If two clients edit the same active version:

```text
Tab A expects v8
→ creates v9

Tab B still expects v8
→ STALE_VERSION
```

The stale request is rejected rather than overwriting the new state.

Expected API semantics:

```text
409 Conflict
error_code = STALE_VERSION
```

The response should expose the expected and actual version identifiers where safe.

---

## 28. Idempotency

Retryable commands require an idempotency key.

Rules:

```text
same key + same semantic payload
→ same logical result
```

```text
same key + different semantic payload
→ IDEMPOTENCY_CONFLICT
```

A lost mobile response and retry must not create duplicate intent or target versions.

---

## 29. Actor Authorization

Source trust and actor authority are separate concepts.

```text
USER_ACTOR
→ may create/activate Intent versions
→ may create target versions
→ may authorize explicit hard exceptions
```

```text
SYSTEM_ACTOR
→ may compute compatibility/routing
→ may create suggestions where policy allows
→ may not authorize user hard-policy exceptions
```

```text
AI / INFERENCE
→ may propose
→ may not activate authoritative policy
```

Confidence does not grant authority.

---

## 30. Ownership Security

All reads and writes are scoped through the ownership chain:

```text
resource
→ target/intent/evaluation
→ twin
→ authorized actor
```

Possession of an identifier is insufficient authorization.

Cross-user resource probing should use access-safe not-found behavior where appropriate.

---

## 31. Safe Read Models

API responses must not expose raw persistence internals.

Examples:

Career Intent view:

```text
active_version
statements
temporal_status
tensions
pending_suggestions_count
```

Saved Target view:

```text
target_id
display_name
active_version
lifecycle
compatibility_status
compatibility_reasons
```

Evaluation view:

```text
scope
selected_target
routing_explanation
resolved_preferences
hard_constraints
policy_gate
strong_tradeoffs
soft_signals
matching_result
```

Raw outbox fields, internal hashes, and persistence-only metadata should not leak without a clear product need.

---

## 32. Error Taxonomy

Stable machine-readable domain errors include at minimum:

```text
INVALID_INTENT_STATEMENT
INVALID_TARGET_OVERRIDE
HARD_CONSTRAINT_EXCEPTION_REQUIRED
UNSATISFIABLE_INTENT
TARGET_NEEDS_REVIEW
TARGET_UNSATISFIABLE
TARGET_NOT_ROUTABLE
AMBIGUOUS_TARGET_ROUTING
STALE_VERSION
IDEMPOTENCY_CONFLICT
UNAUTHORIZED_ACTOR
INVALID_TEMPORAL_RANGE
UNKNOWN_PREDICATE
CONTEXT_RESOLUTION_FAILED
POLICY_EVALUATION_FAILED
```

Approximate HTTP mapping:

```text
400 → malformed/domain-invalid input
401/403 → authentication/actor authority
404 → unavailable/not-owned resource
409 → stale/idempotency/state conflict
422 → semantically invalid command
503 → contextual subsystem unavailable
```

Exact mapping should follow the existing API error style when the implementation plan inspects current code.

---

## 33. Domain Uncertainty vs System Failure

Domain outcomes such as:

```text
AMBIGUOUS
UNSCOPED
REVIEW_REQUIRED
BLOCKED
UNKNOWN
```

are valid domain states, not server failures.

Technical failures such as:

```text
database error
resolver crash
corrupt ontology
```

must not be disguised as domain uncertainty.

Rule:

```text
DOMAIN UNCERTAINTY ≠ SYSTEM FAILURE
```

Example:

```text
salary not disclosed
→ UNKNOWN
```

```text
resolver exception
→ CONTEXT_RESOLUTION_FAILED
```

---

## 34. Transaction and Revalidation Semantics

Intent activation itself is authoritative and atomic:

```text
BEGIN
insert immutable CareerIntentVersion
insert statements
validate
move active pointer
append audit event
append outbox record
COMMIT
```

Dependent target compatibility may be recomputed as a deterministic operation without requiring one giant transaction over every target.

Safety rule:

Before a target participates in routing, the router must verify that compatibility is valid for the **current active Intent version**.

Therefore:

```text
stale compatibility
→ target ineligible
```

This remains safe even if future revalidation is asynchronous.

---

## 35. Events and Outbox

Representative events:

```text
CareerIntentVersionCreated
CareerIntentActivated
SavedCareerTargetCreated
SavedCareerTargetVersionCreated
SavedCareerTargetLifecycleChanged
TargetCompatibilityChanged
IntentSuggestionCreated
IntentSuggestionAccepted
IntentSuggestionRejected
ResolvedTargetViewMaterialized
ContextEvaluationCompleted
```

Events/outbox are integration and audit mechanisms, not the authoritative source of truth.

Required authoritative writes and their required event/outbox records must preserve existing transactional guarantees.

---

## 36. Privacy and Disclosure Boundary

Career Intent may contain sensitive decision context such as:

- desired salary;
- willingness to relocate;
- preferred locations;
- availability;
- work-mode preferences.

Internal decision context is not automatically disclosure context.

```text
DECISION CONTEXT ≠ DISCLOSURE CONTEXT
```

A minimum-salary preference used for internal filtering must not automatically become recruiter-facing text, CV content, or public-profile data.

Recruiter-facing disclosure policy is outside Slice 3.

---

## 37. Explainability Requirements

Every consequential contextual evaluation must be able to answer:

- Why was this target selected?
- Was selection explicit, automatic, ambiguous, or unscoped?
- Which Career Intent version was used?
- Which target version was used?
- Which temporal statements were active?
- Which overrides were applied?
- Which explicit hard exceptions were applied?
- Which hard rules were satisfied, violated, or unknown?
- Why did the result become eligible, review-required, blocked, or invalid?
- Which strong trade-offs and soft signals affected matching?
- Which router, resolver, validator, evaluator, and context versions were used?

These answers must derive from stored provenance rather than post-hoc guesses.

---

## 38. Testing Strategy

### 38.1 Ontology unit tests

Prove:

```text
MIN_SALARY higher value = stricter
MAX_COMMUTE lower value = stricter
```

Also test:

- cardinality;
- allowed operators;
- allowed strengths;
- invalid predicate/value combinations;
- invalid temporal support;
- invalid unknown policy configuration.

### 38.2 Temporal tests

Cover:

```text
FUTURE
ACTIVE
EXPIRED
```

including exact boundary timestamps.

### 38.3 Merge and hard-exception tests

Cover:

```text
INHERIT
REPLACE
ADD
REMOVE
CLEAR
EXPLICIT_EXCEPTION
```

Prove that normal overrides may tighten hard constraints but may not weaken them.

Prove that explicit authorized exceptions can weaken a hard rule without mutating the inherited statement.

### 38.4 Contradiction tests

Cover:

- HARD vs HARD impossible;
- HARD vs SOFT;
- STRONG vs STRONG tensions;
- SOFT vs SOFT trade-offs;
- activation rejection for unsatisfiable Intent.

### 38.5 Target compatibility tests

Cover:

- valid target under active Intent;
- Intent activation causing `NEEDS_REVIEW`;
- Intent activation causing `UNSATISFIABLE`;
- quarantined targets excluded from auto-routing;
- stale compatibility assessment excluded from auto-routing;
- historical target version unchanged.

### 38.6 Routing tests

Cover:

- clear winner;
- ambiguous winner;
- unscoped result;
- lifecycle-ineligible target;
- compatibility-ineligible target;
- explicit user target selection;
- invalid explicit target selection;
- deterministic same-input same-result;
- router-version provenance.

### 38.7 Policy tests

Cover:

```text
SATISFIED
VIOLATED
UNKNOWN
```

for HARD, STRONG, and SOFT strengths.

Cover each hard `unknown_policy`.

Prove similarity cannot override hard-policy outcome.

### 38.8 Snapshot tests

Cover:

- consequential boundary creates immutable snapshot;
- same canonical fingerprint reuses snapshot;
- changed Intent version creates new snapshot;
- changed Target version creates new snapshot;
- temporal expiry creates new semantic fingerprint;
- changed resolver version creates new snapshot;
- past snapshot remains unchanged.

### 38.9 Repository tests

Cover:

- immutable version persistence;
- one active version pointer;
- monotonically valid version numbering under repository conventions;
- target active version pointer;
- ownership scoping;
- compatibility persistence;
- snapshot uniqueness by canonical fingerprint where required.

### 38.10 Command tests

Cover:

- actor authorization;
- optimistic concurrency;
- idempotent retry;
- idempotency payload conflict;
- explicit hard-exception authority;
- audit event/outbox atomicity;
- no partial authoritative state on failure.

### 38.11 Intent suggestion tests

Cover:

- AI/system suggestion cannot directly activate Intent;
- suggestion acceptance creates new immutable Intent version;
- edit-and-accept uses user-edited value/strength;
- rejected suggestion does not change Intent;
- inference cannot directly create HARD;
- user may explicitly promote to HARD via authorized command path;
- repeated rejected suggestion can be suppressed without altering Intent history.

### 38.12 Integration tests

Prove the vertical path:

```text
create Career Intent
→ create Saved Career Target
→ route job
→ resolve target + intent
→ materialize ResolvedTargetView
→ evaluate HARD / STRONG / SOFT
→ build EvaluationContext
→ pass through existing matching adapter
```

### 38.13 Compatibility tests

Preserve:

- Career Twin Slice 1 behavior;
- Career Twin Slice 2 behavior;
- legacy profile compatibility;
- current matching behavior when no Career Intent exists;
- current API behavior outside Slice 3 endpoints.

### 38.14 Failure-injection tests

Inject failure:

- after Intent version insert;
- before active pointer move;
- before required event/outbox write;
- during target-version persistence;
- during snapshot materialization.

Expected:

```text
no partial authoritative state
```

### 38.15 Security tests

Prove:

- actor A cannot mutate actor B's Intent/target/evaluation;
- AI actor cannot create/activate a HARD constraint;
- system actor cannot authorize an explicit hard exception;
- tampered target/twin ownership is blocked;
- unauthorized resource probing does not leak protected resource state.

### 38.16 Full regression gate

Before completion:

```text
python -m pytest -q
git diff --check
git status --short
```

Completion requires zero test failures and a clean implementation state according to the established branch workflow.

---

## 39. Required Invariants

1. One active Career Intent version per Career Intent aggregate.
2. Active pointers may move; immutable versions may not mutate.
3. One Saved Career Target has one active target version.
4. Past `ResolvedTargetView` records never re-resolve in place.
5. Target overrides may tighten hard constraints normally.
6. Weakening/removing hard policy requires explicit user-authorized exception semantics.
7. AI/inference cannot directly create hard authority.
8. `NEEDS_REVIEW`, `UNSATISFIABLE`, stale, paused, and archived targets cannot auto-route.
9. Router cannot create or edit targets.
10. `UNKNOWN` cannot masquerade as `SATISFIED`.
11. Matching score cannot override hard-policy results.
12. Career Intent cannot become Career Twin factual truth.
13. Saved targets cannot duplicate canonical candidate facts.
14. Past evaluations always reference the exact context/version used.
15. Explicit user target selection beats auto-routing but cannot make invalid policy valid.
16. One official evaluation uses at most one target version.
17. Alternative targets cannot contaminate primary evaluation.
18. A valid new global Intent may quarantine dependent targets rather than silently rewrite them.
19. A contextual subsystem failure cannot silently downgrade to legacy matching when Career Intent exists.
20. Decision context does not imply recruiter-facing disclosure authority.

---

## 40. Acceptance Scenario

Slice 3 is successful when the following scenario is proven end-to-end:

```text
Candidate has Career Twin
        ↓
User creates Career Intent v1
        ↓
User creates Saved Career Target v1
        ↓
User edits Intent
        ↓
immutable Intent v2 created and activated
        ↓
dependent targets revalidated
        ↓
a job is evaluated
        ↓
router deterministically selects, abstains, or requests selection
        ↓
Intent + selected Target resolve under typed merge semantics
        ↓
hard weakening requires explicit user exception
        ↓
contradictions are validated
        ↓
ResolvedTargetView is materialized at a consequential boundary
        ↓
HARD / STRONG / SOFT policy is evaluated
        ↓
UNKNOWN remains UNKNOWN
        ↓
EvaluationContext is passed to the existing matching adapter
        ↓
hard policy outranks similarity
        ↓
past evaluation remains reproducible after later Intent/Target edits
```

No stage may silently create new candidate facts, mutate user policy, invent a target, or assume certainty that does not exist.

---

## 41. Final Slice 3 Contract

```text
USER CONTROLS INTENT.
TARGETS PROVIDE CONTEXT.
ROUTER MAY ABSTAIN.
POLICY OUTRANKS SIMILARITY.
UNCERTAINTY STAYS VISIBLE.
HISTORY NEVER MUTATES.
```

Slice 3 should leave GaweYuk with a stable contextual evaluation boundary that later slices can use for richer matching, job decisions, privacy-aware disclosure, and application generation without revisiting the authority model established here.

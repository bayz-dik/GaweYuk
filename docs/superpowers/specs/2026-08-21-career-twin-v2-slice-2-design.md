# GaweYuk Career Twin v2 — Slice 2 Design

**Status:** Approved design, pending repository commit  
**Date:** 2026-08-21  
**Scope:** Candidate Entity + Suggestion/Approval Pipeline  
**Depends on:** Career Twin v2 Slice 1 canonical core, Trust Engine v1

## 1. Purpose

Slice 2 turns Career Twin from a safe canonical store into a controlled intake and review system. It introduces a universal suggestion intake contract, staged candidate entities, atomic suggestions, entity resolution, conflict sets, rejection/suppression memory, direct fact entry, safe website-ready APIs, idempotency, optimistic concurrency, and transactional approval/rejection semantics.

The central rule is:

> Sources may suggest. Only explicit user authority may change canonical career truth.

Slice 2 is designed for a website-first GaweYuk product. It does not implement the frontend yet, but it exposes stable backend contracts so a future web client can consume the system without bypassing Career Twin invariants.

## 2. Existing Boundary from Slice 1

Slice 1 established the authoritative Career Twin core:

- immutable approved claims;
- immutable claim history with supersession;
- canonical CareerEntity records;
- evidence records and claim-evidence links;
- claim assessments;
- append-only domain events and outbox writes;
- atomic approval through `CareerTwinCommandService`;
- optimistic stale-claim protection with `expected_active_claim_id`;
- rebuildable projection from the authoritative ledger;
- legacy migration and compatibility projection;
- safe read-only Career Twin API.

Slice 2 MUST extend this model. It MUST NOT create a second canonical write path.

## 3. Product Invariants

The following invariants are non-negotiable:

1. A source may create evidence, candidates, and suggestions, but may not create approved canonical truth directly.
2. Entity resolution may route a suggestion to an entity, but may not approve a claim.
3. Confidence may prioritize review, but may not authorize replacement of approved truth.
4. Approved claims are never silently overwritten.
5. User rejection is not a career fact and MUST remain outside the Claim Ledger.
6. Candidate entities are staging objects, not canonical entities.
7. Suggestion records are proposals, not truth.
8. Unknown is not false, and unscored is not low confidence.
9. Evidence count is meaningless without evidence-family lineage.
10. More-specific text is not automatically more true than current canonical text.
11. No approved suggestion may exist without the corresponding canonical outcome being committed in the same transaction.
12. Retries must not duplicate canonical effects.
13. Stale browser state must not overwrite newer canonical truth.
14. Raw sensitive payloads must not be copied into suggestion tables.
15. Canonical changes continue to pass through `CareerTwinCommandService` or a transaction-safe extension of the same authority boundary.

## 4. Scope

### 4.1 Implemented in Slice 2

- universal suggestion intake contract;
- active intake sources: `USER_INPUT` and `LEGACY_PROFILE`;
- extension points for future CV, AI, linked-profile, and external-source adapters;
- SuggestionBatch;
- CandidateEntity staging lifecycle;
- AtomicSuggestion model;
- two-axis suggestion state;
- deterministic entity resolution v1;
- entity-type-specific resolver strategies;
- evidence-family and independence handling;
- value relationship classification;
- duplicate detection;
- conflict sets and conflict clustering;
- explicit conflict resolution commands;
- fingerprint-based suppression memory;
- direct fact entry with explicit-save approval semantics;
- idempotency;
- optimistic concurrency;
- transactional domain events/outbox integration;
- safe website-ready read/write API;
- failure-safe error taxonomy;
- TDD, transaction-failure injection, privacy, compatibility, and regression tests.

### 4.2 Explicitly Out of Scope

- CV parser;
- OCR;
- LLM extraction;
- LinkedIn profile import;
- job-platform profile sync;
- machine-learned entity resolver;
- PostgreSQL migration;
- asynchronous workers;
- frontend website implementation;
- Android APK/native application;
- unrestricted user-provided server-side URL fetching.

The interfaces added in Slice 2 must leave clean extension points for these future capabilities.

## 5. Source Intake Model

### 5.1 Universal Intake Contract

All future suggestion sources enter through one source-agnostic contract. Initial source types are:

- `USER_INPUT`
- `LEGACY_PROFILE`

Reserved future source types include:

- `CV_IMPORT`
- `AI_INFERENCE`
- `EXTERNAL_SOURCE`
- `LINKED_PROFILE`

The intake contract accepts normalized proposals plus provenance/evidence metadata. It does not expose canonical claim repositories to adapters.

Conceptually:

```text
Source Adapter
    -> Intake Request
    -> Evidence Registration
    -> Candidate Entity Staging
    -> Atomic Suggestions
```

### 5.2 Direct Fact Entry

A website form intentionally filled and saved by the authenticated owner is treated as explicit approval. The user MUST NOT be forced to approve the same fact twice.

Flow:

```text
Direct Fact Entry
    -> authenticated owner authorization
    -> USER_INPUT evidence registration
    -> entity resolution or canonical entity creation
    -> stale-claim validation
    -> canonical approval/supersession
    -> events/outbox
    -> commit
```

The `Save`/`Confirm` action itself is the explicit approval event.

Direct fact commands MUST carry explicit entity intent rather than guessing the user's structural intent:

```text
CREATE_NEW
EDIT_EXISTING
```

`EDIT_EXISTING` requires the target canonical `entity_id`. `CREATE_NEW` may use entity resolution only to warn about likely duplicates; a `HIGH` resolver result MUST NOT silently turn an explicit create-new action into an edit of an existing entity. If the UI later offers “use existing instead,” that is a separate explicit user choice.

Direct fact entry MUST NOT bypass ontology validation, evidence registration, stale-state protection, canonical command authority, or transaction boundaries.

### 5.3 Imported/Generated Suggestions

Data originating from legacy import, future CV extraction, AI inference, linked profile, or external sources is never silently canonicalized. It enters the review pipeline:

```text
Source
    -> SuggestionBatch
    -> CandidateEntity
    -> AtomicSuggestion[]
    -> resolution / duplicate / conflict classification
    -> user decision
    -> canonical claim only after explicit approval
```

#### Legacy migration compatibility

Slice 1's already-executed one-time legacy migration remains authoritative history. Slice 2 MUST NOT rewrite those existing canonical claims back into suggestions or reinterpret historical migration events.

`LEGACY_PROFILE` in Slice 2 means new/replayed legacy-profile intake through the suggestion architecture after Slice 2 is installed. Historical Slice 1 bootstrap data remains untouched. Idempotent fingerprints must prevent the same already-migrated factual payload from creating misleading duplicate proposals when lineage proves it is the same import.

## 6. Domain Model

Slice 2 introduces six main domain records:

1. `SuggestionBatch`
2. `CandidateEntity`
3. `AtomicSuggestion`
4. `EntityResolution`
5. `ConflictSet`
6. `SuppressionRecord`

Supporting link/assessment records may be added where normalization requires many-to-many relationships.

### 6.1 SuggestionBatch

A batch groups related suggestions from one intake operation for human-friendly review while preserving atomic backend decisions.

Required fields:

```text
batch_id
twin_id
source_type
source_reference?
intake_version
evidence_family_id
lifecycle
created_at
completed_at?
```

Lifecycle:

```text
OPEN
PROCESSED
CANCELLED
```

`PROCESSED` means every contained suggestion is terminal for the batch's current review context; it does not mean every suggestion was approved.

### 6.2 CandidateEntity

A candidate entity is a staged possible entity, distinct from canonical `CareerEntity`.

Required fields:

```text
candidate_id
batch_id
twin_id
proposed_entity_type
fingerprint
display_hint
lifecycle_state
created_at
promoted_entity_id?
```

Lifecycle:

```text
STAGED
LINKED
PROMOTED
REJECTED
SUPERSEDED
```

Semantics:

- `LINKED`: resolver identified an existing canonical entity.
- `PROMOTED`: explicit user-approved flow caused creation of a new canonical CareerEntity.
- `REJECTED`: candidate was explicitly rejected as a proposed entity.
- `SUPERSEDED`: another candidate or resolution replaced this staging interpretation.

A `candidate_id` MUST never be treated as a canonical `entity_id`.

### 6.3 AtomicSuggestion

AtomicSuggestion is the central proposal record.

Required fields:

```text
suggestion_id
batch_id
twin_id
candidate_id
resolved_entity_id?
predicate
proposed_value
value_type
decision_state
disposition
normalized_value_fingerprint
expected_active_claim_id?
version
created_at
decided_at?
decision_actor_id?
```

Evidence is linked through a normalized relation rather than an embedded mutable list when persisted.

#### Decision state

```text
PENDING
APPROVED
REJECTED
```

#### Disposition

```text
READY
CONFLICT
DUPLICATE
STALE
SUPPRESSED
```

Decision and disposition are separate axes. Examples:

- `PENDING + CONFLICT`: user has not decided; proposal conflicts with current truth.
- `REJECTED + SUPPRESSED`: user rejected and suppression policy currently hides recurrence.
- `PENDING + SUPPRESSED`: system suppressed a duplicate/noisy proposal without implying user rejection.

`APPROVED` MUST only be written after the canonical claim operation has succeeded inside the same transaction.

### 6.4 EntityResolution

Resolution results are appendable/versioned assessments, not mutable truth.

Required fields:

```text
resolution_id
candidate_id
proposed_entity_id?
confidence?
confidence_band
method
algorithm_version
input_fingerprint
signals_json
created_at
supersedes_resolution_id?
```

Confidence bands:

```text
HIGH
MEDIUM
LOW
UNKNOWN
```

Semantics:

- `HIGH`: candidate may be auto-linked to an existing canonical entity.
- `MEDIUM`: user review is required before linking.
- `LOW`: candidate is treated as likely separate/new.
- `UNKNOWN`: resolver could not produce a reliable determination.

Even `HIGH` does not grant claim-approval authority.

### 6.5 ConflictSet

A ConflictSet represents mutually incompatible alternatives for a canonical claim family.

Required fields:

```text
conflict_id
twin_id
entity_id
predicate
active_claim_id
status
version
created_at
resolved_at?
resolution_type?
resolution_claim_id?
```

Status:

```text
OPEN
RESOLVED
```

Suggestions connect to conflicts through a link table. Equivalent suggestions may be clustered into one candidate-value alternative while preserving underlying suggestion and evidence lineage.

### 6.6 SuppressionRecord

Suppression records user/system memory about repeated proposals without polluting canonical career truth.

Required fields:

```text
suppression_id
twin_id
entity_scope?
candidate_scope?
predicate
normalized_value_fingerprint
evidence_family_scope?
source_scope?
strength
reason
created_at
expires_at?
lifted_at?
```

Strength:

```text
SOFT
STRONG
```

- `SOFT`: repeated proposals with materially identical evidence are suppressed; materially new independent evidence may reopen review.
- `STRONG`: “do not suggest this again” behavior; only explicit user action or a deliberately defined material-change rule may lift it.

Rejection and suppression are not claims and are never projected as career facts.

## 7. Suggestion State Machine

Allowed transitions are command-driven, not arbitrary repository patches.

```text
PENDING + READY
    approve -> APPROVED
    reject  -> REJECTED
    context invalidated -> PENDING + STALE

PENDING + CONFLICT
    KEEP_CURRENT       -> REJECTED + SUPPRESSED when policy requests suppression
    ACCEPT_ALTERNATIVE -> APPROVED
    EDIT_AND_ACCEPT    -> APPROVED
    DEFER              -> remains PENDING + CONFLICT

PENDING + DUPLICATE
    classify/suppress  -> PENDING + SUPPRESSED

PENDING + SUPPRESSED
    materially new evidence -> PENDING + READY or PENDING + CONFLICT
```

Repositories MUST NOT expose a generic state mutator that allows invalid combinations.

## 8. Entity Resolution

### 8.1 Strategy

Resolution uses deterministic, versioned, explainable multi-signal rules. Slice 2 does not use ML.

Resolver input may include:

- company identity exact/normalized/alias match;
- role exact match;
- role semantic/ontology relation;
- date exact match;
- date overlap;
- date contradiction;
- location match;
- employment type;
- source link;
- evidence-family overlap;
- structural relationships already present in Career Twin.

### 8.2 Hard Contradictions

Strong contradictions may veto otherwise high aggregate similarity.

Example: same company and role but clearly non-overlapping historical periods must not be auto-linked merely because text is similar.

Rule:

> Strong contradiction outranks aggregate similarity for auto-link decisions.

### 8.3 Entity-Type-Specific Resolvers

A single universal threshold is forbidden. Resolver behavior varies by entity type.

Initial strategy modules should include or leave explicit boundaries for:

- ExperienceResolver
- EducationResolver
- SkillResolver
- CertificationResolver
- ProjectResolver
- OrganizationResolver

Each implements a common interface such as:

```text
resolve(candidate, canonical_entities) -> EntityResolutionAssessment
```

### 8.4 Normalization

The system separates:

```text
raw value
normalized value
semantic identity
```

Normalization may remove formatting noise for comparison but MUST NOT erase meaningful specificity from the canonical value. Raw source representation remains available through evidence references where privacy permits.

### 8.5 Explainability

Resolution output must expose safe reasons/warnings suitable for the future website, for example:

```json
{
  "result": "MEDIUM",
  "confidence": 0.76,
  "reasons": [
    "same normalized company",
    "similar role"
  ],
  "warnings": [
    "dates unavailable"
  ]
}
```

No opaque percentage may be the only explanation.

## 9. Evidence Family and Confidence

### 9.1 Evidence Families

Multiple appearances derived from the same upstream fact do not count as independent confirmations.

The system groups evidence into families and tracks independence state such as:

```text
INDEPENDENT
DERIVED
SAME_FAMILY
INDEPENDENCE_UNKNOWN
```

`INDEPENDENCE_UNKNOWN` MUST NOT be treated as independent support.

### 9.2 Provenance Trust vs Claim Confidence

The existing separation remains:

- provenance trust tier describes the source/evidence;
- claim confidence describes support for a proposed/canonical fact;
- approval state describes user authority.

These dimensions MUST NOT be collapsed.

### 9.3 Confidence Algorithm v1

Slice 2 uses a deterministic versioned confidence evaluator. Conceptually it considers:

- independent evidence-family support;
- source quality;
- consistency;
- recency where relevant;
- contradictions;
- lineage uncertainty;
- extractor certainty where applicable.

It MUST NOT simply average source scores or count mirrored sources.

Every computed assessment records an algorithm version such as:

```text
career-evidence-v1
```

Confidence is advisory only.

## 10. Value Relationship Classification

Comparing a proposed value to the current canonical value uses more than binary same/conflict classification.

Supported relationships:

```text
IDENTICAL
EQUIVALENT
COMPATIBLE
MORE_SPECIFIC
LESS_SPECIFIC
CONFLICTING
UNRELATED
UNKNOWN
```

Examples:

- `Microsoft Excel` vs `MS Excel` -> `EQUIVALENT` when ontology aliases support it.
- `Operator` vs `Operator Stamping` -> potentially `MORE_SPECIFIC`, not automatically identical.
- two different responsibilities on a cardinality-MANY predicate -> `COMPATIBLE`, not conflict.
- `PERMANENT` vs `CONTRACT` on a cardinality-ONE predicate -> `CONFLICTING`.

The relationship engine MUST consult ontology cardinality and predicate semantics.

`MORE_SPECIFIC` may produce a review recommendation but may never auto-replace an approved value.

## 11. Duplicate Detection

A suggestion is duplicate only when the system can support equivalence across:

```text
same resolved entity
+ same predicate
+ same normalized/semantic value
```

Source duplication alone is not enough, and text similarity alone is not enough.

Duplicate suggestions may be suppressed without marking them as user-rejected.

## 12. Conflict Intelligence

### 12.1 Conflict Creation

A ConflictSet is created only when alternatives are mutually incompatible under ontology/cardinality semantics.

Not every differing value is a conflict.

### 12.2 Candidate-Value Clustering

Equivalent proposed values from multiple suggestions may be grouped into one review alternative while preserving individual provenance.

Example:

```text
Current: Operator Produksi
Alternative cluster: Operator Stamping
  - suggestion A
  - suggestion B
  - suggestion C
  - supporting evidence families: 2
```

The UI/API must prefer evidence-family counts over misleading raw source counts.

### 12.3 Explicit Resolution Actions

Supported user actions:

```text
KEEP_CURRENT
ACCEPT_ALTERNATIVE
EDIT_AND_ACCEPT
DEFER
```

`KEEP_CURRENT` preserves the active claim. Policy may reject/suppress the competing proposal.

`ACCEPT_ALTERNATIVE` supersedes the current claim and activates the selected proposed value within one transaction.

`EDIT_AND_ACCEPT` preserves the original suggestion as provenance and creates a user-edited canonical value.

`DEFER` changes no canonical truth and leaves the conflict open.

## 13. Suppression Policy

Suppression uses a fingerprint including the relevant combination of:

- twin;
- entity/candidate scope;
- predicate;
- normalized value;
- evidence family/source scope.

Behavior:

- same value + same evidence -> suppressed;
- same value + same upstream family -> suppressed;
- same value + materially new independent evidence -> may reopen review;
- materially changed value -> new suggestion;
- explicit “do not suggest again” -> strong suppression.

Suppression rules must be deterministic and testable.

## 14. Commands

The write API is command-oriented. Initial commands:

```text
SubmitDirectFactCommand
CreateSuggestionBatchCommand
ApproveSuggestionCommand
RejectSuggestionCommand
ResolveConflictCommand
LiftSuppressionCommand
ReevaluateCandidateCommand
```

`SubmitDirectFactCommand` must include `entity_intent=CREATE_NEW|EDIT_EXISTING`; `EDIT_EXISTING` requires the canonical entity target and the appropriate stale-state expectation.

### 14.1 ApproveSuggestionCommand

Expected fields include:

```text
twin_id
suggestion_id
expected_suggestion_version
expected_active_claim_id?
selected_entity_id?
edited_value?
idempotency_key
```

If `edited_value` is supplied, the suggestion record remains immutable as the original proposal. The edited value becomes the approved claim with provenance back to the source suggestion/evidence and explicit user edit.

### 14.2 RejectSuggestionCommand

Expected fields include:

```text
suggestion_id
expected_suggestion_version
reason?
suppression_mode: NONE | SOFT | STRONG
idempotency_key
```

### 14.3 ResolveConflictCommand

Expected fields include:

```text
conflict_id
action
selected_suggestion_id?
edited_value?
expected_active_claim_id
expected_conflict_version
idempotency_key
```

Generic arbitrary `PATCH` mutation of canonical claims or conflict state is forbidden.

## 15. Optimistic Concurrency

Workflow records that can change due to decisions carry an integer version.

Clients submit the version they observed:

```text
expected_suggestion_version
expected_conflict_version
expected_active_claim_id
```

If server state has advanced, the command fails with a stale-state conflict. The server does not silently replay the user's old decision against newer truth.

## 16. Idempotency

All consequential write commands carry an idempotency key.

Persisted idempotency metadata includes:

```text
idempotency_key
request_fingerprint
result_reference
created_at
```

Rules:

- same key + same request -> return the original result;
- same key + different request -> fail with `IDEMPOTENCY_KEY_REUSED`;
- retries MUST NOT duplicate claims, entities, events, or conflict effects.

Generated suggestions additionally use deterministic fingerprints to prevent repeated imports from flooding the queue.

## 17. Transaction Boundaries

### 17.1 Suggestion Approval

Approval is atomic:

```text
BEGIN
  authorize actor/twin
  reload suggestion
  validate version/state
  resolve/link/promote entity as needed
  reload active claim
  validate expected_active_claim_id
  create or supersede canonical claim
  link evidence
  update suggestion decision
  resolve conflict when applicable
  append domain events
  append outbox records
  persist idempotency result
COMMIT
```

Any failure rolls back every effect.

### 17.2 Rejection

```text
BEGIN
  authorize
  reload suggestion
  stale/state check
  record rejection
  create suppression if requested
  update conflict state/membership if required
  append event/outbox
  persist idempotency result
COMMIT
```

### 17.3 Direct Fact Entry

Evidence registration, entity resolution/promotion, claim approval/supersession, event/outbox writes, and idempotency result are committed atomically.

## 18. Domain Events

Slice 2 introduces at least:

```text
SUGGESTION_BATCH_CREATED
CANDIDATE_ENTITY_STAGED
CANDIDATE_ENTITY_LINKED
CANDIDATE_ENTITY_PROMOTED
SUGGESTION_CREATED
SUGGESTION_APPROVED
SUGGESTION_REJECTED
SUGGESTION_SUPPRESSED
CONFLICT_OPENED
CONFLICT_RESOLVED
SUPPRESSION_CREATED
SUPPRESSION_LIFTED
```

Existing canonical events such as `CLAIM_APPROVED` and `CLAIM_SUPERSEDED` remain authoritative for claim history.

A single command may emit multiple events inside one transaction.

## 19. Authorization and Security

### 19.1 Actor Context

Future website requests must not gain access by supplying an arbitrary `twin_id`.

Service commands operate with an actor/authorization context:

```text
authenticated actor
    -> authorized twin
    -> resource ownership
    -> command execution
```

Even if production authentication is not fully implemented in Slice 2, service interfaces must be designed so actor context can be enforced without a future architectural rewrite.

Canonical direct-fact approval requires an owner-authorized human actor context. Non-human migration/import actors may create evidence, batches, candidates, and suggestions, but they may not invoke the direct-fact canonical path merely by labeling their source as `USER_INPUT`.

### 19.2 Source Trust Is Not Actor Trust

`source_type=USER_INPUT` does not prove that the authenticated owner performed the request. Provenance classification and authorization are independent concerns.

### 19.3 Privacy

Suggestion persistence may contain:

- normalized career fact values;
- safe display hints;
- evidence identifiers;
- fingerprints;
- confidence/reason metadata.

It must not contain duplicated raw sensitive payloads such as:

- passwords;
- API keys;
- identity-document images;
- full private CV payloads;
- authentication credentials;
- future Sensitive Vault raw contents.

Future sensitive ingestion supplies scoped evidence references rather than raw-payload duplication.

## 20. API Contract

The API is website-ready but frontend-independent.

### 20.1 Read Endpoints

```http
GET /api/career-twin
GET /api/career-twin/suggestions
GET /api/career-twin/suggestions/{id}
GET /api/career-twin/conflicts
GET /api/career-twin/conflicts/{id}
GET /api/career-twin/candidates/{id}
```

Suggestion listing may filter by:

- decision_state;
- disposition;
- source_type;
- entity_type;
- batch_id.

### 20.2 Write Endpoints

```http
POST /api/career-twin/facts
POST /api/career-twin/suggestion-batches
POST /api/career-twin/suggestions/{id}/approve
POST /api/career-twin/suggestions/{id}/reject
POST /api/career-twin/conflicts/{id}/resolve
POST /api/career-twin/suppressions/{id}/lift
```

There is no mutable `PATCH /career-claims/{id}` endpoint. Corrections continue to use immutable supersession semantics.

### 20.3 Safe Responses

API responses may include safe explainability fields such as:

```text
suggestion_id
entity display/type
predicate
proposed value
current value when safe
decision state
disposition
confidence?
reasons[]
warnings[]
```

They must not expose raw payload bodies, vault internals, database implementation details, secrets, or stack traces.

## 21. Error Taxonomy

Domain errors are explicit and mapped to stable API behavior.

Representative errors:

```text
SuggestionNotFound
CandidateNotFound
ConflictNotFound
StaleSuggestionState
StaleClaimState
StaleConflictState
InvalidEntityResolution
InvalidSuggestionTransition
InvalidConflictResolution
SuppressedSuggestion
DuplicateSuggestion
OntologyViolation
IdempotencyConflict
AuthorizationDenied
PrivacyBoundaryViolation
```

Recommended HTTP mapping:

```text
400 malformed or structurally invalid command
403 authorization/privacy denial
404 resource missing
409 stale state, command conflict, idempotency conflict
422 ontology/domain validation
503 configured subsystem unavailable
500 unexpected internal failure
```

Unexpected errors must not disclose internal paths, SQL, secrets, or stack traces.

## 22. Persistence and Migration

Slice 2 adds forward-only schema migration(s) after the current Career Twin migrations. Existing merged migrations are never edited.

The exact split may be one or multiple numbered migrations depending on dependency clarity, but migration behavior must satisfy:

- old database migrates forward;
- fresh database reaches the same final schema;
- migrations are idempotent under the existing migration runner contract;
- no historical approved claim is rewritten;
- canonical claim history remains authoritative.

Persistence should use focused repositories rather than allowing API/services to issue ad-hoc SQL.

## 23. Module Boundaries

Recommended package layout:

```text
onejob/career_twin/
  intake.py
  suggestions.py
  candidates.py
  resolution.py
  conflicts.py
  suppression.py
  service.py          # existing canonical authority, extended carefully
  repositories.py
  models.py
  projection.py
```

Responsibilities:

- `intake.py`: source-agnostic intake requests and orchestration;
- `suggestions.py`: suggestion models/state transitions/commands;
- `candidates.py`: staging/promotion lifecycle;
- `resolution.py`: deterministic entity/value resolution and assessments;
- `conflicts.py`: conflict creation, clustering, resolution semantics;
- `suppression.py`: rejection/suppression matching and lifting;
- `service.py`: canonical command authority and transaction-safe integration;
- `repositories.py`: focused persistence operations only.

If implementation reveals one file growing into multiple unrelated responsibilities, it should be split rather than forming a monolithic suggestion service.

## 24. Testing Strategy

Development follows TDD: RED -> GREEN -> focused regression -> full regression.

### 24.1 State and Model Tests

- suggestion state transitions;
- candidate lifecycle;
- conflict lifecycle;
- suppression policy;
- invalid transition rejection.

### 24.2 Entity Resolution Tests

Required cases include:

- similar role/company plus contradictory dates does not auto-link;
- exact/known skill aliases can classify as equivalent;
- unknown evidence independence is not counted as independent;
- resolver failure returns `UNKNOWN`, not false certainty;
- HIGH resolution links routing only and does not approve a claim;
- entity-type resolver policies differ where semantics require it.

### 24.3 Relationship and Conflict Tests

- cardinality-MANY compatible values do not create false conflicts;
- cardinality-ONE incompatible values create ConflictSet;
- MORE_SPECIFIC is advisory and does not auto-replace;
- equivalent suggestions cluster while preserving provenance;
- raw source count does not inflate independent evidence-family count.

### 24.4 Atomicity and Failure Injection

Inject failures after critical steps such as:

- canonical claim creation;
- claim supersession;
- event append;
- outbox append;
- suggestion decision update;
- conflict resolution update;
- idempotency result persistence.

Every injected failure must prove full rollback: no partial canonical claim, false approved suggestion, orphan event, or dangling conflict resolution.

### 24.5 Concurrency and Idempotency Tests

- stale `expected_active_claim_id` rejected;
- stale suggestion version rejected;
- stale conflict version rejected;
- same idempotency key + same payload returns same result;
- same idempotency key + different payload fails;
- retry never creates duplicate canonical effects.

### 24.6 Privacy Tests

Safe API responses must not contain fields/payloads such as:

```text
raw_payload
payload_json
raw_evidence
secret
vault internals
credentials
```

### 24.7 Compatibility Regression

Existing behavior must remain green, including:

- Career Twin projection/rebuild;
- canonical claim repository tests;
- approval/supersession tests;
- legacy migration/compatibility projection;
- matching;
- answers;
- Trust Engine;
- existing API routes;
- database migrations.

## 25. End-State Acceptance Criteria

Slice 2 is complete when all of the following are true:

1. `USER_INPUT` and `LEGACY_PROFILE` enter through the new intake architecture.
2. Imported data can produce SuggestionBatch + CandidateEntity + atomic suggestions without writing canonical truth.
3. Direct user fact entry can atomically write a user-approved canonical fact without double confirmation.
4. Entity resolution v1 is deterministic, versioned, explainable, entity-type-aware, and fail-safe.
5. Entity resolution never grants claim-approval authority.
6. Evidence-family lineage prevents mirrored evidence from inflating support.
7. Value comparisons distinguish identical/equivalent/compatible/specific/conflicting/unknown relationships.
8. Conflict sets are created only for genuinely incompatible canonical alternatives.
9. Approved canonical facts are never silently overwritten.
10. User can approve, reject, keep current, edit-and-accept, defer, and lift suppression through explicit commands.
11. Rejections remain outside the canonical Claim Ledger.
12. Suppression prevents repeated noise without permanently hiding materially new independent evidence unless the user chose strong suppression.
13. Suggestion approval and conflict resolution are fully atomic with existing claim/event/outbox behavior.
14. Stale state and retry safety are enforced through optimistic concurrency and idempotency.
15. API responses are safe for a future website client and do not leak raw/private internals.
16. Existing Slice 1/Trust Engine behavior remains green.
17. Full repository regression passes before merge.

## 26. Future Extension Points

After Slice 2, the same intake contract can accept future adapters without granting them canonical authority:

```text
CV parser / extractor
AI inference engine
linked profile import
external verified source
user-authorized integrations
```

A future Career Intent / Saved Career Target slice can consume the canonical Career Twin produced by this pipeline without reinterpreting source-level proposals as facts.

A future website can then expose:

```text
Career Twin view
Suggestion inbox
Conflict review
Direct fact editor
Evidence explanations
Suppression controls
```

without bypassing backend authority rules.

## 27. Final Architectural Rule

Slice 2 intentionally separates intelligence from authority:

```text
intelligence may collect
intelligence may normalize
intelligence may resolve
intelligence may rank
intelligence may explain
intelligence may recommend

but only explicit authorized user intent may change canonical Career Twin truth
```

That boundary is the defining safety and correctness property of Career Twin v2 Slice 2.

# GaweYuk Slice 4A Design — Job Source & Verification Network

**Date:** 2026-08-21
**Status:** Approved design, ready for implementation planning after user review
**Scope:** Slice 4A only
**Roadmap position:** 4A → 4B → 4C → 4D
**Product launch posture:** Indonesia-first, global-ready
**Design method:** Evidence-first, deterministic authority, human review for ambiguity
**Quality mode:** Anti-Slop `DURING`

---

## 1. Purpose

Slice 4A turns GaweYuk's existing ingestion and Trust Engine foundations into a production-grade **Job Source & Verification Network**.

The objective is not to collect the largest possible number of job URLs. The objective is to build a trustworthy job catalog where a job becomes visible only after GaweYuk can explain why it is sufficiently credible, current, and safe to show.

The core product promise is therefore:

> A job may be discovered from many places, but discovery never grants publication authority.

GaweYuk must not claim that every published job is "100% real" or "scam-free." Verification is probabilistic and evidence-dependent. The system instead provides auditable provenance, explicit uncertainty, hard safety gates, freshness guarantees, and clear publication policy.

---

## 2. Context and Existing Baseline

GaweYuk already contains useful primitives that Slice 4A must extend rather than replace:

- collectors for Greenhouse, Lever, and Ashby;
- a `Collector` protocol and collection health/status concepts;
- `RawJobObservation` primitives with durable provenance fields;
- ingestion modules for evidence, consensus, identity, lifecycle, and explainability;
- canonical job storage and job versioning;
- evidence-family-aware consensus;
- Trust Engine dimensions for company identity, source credibility, listing integrity, evidence consensus, recruiter integrity, privacy safety, and freshness;
- Trust classifications from `AUTOPILOT_ELIGIBLE` through `ABSOLUTE_BLOCK`;
- risk-signal extraction for payment requests, OTP/password/PIN/recovery-code requests, bank-data requests, identity-document requests, and related sensitive recruitment patterns;
- Career Twin / Career Intent / Career Targets / Career Context subsystems that consume jobs downstream;
- SQLite migrations applied in lexical order through `Database`;
- a verified `main` baseline of 513 passing tests after Slice 3 merge.

Slice 4A must preserve backward compatibility unless a design requirement explicitly says otherwise.

The current ingestion pipeline intentionally commits raw/canonical ingestion before Trust Engine shadow evaluation. Slice 4A preserves that durability principle: **evidence ingestion survives verification failures**.

---

## 3. Scope

### 3.1 In scope

Slice 4A includes:

1. Source Registry
2. Source Adapter Network
3. Progressive source rollout and per-source health/circuit breaker
4. Raw observation durability and provenance
5. Canonical Job + Source Appearance separation
6. Safer job identity resolution and deduplication
7. Company Identity Graph
8. Evidence-family lineage
9. Source authority and corroboration semantics
10. Apply-destination verification
11. Existing Trust Engine integration
12. Immutable verification snapshots
13. Publication policy and publication state
14. Two-zone catalog: public catalog vs internal review/quarantine/rejected stores
15. Tier-aware freshness and reverification
16. Official closure/reopen handling
17. Evidence-first human review queue
18. Internal/public API boundaries
19. Fetch/SSRF security
20. Failure semantics and atomic publication updates
21. Source/verification observability
22. Security/adversarial corpus
23. Progressive rollout from existing ATS collectors
24. Shared adapter contract tests
25. Anti-Slop DURING quality gates for code comments and later-facing API/copy surfaces

### 3.2 Explicitly out of scope

Slice 4A does **not** include:

- the full production website shell;
- final candidate authentication/session UX;
- job-feed visual redesign;
- Career workspace UI;
- full global source coverage;
- bypassing platform anti-bot controls, authentication, robots policy, terms, or unsupported access methods;
- building a universal scraper;
- Kafka/Celery/distributed microservices;
- replacing SQLite solely for architecture aesthetics;
- full matching rewrite;
- automatic application submission;
- recruiter-facing disclosure logic;
- public moderation console UI.

Those belong to later slices or future operational work.

---

## 4. Approved Product Decisions

The following decisions are locked for Slice 4A.

### 4.1 Source strategy

**Tiered Source Network**

Sources are classified by authority:

- `TIER_1_OFFICIAL`
  - official company career pages;
  - official ATS tenants;
  - government/public employment sources;
  - verified employer feeds.

- `TIER_2_AUTHORIZED`
  - official job-board APIs;
  - partner feeds;
  - licensed/authorized aggregators.

- `TIER_3_DISCOVERY`
  - permitted public discovery sources;
  - public recruitment announcements;
  - community/public sources that may help discover a candidate listing.

A source can discover a job. A source cannot declare the job true.

### 4.2 Publication catalog

**Two-Zone Trust Catalog**

The public job catalog contains only publishable jobs.

Internal zones hold:

- review-required jobs;
- quarantined jobs;
- rejected jobs;
- not-yet-evaluated jobs.

Canonical storage is not equivalent to public visibility.

### 4.3 Duplicate handling

**Canonical Job + Source Appearances**

Multiple source appearances that represent one real requisition become one canonical job plus multiple source appearances.

Many URLs do not imply many jobs.

Many mirrors do not imply independent corroboration.

### 4.4 Freshness

**Tier-Aware Freshness + Active Reverification**

Verification expires. A job that was verified once is not verified forever.

Reverification cadence depends on source tier, source reliability, job age, explicit expiry, last authoritative sighting, previous change behavior, source health, and verification confidence.

### 4.5 Adapter architecture

**Source Adapter Network**

Every source uses a bounded adapter that produces a shared observation contract.

Adapters observe; they do not verify, trust, match, or publish.

### 4.6 Human review

**Evidence-First Hybrid Verification**

Deterministic rules and evidence resolve clear cases automatically.

Humans review ambiguous cases.

AI may summarize evidence or suggest anomalies. AI is not the trust authority and cannot independently create official identity relationships, clear hard safety gates, or publish jobs.

### 4.7 Launch strategy

**Indonesia-first, global-ready**

The architecture must not hard-code Indonesia into identifiers, currency handling, geography, source contracts, or identity models.

Initial source rollout and operational success criteria prioritize Indonesian job-market coverage.

### 4.8 Source rollout

**Progressive Trust Rollout**

New sources start in non-authoritative states and must earn production publication authority.

Normal progression:

`REGISTERED → SHADOW → OBSERVED → VALIDATED → ACTIVE`

Possible demotion:

`ACTIVE → DEGRADED → SHADOW | DISABLED | POLICY_BLOCKED`

### 4.9 Evidence authority

**Evidence-weighted authority**

One authoritative official source may be sufficient for publication when:

- company identity is sufficiently verified;
- the source-company relationship is sufficiently verified;
- the apply destination is safe enough for policy;
- the listing is fresh;
- no hard safety gate is hit;
- the Trust Engine classification is eligible;
- critical evidence is not unknown.

Five unverified mirrors cannot outweigh one authoritative contradiction.

### 4.10 Company identity

**Company Identity Graph**

A normalized company name is a candidate clue, not verified identity.

Identity is built from evidence-backed relationships among legal entities, brands, domains, career domains, ATS tenants, and aliases.

### 4.11 Top-level architecture

**Observation → Verification → Catalog**

This is the central boundary for Slice 4A.

---

## 5. Architectural Invariants

These invariants are hard requirements.

1. **Adapter = observe**
2. **Normalizer = standardize representation**
3. **Canonicalizer = resolve job identity**
4. **Company Identity = resolve organization relationships**
5. **Trust Engine = assess trust/risk**
6. **Publication Policy = decide public visibility**
7. **Career Engine = decide candidate relevance**
8. **Catalog API = expose only publishable jobs**
9. **Canonical existence ≠ publication permission**
10. **Lifecycle state ≠ publication state**
11. **UNKNOWN ≠ SAFE**
12. **System failure ≠ domain uncertainty**
13. **Many mirrors ≠ independent evidence**
14. **One authoritative source may outweigh many weak sources**
15. **AI inference alone has no publication authority**
16. **Hard safety gates cannot be silently overridden**
17. **Expired verification cannot remain silently valid**
18. **A reviewer decision is tied to an immutable evidence snapshot**
19. **Raw evidence is preserved even when the job is rejected**
20. **Public API must not leak internal evidence payloads, secrets, or reviewer-only notes**
21. **No unsupported source acquisition method is enabled merely to improve coverage**
22. **No country-specific hard-coding in core domain contracts**

---

## 6. Module Boundaries

Slice 4A should evolve toward the following bounded domains while reusing existing code where practical.

```text
onejob/
├── collectors/                  # existing adapters, evolved under shared contracts
├── ingestion/                   # observations, evidence, consensus, canonicalization
├── job_sources/                 # source registry, rollout, health, acquisition policy
├── company_identity/            # company graph and relationship verification
├── job_verification/            # verification snapshots, freshness, publication policy
├── trust_engine/                # existing authority for trust/risk
└── catalog/                     # public catalog query boundary
```

The exact final filenames belong to the implementation plan. The design requirement is the dependency direction:

```text
job_sources / collectors
          ↓
       ingestion
          ↓
 company_identity
          ↓
 job_verification orchestrator
       ↙           ↘
trust_engine    freshness / destination / corroboration
       \           /
        verification snapshot
                ↓
       publication policy
                ↓
             catalog
```

`job_verification` may call the existing Trust Engine. The Trust Engine must not import catalog or publication policy; publication consumes trust results, never the reverse.

Circular authority is prohibited.

For example, collectors must not import publication policy to self-mark observations as trusted.

---

## 7. Source Registry

### 7.1 JobSource

Conceptual fields:

```text
JobSource
├── source_id
├── source_key
├── source_type
├── trust_tier
├── acquisition_method
├── primary_domain?
├── country_scope[]
├── compliance_status
├── rollout_state
├── health_state
├── verification_policy_version
├── created_at
└── updated_at
```

### 7.2 Acquisition methods

Supported acquisition methods are explicit and closed/versioned:

- `OFFICIAL_API`
- `PARTNER_API`
- `PUBLIC_FEED`
- `STRUCTURED_PUBLIC_PAGE`
- `PERMITTED_HTML`
- `MANUAL_IMPORT`
- `USER_SUPPLIED`

A source whose access status is unknown is not silently treated as permitted.

Where applicable, the registry may store terms/permission review metadata and robots/access-policy observations. These fields record acquisition constraints; they are not interpreted as job-trust evidence.

### 7.3 Compliance state

At minimum, the model must distinguish:

- known/allowed acquisition;
- policy unknown;
- blocked/unsupported;
- disabled.

The implementation may refine enum names, but the semantics must remain explicit.

### 7.4 Rollout state

Required rollout states:

- `REGISTERED`
- `SHADOW`
- `OBSERVED`
- `VALIDATED`
- `ACTIVE`
- `DEGRADED`
- `DISABLED`
- `POLICY_BLOCKED`

Promotion requires evidence from adapter health and verification quality, not only a manual boolean.

Only `ACTIVE` sources may contribute new source authority to a public publication decision. `SHADOW`, `OBSERVED`, `VALIDATED`, `DEGRADED`, `DISABLED`, and `POLICY_BLOCKED` sources may still contribute stored evidence according to policy, but they cannot independently authorize publication.

### 7.5 Health state

Required health semantics include:

- healthy;
- degraded;
- rate limited;
- authentication required where applicable;
- schema changed/broken;
- disabled;
- policy blocked;
- unknown.

A source health problem affects source authority and scheduling but does not erase historical observations.

---

## 8. Adapter Contract

The existing `Collector` concept remains the foundation.

Each adapter must return a deterministic collection batch containing `RawJobObservation` values and operational metadata.

### 8.1 Observation contract

The current observation fields remain useful and should be extended where necessary:

```text
RawJobObservation
├── observation_id
├── source_id / source_key
├── source_type
├── collector_version
├── external_id
├── source_url
├── canonical_hint_url?
├── observed_at
├── published_at?
├── updated_at?
├── expires_at?
├── title
├── company_name
├── location_text
├── description
├── salary_min?
├── salary_max?
├── currency?
├── employment_type?
├── skills[]
├── contact_email?
├── apply_url?
├── source_payload_hash
├── raw_payload_reference?
└── evidence_family_id / lineage metadata
```

Observation history is append-only from the domain perspective. Re-fetching a job creates a new observation or a stable idempotent replay outcome; it does not rewrite prior observations.

### 8.2 Adapter prohibition

Adapters must not:

- set public publication state;
- declare company identity verified;
- set final trust classification;
- merge canonical jobs on their own;
- bypass shared safe-fetch policy;
- emit secrets into raw evidence;
- turn rate limiting into closure evidence.

### 8.3 Shared adapter contract tests

Every adapter must pass the same reusable contract suite covering:

- required fields;
- stable source identity;
- timestamp semantics;
- external ID behavior;
- malformed payload handling;
- pagination/partial batch behavior where relevant;
- source URL provenance;
- apply URL capture where available;
- no secret leakage;
- deterministic parsing for the same fixture.

---

## 9. Raw Evidence and Provenance

All source claims are evidence.

The ingestion layer must preserve enough provenance to answer:

- which source claimed this field;
- when it was observed;
- which collector version produced it;
- whether another appearance came from the same upstream origin;
- whether the claim later changed;
- whether the source later disappeared.

Raw payload bytes may be stored by reference rather than inline, but their hash and provenance must be durable.

Sensitive tokens, connector credentials, authorization headers, cookies, or API keys are never evidence.

---

## 10. Evidence Families

Evidence-family lineage is first-class.

Examples:

```text
Official ATS
  ├─ syndicated to Job Board A
  └─ copied by Aggregator B
```

All three appearances may be retained, while corroboration counts the common origin once.

The consensus system may raise confidence only when a confirming appearance introduces an independent evidence family.

The implementation must never use raw source count as a substitute for independent evidence count.

---

## 11. Canonical Job and Source Appearance

### 11.1 CanonicalJob

Conceptual fields:

```text
CanonicalJob
├── canonical_job_id
├── company_id
├── active_version_id
├── lifecycle_state
├── first_seen_at
├── last_seen_at
└── identity_confidence
```

### 11.2 JobSourceAppearance

Conceptual fields:

```text
JobSourceAppearance
├── appearance_id
├── canonical_job_id
├── source_id
├── external_id
├── source_url
├── apply_url?
├── evidence_family_id
├── first_seen_at
├── last_seen_at
├── latest_observation_id
└── appearance_state
```

Source appearance records are not themselves user-visible job cards.

---

## 12. Canonical Job Versions

Material job changes create immutable versions.

Conceptual model:

```text
CanonicalJobVersion
├── version_id
├── canonical_job_id
├── version_number
├── field_snapshot
├── selected_evidence_refs[]
├── content_hash
├── valid_from
└── valid_to?
```

Material fields include at least:

- title;
- company identity reference;
- location;
- description;
- salary range;
- currency;
- employment type;
- contact fields that affect risk;
- apply destination when it affects public action.

History must remain reconstructable.

---

## 13. Company Identity Graph

### 13.1 Purpose

The current normalized-name hash is insufficient as the only production identity authority.

The graph establishes evidence-backed relationships.

### 13.2 Node types

At minimum:

- `COMPANY`
- `LEGAL_ENTITY`
- `BRAND`
- `DOMAIN`
- `CAREER_DOMAIN`
- `ATS_TENANT`

### 13.3 Relationship types

At minimum:

- `OWNED_BY`
- `CAREER_SITE_FOR`
- `ATS_FOR`
- `BRAND_OF`
- `SUBSIDIARY_OF`
- `ALIAS_OF`

### 13.4 Relationship record

```text
IdentityRelationship
├── relationship_id
├── subject_id
├── predicate
├── object_id
├── confidence
├── status
├── verification_method
├── evidence_refs[]
├── first_verified_at
└── last_verified_at
```

### 13.5 Resolution states

Identity resolution must be able to express:

- `VERIFIED`
- `PROBABLE`
- `AMBIGUOUS`
- `CONFLICTING`
- `UNKNOWN`

Publication policy defines which states are sufficient per source context.

Name equality never implies verified identity.

### 13.6 Historical identity snapshots

The graph may evolve as new domain, ATS, brand, or legal-entity evidence arrives. Consequential job verification must therefore reference an immutable identity assessment/snapshot rather than reading an unversioned graph and losing historical context.

A future correction to the identity graph creates a new assessment for future verifications; it does not rewrite why a past publication decision was made.

---

## 14. Job Identity and Deduplication

Deduplication uses a three-way resolution:

- `SAME`
- `DISTINCT`
- `AMBIGUOUS`

It must not force a binary merge when evidence is weak.

Strong identity keys include:

- same authoritative source + same external requisition ID;
- same verified ATS tenant + same requisition ID;
- other future source-specific identifiers that have explicit authority.

Fallback resolution may combine:

- verified company identity;
- normalized title;
- location;
- description similarity;
- employment type;
- apply destination;
- publication window;
- external IDs;
- source/evidence lineage.

Hard contradictions outrank soft similarity.

Ambiguous possible duplicates are routed to review or held separately according to policy. It is safer to temporarily keep two jobs separate than silently merge two distinct requisitions.

---

## 15. Consensus

Canonical fields are selected from evidence, not from "latest source wins."

The existing evidence-family-aware consensus principle remains.

Consensus outputs must preserve:

- selected value;
- confidence;
- primary evidence references;
- conflicting evidence references;
- resolution reason.

Consensus confidence is not equivalent to trust or publication permission.

---

## 16. Verification Pipeline

For each canonical version:

```text
CanonicalJobVersion
        ↓
Company Identity Assessment
        ↓
Source Authority Assessment
        ↓
Apply Destination Assessment
        ↓
Evidence Consensus / Conflict Assessment
        ↓
Risk Signal Extraction
        ↓
Freshness Assessment
        ↓
Existing Trust Engine
        ↓
JobVerificationSnapshot
        ↓
Publication Policy
```

The Trust Engine remains the trust/risk authority. Slice 4A must not create a second competing scam-scoring engine.

---

## 17. Apply Destination Verification

A user-facing application destination must be explicitly assessed.

Conceptual snapshot:

```text
ApplyDestinationAssessment
├── original_apply_url
├── resolved_apply_url
├── resolved_domain
├── redirect_chain_fingerprint
├── verified_at
└── destination_status
```

Statuses include:

- `VERIFIED`
- `ALLOWED_EXTERNAL`
- `UNKNOWN`
- `SUSPICIOUS`
- `BLOCKED`

Redirects are part of the verification boundary. A previously safe link that later redirects elsewhere requires reevaluation.

Public catalog APIs expose only destinations permitted by publication policy.

---

## 18. Trust Engine Integration

The existing Trust Engine remains authoritative for trust dimensions and hard gates.

Slice 4A feeds it stronger evidence for:

- company identity;
- source credibility;
- listing integrity;
- evidence consensus;
- recruiter integrity when available;
- privacy safety;
- freshness.

Trust classification mapping participates in publication policy:

- `AUTOPILOT_ELIGIBLE` → potentially publishable;
- `ASSISTED_ALLOWED` → potentially publishable;
- `REVIEW_REQUIRED` → review;
- `AUTOMATION_BLOCKED` → quarantine;
- `ABSOLUTE_BLOCK` → rejected.

"Potentially" matters: publication also depends on source rollout, identity sufficiency, freshness, apply destination, and critical unknowns.

---

## 19. Hard Safety Semantics

Examples of signals that may create hard publication blocks when confirmed by existing policy include:

- recruitment payment required;
- OTP/password/PIN/recovery-code harvesting;
- malicious credential capture;
- confirmed company impersonation;
- malicious or blocked apply destination.

Negation and context handling must remain intact. A statement such as "we never charge recruitment fees" must not become a payment-risk signal.

AI cannot override a hard gate.

A human reviewer cannot bypass an absolute hard gate unless a future explicit policy change introduces a separately authorized mechanism. Slice 4A introduces no such bypass.

---

## 20. UNKNOWN Semantics

UNKNOWN is a first-class state.

Examples:

```text
company identity       VERIFIED
listing integrity      VERIFIED
apply destination      VERIFIED
recruiter identity     UNKNOWN
```

This may still be publishable during discovery if policy says recruiter identity is non-critical at that stage.

By contrast:

```text
company ownership      UNKNOWN
apply destination      UNKNOWN
```

may require review.

The design forbids:

- treating missing evidence as automatically safe;
- treating missing evidence as automatically fraudulent;
- collapsing system errors into UNKNOWN.

---

## 21. Verification Snapshot

Verification results are immutable.

Conceptual record:

```text
JobVerificationSnapshot
├── verification_id
├── canonical_job_id
├── canonical_version_id
├── identity_snapshot_id
├── trust_evaluation_id
├── source_evidence_refs[]
├── freshness_result
├── corroboration_result
├── apply_destination_result
├── hard_gate_hits[]
├── unknowns[]
├── evaluated_at
├── valid_until
├── input_fingerprint
└── verification_policy_version
```

If the input fingerprint is semantically identical and the snapshot is still valid, the implementation may reuse it.

If evidence changes, create a new snapshot.

Never mutate old snapshots.

---

## 22. Publication Decision

Publication is its own state machine and is separate from lifecycle.

The current publication projection must support:

- `NOT_EVALUATED`
- `VERIFYING`
- `PUBLISHABLE`
- `REVIEW_REQUIRED`
- `QUARANTINED`
- `REJECTED`
- `WITHDRAWN`

Consequential outcomes are appended as immutable `PublicationDecision` records. The current projection/pointer is updated transactionally to the latest applicable decision. `NOT_EVALUATED` and `VERIFYING` are workflow/projection states and do not need to masquerade as completed immutable decisions.

Conceptual immutable decision record:

```text
PublicationDecision
├── decision_id
├── canonical_job_id
├── verification_id
├── state
├── reason_codes[]
├── decided_at
├── valid_until?
└── policy_version
```

### 22.1 Core publication rules

A job may become `PUBLISHABLE` when all required conditions hold:

- source rollout state is eligible;
- company identity is sufficient;
- listing lifecycle is sufficiently current;
- apply destination is allowed;
- Trust Engine classification is publication-eligible;
- no publication hard gate is active;
- critical evidence is not unknown;
- verification snapshot is valid.

A single Tier 1 authoritative source may satisfy the source-evidence requirement.

Five Tier 3 mirrors do not.

---

## 23. Lifecycle vs Publication

These are separate state machines.

Lifecycle states include existing semantics:

- `ACTIVE`
- `UPDATED`
- `STALE`
- `CLOSED`
- `REOPENED`

Publication states are defined above.

Valid combinations include:

```text
Lifecycle = ACTIVE
Publication = QUARANTINED
```

and:

```text
Lifecycle = CLOSED
Publication = WITHDRAWN
```

`ACTIVE` means the listing appears active in source evidence. It never means "allowed in public feed."

---

## 24. Freshness and Reverification

### 24.1 Inputs

Reverification scheduling considers:

- source tier;
- source health;
- source historical reliability;
- last authoritative observation;
- job age;
- explicit expiration date;
- prior change frequency;
- verification confidence;
- current publication state.

### 24.2 Expiry

Every verification snapshot has `evaluated_at` and `valid_until`.

After `valid_until`, the old verification cannot silently authorize continued publication.

Policy may temporarily withdraw or review jobs whose verification is overdue.

### 24.3 Closure

Authoritative closure evidence has high lifecycle authority.

When an authoritative requisition is confirmed closed:

1. lifecycle becomes `CLOSED`;
2. publication becomes `WITHDRAWN`;
3. the job disappears from active catalog queries;
4. history and evidence remain available internally.

If it reappears:

1. lifecycle may become `REOPENED`;
2. fresh verification is mandatory;
3. prior publication permission is not automatically reused.

Rate limiting, timeout, or adapter failure are not closure evidence.

---

## 25. Source Circuit Breaker

Source quality degradation must be isolated.

Signals may include:

- rising parse error rate;
- unexpected empty payload rate;
- schema change;
- repeated rate limits;
- authentication breakage;
- company identity mismatch spike;
- verification rejection spike;
- anomalous data volume.

A source may be demoted from `ACTIVE` to `DEGRADED`, `SHADOW`, `DISABLED`, or `POLICY_BLOCKED`.

Existing jobs remain publishable only if their still-valid evidence does not depend on now-invalid authority and publication policy continues to permit them.

---

## 26. Human Review Queue

### 26.1 VerificationCase

Conceptual record:

```text
VerificationCase
├── case_id
├── canonical_job_id
├── verification_id
├── reason_codes[]
├── priority
├── state
├── opened_at
├── assigned_to?
├── resolved_at?
└── resolution_id?
```

States:

- `OPEN`
- `IN_REVIEW`
- `DEFERRED`
- `RESOLVED`
- `SUPERSEDED`

### 26.2 Review priority

High-priority examples:

- possible impersonation;
- suspicious payment;
- apply-domain mismatch;
- credential-harvesting indicators.

Lower-priority examples:

- possible duplicate;
- non-critical field conflict.

### 26.3 VerificationResolution

```text
VerificationResolution
├── resolution_id
├── reviewer_id
├── evidence_snapshot_id
├── decision
├── reason_codes[]
├── notes?
└── decided_at
```

The reviewer acts on an immutable evidence snapshot.

If current evidence has advanced beyond the reviewed snapshot, mutation returns a stale-context conflict and requires a refresh.

AI is never stored as the human reviewer identity.

A human resolution does not directly mutate the catalog. It becomes an authorized input to a new verification/publication reevaluation. Hard gates and publication policy still apply.

---

## 27. Public Catalog Boundary

The public website must not query raw ingestion tables or Trust Engine tables.

Candidate-facing APIs are bounded around the catalog.

Minimum conceptual endpoints:

```text
GET /api/catalog/jobs
GET /api/catalog/jobs/{job_id}
GET /api/catalog/jobs/{job_id}/verification
```

### 27.1 Catalog visibility

`GET /api/catalog/jobs` returns only jobs with currently effective `PUBLISHABLE` decisions and eligible lifecycle state.

### 27.2 Public job shape

Conceptual fields:

```text
PublicJob
├── canonical_job_id
├── title
├── company
├── location
├── employment_type
├── salary?
├── source_published_at?
├── catalog_published_at?
├── apply_destination
├── lifecycle
├── verification_summary
│   ├── confidence
│   ├── checked_at
│   ├── appearance_count
│   ├── independent_evidence_family_count
│   └── primary_reason_codes[]
└── source_attribution[]
```

The public verification response may expose useful provenance and reason codes, but not:

- raw payloads;
- credentials;
- private reviewer notes;
- internal fetch errors;
- secret source metadata;
- security-sensitive rule internals.

---

## 28. Internal API Boundary

Operational endpoints are separate from candidate APIs.

Conceptual namespaces:

```text
/internal/sources/*
/internal/verification/*
/internal/review/*
/internal/quarantine/*
```

Internal mutation endpoints require explicit authorization, idempotency for consequential writes, and optimistic concurrency where state may have changed.

---

## 29. Fetch Security and SSRF Defense

Any shared fetch layer used by adapters or destination verification must enforce:

- HTTP(S) only;
- no loopback targets;
- no private-network targets;
- no link-local targets;
- no cloud metadata endpoints;
- DNS/IP validation across redirects;
- redirect depth limits;
- size/time limits;
- source-specific allow/deny policy where appropriate;
- no credential forwarding to unrelated redirect domains;
- no `file://` or other local schemes.

Payload-supplied URLs are untrusted input.

This security boundary applies even when the original source is trusted.

---

## 30. Credentials and Secret Handling

Connector/API credentials:

- never enter observations;
- never enter raw evidence;
- never enter logs in plaintext;
- never enter catalog responses;
- never become evidence references.

Authentication failures affect source health; they do not create job-risk evidence.

---

## 31. Transaction and Failure Semantics

### 31.1 Ingestion durability

Raw observation/evidence persistence should remain independently durable from downstream verification.

Verification failure must not roll back successfully collected evidence.

### 31.2 Publication atomicity

Within the publication boundary, the following must remain consistent:

- verification snapshot reference;
- publication decision;
- review case creation/update where required;
- catalog projection/update;
- event/outbox record where used.

A transaction failure leaves the old consistent publication state intact.

### 31.3 Failure classes

Required semantic distinctions:

```text
source timeout
→ operational failure

HTTP 429
→ source rate limited

authoritative 404 / explicit closed status
→ possible closure evidence

identity resolver crash
→ system failure, do not publish

company ownership unknown
→ domain uncertainty

Trust Engine crash
→ system failure, do not publish

review system unavailable
→ review remains pending
```

No silent fallback from contextual verification failure to legacy public visibility.

---

## 32. Reverification Runner

Slice 4A requires a persistent scheduler boundary without introducing distributed infrastructure prematurely.

Conceptual flow:

```text
ReverificationScheduler
        ↓
due verification work
        ↓
refresh source evidence where permitted
        ↓
new observations
        ↓
verification
        ↓
publication reevaluation
```

Requirements:

- due work survives process restart;
- retries are bounded;
- exponential backoff is used for retryable operational failures;
- rate-limit responses influence source health and retry timing;
- repeated permanent failures do not hot-loop;
- scheduler activity is observable.

Implementation may begin in-process/CLI-driven if persistence and deterministic behavior are preserved.

---

## 33. Observability

Metrics must measure catalog quality, not collection vanity.

Required operational metrics include:

- observations received;
- collection run success/partial/failure;
- canonical jobs produced;
- identity resolution outcomes;
- dedup `AMBIGUOUS` rate;
- verification outcome distribution;
- publication outcome distribution;
- review queue depth and age;
- hard-block rate;
- source failure and schema-change rate;
- reverification overdue count;
- authoritative closure withdrawal count;
- catalog freshness age;
- time from observation to publishable decision;
- reviewer disagreement/feedback where available.

Success is not "millions of scraped URLs."

Primary quality indicators are:

- publishable precision;
- freshness;
- verified source coverage;
- verification latency;
- false-positive/false-negative review feedback.

---

## 34. Security and Adversarial Corpus

Slice 4A adds permanent adversarial fixtures for at least:

- lookalike company domains;
- punycode/Unicode impersonation;
- fake official-looking ATS tenant;
- redirects to unrelated domains;
- redirects to private/local targets;
- multiple mirrors from one upstream origin;
- salary bait;
- stale discovery mirror after official closure;
- payment request;
- payment-request negation;
- OTP/password/PIN/recovery-code requests;
- bank/identity-document request contexts;
- conflicting company identity;
- malformed collector payload;
- source schema change;
- abnormal empty batch;
- source timeout;
- source rate limiting;
- stale reviewer snapshot;
- blocked publication with preserved evidence.

Any real production failure that escapes the corpus should be captured as a regression fixture after diagnosis.

---

## 35. Testing Strategy

### 35.1 Unit tests

Cover:

- source registry policies;
- rollout transitions;
- source health;
- identity graph rules;
- dedup resolution;
- evidence-family behavior;
- destination verification;
- freshness;
- publication policy;
- review state transitions;
- scheduler selection/retry policy.

### 35.2 Contract tests

Every source adapter must pass the shared adapter contract suite.

### 35.3 Invariant/property tests

At minimum:

- canonical existence never implies publishable state;
- raw source count never substitutes for independent evidence families;
- confirmed hard block never becomes publishable;
- UNKNOWN never silently becomes SAFE;
- official closure cannot remain visible in active catalog after successful reevaluation;
- review resolution cannot apply to a newer evidence snapshot without revalidation;
- system failure cannot silently fallback to publishable;
- Tier 3 discovery-only evidence cannot self-promote to authoritative publication.

### 35.4 Integration tests

End-to-end flow:

`collector → observation → canonicalization → identity → trust → verification → publication → catalog`

### 35.5 Failure injection

Inject failures in:

- database writes;
- identity resolver;
- Trust Engine call;
- publication transaction;
- source fetch;
- source parse;
- scheduler retry;
- review concurrency.

### 35.6 Security tests

Cover:

- SSRF;
- redirect abuse;
- secret leakage;
- authorization;
- raw evidence exposure;
- reviewer write access;
- stale review writes.

### 35.7 Regression requirement

All existing tests must remain green. The pre-Slice-4A verified baseline is 513 passing tests with one known deprecation warning.

---

## 36. Rollout Plan

### Phase 0 — Foundations

Introduce models, migrations, source registry, verification/publication states, and repository boundaries without changing public behavior.

### Phase 1 — Existing ATS collectors in shadow

Run Greenhouse, Lever, and Ashby through the new source registry and verification architecture in shadow.

No new public catalog authority yet.

### Phase 2 — Compare old and new canonicalization

Measure:

- canonical IDs;
- duplicate decisions;
- evidence families;
- material field consensus;
- identity outcomes.

Resolve unacceptable regressions before promotion.

### Phase 3 — Internal publication catalog

Enable publication decisions and catalog projection internally.

No candidate-facing dependency is required yet.

### Phase 4 — Freshness and source health

Enable reverification scheduling, source health, circuit breaker, and withdrawal semantics.

### Phase 5 — Validated Tier 1 Indonesia sources

Add/validate Indonesia-priority official/company/ATS/government sources through the same adapter and source-registry contracts.

### Phase 6 — Tier 2 authorized sources

Enable authorized APIs/feeds after compliance and data-quality validation.

### Phase 7 — Tier 3 discovery shadow

Discovery sources remain shadow-only until independent evidence and policy justify promotion behavior.

A Tier 3 source never gains authority merely from volume.

---

## 37. API Compatibility and Migration

### 37.1 Existing `/api/jobs`

Slice 4A must not silently change legacy `/api/jobs` semantics unless the implementation plan explicitly introduces a compatibility bridge and tests it.

The preferred future direction is for 4B/4C to use `/api/catalog/*`.

### 37.2 Database migrations

The current migration directory reaches `006_career_intent_context.sql`.

The implementation plan must perform a fresh migration-number preflight against `main` before assigning Slice 4A migration filenames. It must not assume `007` without checking for concurrent work.

Migrations must be additive where practical and preserve existing data.

### 37.3 Existing canonical tables

Where current tables can be evolved safely, prefer migration/extension over duplicate replacement tables.

Where semantics differ materially—for example publication state vs lifecycle state—use separate explicit structures rather than overloading old columns.

---

## 38. Anti-Slop DURING Quality Gate

The user approved Anti-Slop `DURING` and all available Anti-Slop skills.

For Slice 4A, the directly relevant quality rules are:

- architecture must not introduce abstractions only to look "enterprise";
- service/repository types require clear authority and a concrete dependency boundary;
- code comments explain non-obvious constraints, trade-offs, security semantics, or business rules;
- remove decorative separators, ALL CAPS comment banners, workflow narration, obvious restatements, decorative emoji, and vague TODOs;
- evidence claims in public/API-facing text must be backed by actual evidence;
- later UI surfaces must use dedicated UI/copy/human/mobile Anti-Slop skills and `DESIGN.md` direction.

The repository setup approved earlier should be performed during implementation preparation:

- place the user-supplied Anti-Slop release in the approved project skill location without downloading a different version;
- add or update the project agent entry file pointer block;
- do not mix Anti-Slop versions;
- do not silently overwrite unrelated agent instructions.

Anti-Slop is a filter, not a product design direction. Website visual identity will be defined in Slice 4B with a user-reviewed `DESIGN.md`.

---

## 39. Acceptance Scenarios

Slice 4A is not complete merely because models exist.

### 39.1 Authoritative publish scenario

Given:

- one authoritative ATS listing;
- verified ATS-to-company relationship;
- valid company identity;
- allowed apply destination;
- fresh listing;
- no hard-risk signals;
- eligible Trust classification;

Then:

1. observation is persisted;
2. source appearance is linked;
3. canonical job/version is produced;
4. verification snapshot is created;
5. publication decision becomes `PUBLISHABLE`;
6. job appears in the Catalog API.

A second independent source is not mandatory.

### 39.2 Official closure scenario

Given a previously publishable authoritative ATS requisition:

1. authoritative source confirms closure/removal;
2. new evidence is stored;
3. lifecycle becomes `CLOSED`;
4. publication becomes `WITHDRAWN`;
5. active catalog no longer returns the job;
6. prior evidence and history remain queryable internally.

### 39.3 Scam/impersonation scenario

Given:

- a Tier 3 discovery appearance;
- company impersonation evidence;
- suspicious recruitment payment request;

Then:

1. evidence is preserved;
2. hard risk signals are created;
3. verification cannot become publication-eligible;
4. publication becomes `REJECTED` or the stronger policy-equivalent;
5. job never appears in the active catalog.

### 39.4 Mirror lineage scenario

Given three source appearances that all originate from one ATS:

- all three appearances are retained;
- independent evidence-family count remains one;
- corroboration confidence does not receive three independent boosts.

### 39.5 Ambiguous duplicate scenario

Given two very similar listings without a decisive requisition identity:

- resolver returns `AMBIGUOUS`;
- the system does not silently merge;
- possible-duplicate review/holding behavior is invoked.

### 39.6 System failure scenario

Given Trust Engine or identity resolver failure:

- successfully collected evidence remains durable;
- no new publishable decision is created;
- existing consistent publication state is not corrupted;
- failure is observable and retryable/reviewable according to class.

---

## 40. Non-Functional Requirements

### 40.1 Determinism

For the same domain inputs, policy versions, evidence snapshots, and clock value, core identity/verification/publication decisions should be deterministic.

### 40.2 Explainability

Every publication decision must have machine-readable reason codes and references to the verification snapshot that caused it.

### 40.3 Auditability

Historical decisions remain reconstructable by version and timestamp.

### 40.4 Idempotency

Repeated collection or command processing must not create duplicate irreversible state.

### 40.5 Concurrency

Consequential reviewer/source-state/publication mutations must detect stale context rather than last-write-wins silently.

### 40.6 Global-ready domain model

Currency, country, location, domain, and source identifiers must not assume Indonesia even though initial rollout prioritizes Indonesia.

---

## 41. Design Risks and Mitigations

### Risk: false confidence from famous platforms

**Mitigation:** source authority is evidence-based and relationship-aware, not brand-name based.

### Risk: mirror amplification

**Mitigation:** evidence-family lineage and independent-family counting.

### Risk: aggressive dedup hides distinct jobs

**Mitigation:** three-way `SAME | DISTINCT | AMBIGUOUS` resolution.

### Risk: verified job becomes stale or hijacked

**Mitigation:** expiring verification snapshots, active reverification, redirect re-checking.

### Risk: one broken adapter pollutes the catalog

**Mitigation:** per-source health and circuit breaker.

### Risk: review queue explosion

**Mitigation:** deterministic automation for clear cases, priority queue for ambiguity, Tier 3 shadow posture.

### Risk: AI becomes hidden authority

**Mitigation:** AI outputs are advisory signals/summaries only; policy authority remains deterministic/evidence-based.

### Risk: architecture becomes over-engineered

**Mitigation:** modular monolith boundaries, existing SQLite/repository patterns, no queue/microservice infrastructure without measured need.

### Risk: source acquisition violates policy

**Mitigation:** explicit acquisition method and compliance state; unsupported/unknown sources remain disabled/shadow.

---

## 42. Definition of Done for Slice 4A

Slice 4A may be declared complete only when all of the following are true:

- approved data/state boundaries are implemented;
- existing ATS collectors work through the new contracts;
- source registry and rollout states are persistent;
- company identity relationship verification exists;
- canonical jobs and source appearances are separated;
- evidence-family lineage affects corroboration;
- verification snapshots are immutable;
- publication state is distinct from lifecycle;
- catalog query returns only eligible publishable jobs;
- apply destination verification is enforced;
- reverification can withdraw stale/closed jobs;
- review queue supports stale-context protection;
- SSRF/redirect defenses are tested;
- critical failure-injection tests pass;
- adversarial security corpus passes;
- all pre-existing tests remain green;
- `git diff --check` is clean;
- working tree is clean at release verification;
- feature branch is pushed and ready for PR;
- no Anti-Slop quality gate is knowingly violated.

---

## 43. Handoff to Later Slices

### Slice 4B — Website Foundation

Consumes stable catalog and career APIs. Adds responsive shell, auth/session boundary, Today/Jobs/Career/Activity/You navigation, design system, and `DESIGN.md`.

### Slice 4C — Jobs Experience

Consumes `/api/catalog/*` for verified job feed, job detail, verification evidence, matching explanation, filters, saved jobs, and closed/stale handling.

### Slice 4D — Career Workspace

Builds user-facing Career Twin, Intent, Targets, approvals, review workflows, and settings.

Slice 4A must not pre-design these UIs beyond what its public data contracts require.

---

## 44. Final Design Summary

Slice 4A establishes a simple authority chain:

```text
SOURCE MAY DISCOVER
        ↓
ADAPTER MAY OBSERVE
        ↓
INGESTION MAY PRESERVE
        ↓
CANONICALIZATION MAY RESOLVE
        ↓
IDENTITY MAY ESTABLISH RELATIONSHIPS
        ↓
TRUST MAY ASSESS RISK
        ↓
VERIFICATION MAY ASSEMBLE EVIDENCE
        ↓
PUBLICATION POLICY MAY AUTHORIZE
        ↓
CATALOG MAY EXPOSE
```

No earlier layer may skip the authority of a later layer.

That boundary is the core of GaweYuk's trustworthy job network.

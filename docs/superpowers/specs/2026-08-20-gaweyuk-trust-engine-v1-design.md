# GaweYuk Trust Engine v1 — Architecture & Safety Design

**Date:** 2026-08-20
**Status:** Approved design, pending written-spec review
**Project:** GaweYuk
**Subsystem:** 6D — Trust Engine v1
**Primary principle:** Privacy & Security > Automation > Convenience

## 1. Purpose

GaweYuk Trust Engine v1 evaluates whether a job opportunity and its surrounding recruitment flow are trustworthy enough for browsing, assisted application, or automation.

The engine must be explainable, deterministic at the decision layer, evidence-driven, privacy-first, conservative around sensitive actions, resilient to missing data and component failures, historically auditable, inexpensive to operate before revenue, and extensible toward a future TrustGraph without requiring a graph database in v1.

The Trust Engine is not a generic scam-probability model. It is an enforcement-aware safety system that converts evidence into explicit, versioned permissions.

## 2. Non-Negotiable Principles

1. Privacy & security are priority #1.
2. Trust score is not consent.
3. High trust cannot override hard safety gates.
4. AI may extract signals, but AI does not make final enforcement decisions.
5. Missing evidence is not negative evidence.
6. System failure is not scam evidence.
7. Low confidence is not automatically low trust.
8. Old trust does not authorize a current sensitive action.
9. Credential, OTP, PIN, password, recovery code, and authentication-secret handling is never delegated to an application agent.
10. GaweYuk never executes recruitment-related payments or transfers.
11. Sensitive-document submission requires context validation and explicit, scoped user consent.
12. Historical trust evaluations are immutable.
13. Every safety-relevant decision must be explainable from evidence and policy version.
14. Paid infrastructure must have measurable value, a cap, a fallback, and a monetization justification.

## 3. Scope

### In scope
- trust-signal extraction;
- deterministic hard-gate enforcement;
- multidimensional trust scoring;
- trust confidence;
- recruitment-stage-aware privacy policy;
- ALLOW / REVIEW / BLOCK decisions;
- tiered overrides;
- immutable trust-evaluation snapshots;
- signal lifecycle;
- action-time revalidation;
- consent enforcement;
- audit events;
- failure handling;
- source-health influence;
- evidence provenance;
- relational TrustGraph foundation;
- shadow-mode rollout;
- security regression corpus;
- cost guardrails.

### Out of scope
- dedicated graph database;
- full ML fraud classifier;
- autonomous web-investigation agent;
- cross-company global fraud network;
- biometric identity verification;
- document authenticity verification;
- any automated payment or transfer;
- arbitrary credential handling.

## 4. Architecture

GaweYuk uses a layered trust pipeline:

```text
Raw Job / Recruiter / Form
            |
            v
Signal Extractors
deterministic + AI sensors
            |
            v
Trust Evidence Ledger
provenance + timestamp
            |
            v
Risk Evaluators
identity / source / scam / privacy / freshness
            |
            v
Trust Score Engine
dimensions + overall + confidence
            |
            v
Hard-Gate Policy Engine
ALLOW / REVIEW / BLOCK
            |
            v
Explainability + Audit
```

This extends the existing canonical jobs, source links, field evidence, field consensus, field conflicts, lifecycle, and source-health foundation instead of creating a parallel source of truth.

## 5. AI Boundary

AI is a structured signal extractor only.

Accepted output example:

```yaml
signal_type: RECRUITMENT_PAYMENT
value: true
confidence: 0.91
evidence_reference: observation:abc123#span17
extractor_version: trust-ai-1
```

AI does not have authority to directly set a final trust decision. Policy enforcement is deterministic.

Job descriptions, forms, recruiter messages, and websites are untrusted data. Prompt-injection text must never alter policy, thresholds, hard gates, consent rules, source authority, or system configuration.

## 6. Recruitment Stages

```text
DISCOVERY
APPLICATION
SCREENING
INTERVIEW
OFFER
ONBOARDING
UNKNOWN
```

UNKNOWN is treated conservatively. The same data request may produce different policy outcomes by stage.

## 7. Trust Dimensions

| Dimension | Weight | Description |
|---|---:|---|
| Company Identity | 18% | legal/name consistency, official domain evidence |
| Source Credibility | 16% | source provenance, ATS/portal authority, source health |
| Listing Integrity | 14% | title/location/salary/contact plausibility and history |
| Evidence Consensus | 14% | independent support and unresolved conflicts |
| Recruiter Integrity | 14% | recruiter identity and contact/domain consistency |
| Privacy Safety | 16% | data requests relative to stage and sensitivity |
| Freshness & Lifecycle | 8% | listing age, recent confirmation, stale/closed/reopened state |

Dimension state:

```text
KNOWN
UNKNOWN
NOT_APPLICABLE
```

UNKNOWN reduces confidence. NOT_APPLICABLE does not.

Missing data is never silently converted to 0 or 50.

## 8. Overall Trust vs Trust Confidence

Overall Trust answers how trustworthy the opportunity appears.

Trust Confidence answers how strongly the evidence supports that assessment.

A high score with low confidence does not authorize autonomy.

## 9. Hard Red-Flag Taxonomy

### L4 — ABSOLUTE_BLOCK

Examples:

```text
CREDENTIAL_REQUEST
OTP_REQUEST
PIN_REQUEST
PASSWORD_REQUEST
RECOVERY_CODE_REQUEST
AUTHENTICATION_SECRET_REQUEST
```

No automation override.

### L3 — AUTOMATION_BLOCK

Examples:

```text
RECRUITMENT_PAYMENT
DEPOSIT_REQUEST
TRANSFER_REQUEST
CARD_IMAGE_REQUEST
EARLY_IDENTITY_DOCUMENT
EARLY_BANK_DATA
CONFIRMED_DOMAIN_IMPERSONATION
```

Autopilot is blocked. Some context-sensitive categories may permit manual override. Payment execution remains permanently unavailable.

### L2 — REVIEW_REQUIRED

Examples:

```text
RECRUITER_DOMAIN_MISMATCH
COMPANY_IDENTITY_MISMATCH
EXTREME_SALARY_ANOMALY
UNRESOLVED_CRITICAL_CONFLICT
URGENCY_MANIPULATION
OFF_PLATFORM_CONTACT_PRESSURE
```

### L1 — SCORE_SIGNAL

Examples:

```text
STALE_LISTING
THIN_DESCRIPTION
SINGLE_SOURCE_ONLY
FREE_EMAIL_RECRUITER
MINOR_SOURCE_DEGRADATION
```

## 10. Context-Aware Privacy Gate

Credentials and authentication secrets are L4 at every stage.

Recruitment fees, deposits, and transfer requests are L3. GaweYuk never performs the payment.

Requests for KTP, KK, NPWP, bank data, or card images during early recruitment block automation or require strict review.

During verified OFFER/ONBOARDING, identity/financial documents may be allowed only when company context is verified, policy allows the action, and the user gives explicit scoped consent.

## 11. Sensitive Action Barrier

Core invariant:

```text
TRUST != CONSENT
```

Sensitive action requires:

```text
verified context
+ policy allows action
+ current trust authorization
+ explicit scoped user consent
```

## 12. Policy Matrix

| Classification | Overall | Confidence | Critical floor | Hard gates |
|---|---:|---:|---:|---|
| AUTOPILOT_ELIGIBLE | >= 85 | >= 80 | >= 70 | no L2+ |
| ASSISTED_ALLOWED | >= 70 | >= 60 | >= 55 | no L2+ |
| REVIEW_REQUIRED | >= 60 or uncertainty | variable | >= 40 | L2 allowed |
| AUTOMATION_BLOCKED | < 60 or critical < 40 | any | < 40 | L3 |
| ABSOLUTE_BLOCK | any | any | any | L4 |

Hard gates always take precedence over numerical thresholds.

## 13. Tiered Override Policy

- L1: no override required.
- L2: user review/acknowledgement can permit assisted action where safe.
- L3: Autopilot cannot override. Manual override exists only for specifically overrideable context-sensitive categories, with explicit reason and consent.
- L4: no automation override.

Override activity is recorded separately and does not rewrite the original evaluation.

## 14. Trust Signal Persistence

New concept: `trust_signals`.

Conceptual fields:

```text
signal_id
canonical_job_id
signal_type
level
status
confidence
detection_method
context_stage
evidence_refs
extractor_version
first_seen_at
last_seen_at
resolved_at
resolution_reason
fingerprint
```

Status:

```text
ACTIVE
RESOLVED
EXPIRED
```

Signals are not deleted.

## 15. Signal Dedupe

Repeated ingestion must not create repeated identical active signals.

Fingerprint is based conceptually on:

```text
canonical job
+ signal type
+ upstream evidence family
+ normalized evidence
```

## 16. Immutable Trust Evaluations

New concept: `trust_evaluations`.

```text
evaluation_id
canonical_job_id
recruitment_stage
policy_version
overall_score
trust_confidence
classification
evaluated_at
valid_until
input_fingerprint
active_signal_ids
unknown_dimensions
allowed_actions
blocked_actions
override_policy
primary_reason_codes
evidence_refs
```

Current trust state is derived from the latest valid successful evaluation. No independent mutable `current_trust` source of truth is required.

## 17. Trust Dimension Persistence

New concept: `trust_dimension_scores`.

```text
evaluation_id
dimension_name
state
score
confidence
reason_codes
evidence_refs
```

## 18. Hard-Gate Persistence

New concept: `trust_gate_hits`.

```text
evaluation_id
signal_id
gate_code
level
effect
override_policy
```

## 19. Action Audit

New concept: `trust_action_events`.

```text
action_event_id
canonical_job_id
evaluation_id
action_type
requested_mode
result
reason_codes
consent_id
override_id
occurred_at
```

Evaluation records what was allowed. Action events record what actually happened.

## 20. Consent Model

Consent is explicit, scoped, contextual, expiring, and auditable.

```text
consent_id
user_id
job_id
company_id
scope
stage
issued_at
expires_at
revoked_at
```

Consent for KTP onboarding does not authorize bank account, KK, NPWP, or unrelated sensitive data.

## 21. Relational TrustGraph Foundation

No graph database in v1.

A relational link layer may represent:

```text
from_entity_type
from_entity_id
relation_type
to_entity_type
to_entity_id
confidence
evidence_refs
status
first_seen_at
last_seen_at
```

Examples:

```text
COMPANY USES_DOMAIN DOMAIN
RECRUITER CONTACTS_FOR JOB
DOMAIN IMPERSONATES COMPANY
JOB PUBLISHED_BY SOURCE
```

## 22. Event-Driven Recalculation

Re-evaluate on material events:

```text
NEW_OBSERVATION
FIELD_CONSENSUS_CHANGED
CONFLICT_OPENED
CONFLICT_RESOLVED
TRUST_SIGNAL_CREATED
TRUST_SIGNAL_UPDATED
TRUST_SIGNAL_RESOLVED
SOURCE_HEALTH_CHANGED
JOB_LIFECYCLE_CHANGED
RECRUITER_EVIDENCE_CHANGED
DOMAIN_EVIDENCE_CHANGED
COMPANY_IDENTITY_CHANGED
RECRUITMENT_STAGE_CHANGED
POLICY_VERSION_CHANGED
```

If the input fingerprint is unchanged, do not create a duplicate evaluation.

## 23. Action-Time Revalidation

A safe evaluation is not a permanent authorization token.

Sensitive/autonomous action rechecks:

```text
latest successful evaluation
+ freshness
+ policy version
+ active hard gates
+ pending critical signals
+ consent when required
```

## 24. Failure Philosophy

```text
Missing data      != bad data
System failure    != scam evidence
Low confidence    != low trust
High trust        != permission
Old trust         != current permission
Hard safety flag  > score
```

AI extractor failure reduces coverage/confidence instead of creating scam evidence.

Source reliability and source trustworthiness remain separate.

A failed evaluation does not overwrite the last successful immutable evaluation.

## 25. Hysteresis

Soft numeric thresholds use hysteresis to prevent status oscillation.

Example:

```text
enter AUTOPILOT_ELIGIBLE >= 85
remain eligible while >= 82
leave eligibility < 82
```

L3/L4 hard gates bypass hysteresis.

## 26. Recalculation Priority

```text
P0 IMMEDIATE
- L4/L3 critical signal
- credential/payment/privacy-critical

P1 HIGH
- company identity change
- domain change
- critical conflict opened

P2 NORMAL
- new source
- consensus change
- source health change

P3 BACKGROUND
- freshness decay
- policy migration
- maintenance
```

## 27. Autopilot Safety Barrier

Autopilot requires:

```text
latest successful evaluation
current policy version
sufficient confidence
evaluation fresh enough
no pending critical signal
no active L3/L4 gate
all required critical dimension floors satisfied
```

If any condition fails, Autopilot does not run.

## 28. Security Testing Invariants

Build-breaking invariants:

```text
OTP_REQUEST -> Autopilot never allowed
PASSWORD_REQUEST -> Assisted execution never allowed
RECRUITMENT_PAYMENT -> automation never allowed
Sensitive document -> never sent without explicit scoped consent
L4 -> cannot be downgraded by high trust score
Low confidence -> cannot become autopilot eligible
Expired evaluation -> cannot authorize sensitive action
Failed audit write -> sensitive action does not execute
```

Testing covers signal extraction, negation, adversarial patterns, privacy-stage matrix, deterministic scoring, UNKNOWN vs NOT_APPLICABLE, hard-gate precedence, historical immutability, action authorization, scoped consent, AI authority boundary, and prompt-injection resistance.

## 29. Data Minimization & Redaction

Detecting a secret does not authorize persisting it.

If an OTP/password is encountered, persist only metadata such as:

```text
credential_type
detected = true
value = REDACTED
```

Never persist secrets in trust signals, audit logs, error messages, or debug traces.

## 30. Rollout

### Phase 1 — Shadow Mode
Record what the engine would decide without altering behavior.

### Phase 2 — Critical Enforcement
Enable L4 absolute blocks and L3 automation blocks.

### Phase 3 — Assisted Enforcement
Trust controls ASSISTED_ALLOWED / REVIEW_REQUIRED / AUTOMATION_BLOCKED.

### Phase 4 — Autopilot Eligibility
Only after sufficient validation does AUTOPILOT_ELIGIBLE grant autonomous privileges.

Autopilot receives privilege last.

## 31. Kill Switches

```text
AUTOPILOT_ENABLED = false
SENSITIVE_DOCUMENT_AUTOMATION = false
PAYMENT_ACTIONS = permanently false
CREDENTIAL_ACTIONS = permanently false
```

If consent/audit persistence fails, sensitive action does not execute.

## 32. Security Regression Corpus

Maintain:

```text
tests/security_cases/
```

Examples:

```text
payment_deposit.json
fake_recruiter_domain.json
otp_request.json
early_ktp.json
legit_onboarding_ktp.json
negated_payment_warning.json
```

Every fixed security defect becomes a permanent regression case.

## 33. Financial Sustainability Guardrail

### Pre-revenue

Target recurring paid spend:

```text
Rp0
```

Emergency/essential-spend guideline:

```text
<= Rp100,000/month
```

Paid AI, proxies, and always-on infrastructure remain off unless clearly necessary.

### Post-revenue

Technology/AI/infrastructure spend cap:

```text
<= 20% of realized trailing-30-day revenue
```

This is a ceiling, not a target. Scaling uses realized revenue, not projected revenue.

Target gross margin:

```text
>= 80%
```

### Cost circuit breaker

If cost/revenue exceeds 20%, AI spend spikes abnormally, or cost per successful application materially worsens:

```text
pause scale-up
prefer deterministic/local processing
reduce AI to ambiguous cases
pause expensive collectors where possible
```

No paid dependency without:

```text
1. measurable value
2. budget cap
3. fallback path
4. monetization justification
5. kill switch
```

## 34. Cost-Aware Trust Execution

Prefer:

```text
deterministic rules
local normalization
existing evidence
SQLite/Postgres queries
cached domain/source facts
```

before paid AI or expensive crawling.

AI is an escalation path for ambiguous cases, not the default for every record.

## 35. Acceptance Criteria

Trust Engine v1 is implemented when:

1. trust signals persist with provenance and lifecycle;
2. seven trust dimensions score independently;
3. overall trust and trust confidence are separate;
4. UNKNOWN and NOT_APPLICABLE are distinct;
5. L4/L3/L2/L1 taxonomy is deterministic;
6. hard gates override numerical score;
7. recruitment stage influences privacy policy;
8. sensitive actions require explicit scoped consent;
9. trust evaluations are immutable and policy-versioned;
10. action-time revalidation exists;
11. stale evaluation cannot authorize sensitive/autonomous action;
12. signal resolution creates a new evaluation rather than rewriting history;
13. source outage reduces confidence/reliability rather than creating scam accusations;
14. AI output cannot directly enforce a block;
15. untrusted content cannot modify policy;
16. secrets are redacted and not persisted;
17. failed audit persistence prevents sensitive execution;
18. kill switches exist;
19. shadow-mode rollout exists;
20. security regression corpus exists;
21. paid dependencies remain behind cost guardrails and fallbacks;
22. the full existing GaweYuk regression suite remains green.

## 36. Final Trust Contract

```text
TrustDecision

overall_score
confidence

dimensions:
  company_identity
  source_credibility
  listing_integrity
  evidence_consensus
  recruiter_integrity
  privacy_safety
  freshness

classification:
  AUTOPILOT_ELIGIBLE
  ASSISTED_ALLOWED
  REVIEW_REQUIRED
  AUTOMATION_BLOCKED
  ABSOLUTE_BLOCK

hard_gates[]
risk_signals[]
unknown_dimensions[]
not_applicable_dimensions[]

allowed_actions[]
blocked_actions[]
override_policy

primary_reasons[]
evidence_refs[]

recruitment_stage
evaluated_at
valid_until
input_fingerprint
policy_version
```

## 37. Final Priority Order

```text
1. PRIVACY & SECURITY
2. USER CONSENT
3. EVIDENCE & EXPLAINABILITY
4. RELIABILITY
5. PRODUCT VALUE
6. COST EFFICIENCY
7. AUTOMATION SPEED
8. CONVENIENCE
```

The product must never silently trade a higher-ranked property for a lower-ranked one.

## 38. Conclusion

GaweYuk Trust Engine v1 is a deterministic, explainable safety-control layer built on the existing evidence and canonicalization pipeline.

It establishes durable contracts for safer assisted application, carefully gated Autopilot, future TrustGraph capabilities, stronger fraud detection, and sustainable infrastructure growth.

Guiding rule:

```text
PRIVACY & SECURITY > AUTOMATION
CONSENT > TRUST SCORE
HARD SAFETY > AI
EVIDENCE > GUESS
REALIZED REVENUE > SPECULATIVE SPEND
```

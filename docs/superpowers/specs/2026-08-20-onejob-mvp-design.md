# ONEJOB MVP Design

## Goal
Build a runnable vertical slice of ONEJOB: a unified job market layer that normalizes jobs from multiple sources, deduplicates them, evaluates trust, matches them against a user's Career Twin and policy, generates safe application answers, and exposes the same data through Web and CLI interfaces.

## MVP Scope
1. Universal Job Schema with multi-source provenance.
2. Job Identity/Deduplication based on normalized company/title/location plus description similarity.
3. Career Twin with facts, preferences, and evidence.
4. Policy Engine with hard constraints and soft preferences.
5. Matching Engine with explainable evidence and negative evidence.
6. Trust Engine with source, contact, payment-request, salary-anomaly, and cross-source signals.
7. Answer Engine that distinguishes factual, preference, generative, and unknown questions; it may rephrase supported facts but must not invent them.
8. Decision Engine returning APPLY, REVIEW, SKIP, or BLOCK based on trust, policy, match, and answer confidence.
9. REST API, simple responsive web dashboard, and Termux-friendly CLI using the same core modules.
10. Demo seed data representing multiple platforms so the vertical slice can be exercised without external credentials.

## Non-goals for MVP
- Live scraping of LinkedIn/JobStreet/Indeed.
- Browser automation or auto-submit.
- Authentication/multi-user accounts.
- LLM calls or vector database.
- Production-grade persistent database.

These are intentionally deferred until the core decision model is testable.

## Architecture
The project uses a Python package split by responsibility. Core domain modules are pure Python and framework-agnostic. FastAPI is only an adapter around the core. The CLI uses the same service layer. Data is stored in an in-memory repository seeded from JSON for the MVP.

## Core Data Flow
Raw source jobs -> normalize -> deduplicate -> trust analysis -> match against Career Twin -> apply policy -> decision -> answer suggestions -> API/CLI/Web.

## Safety and Truth Rules
- No generated answer may contain a factual claim not backed by Career Twin evidence.
- Unknown personal questions return `needs_user_input` rather than guessing.
- Hard policy violations cannot be overridden by a high semantic match score.
- Trust scores are probabilistic and explainable; the UI must not label a job as definitively fake without hard evidence.
- Auto-apply is not implemented in MVP; decisions indicate eligibility only.

## Initial Scoring
Match score is deterministic for MVP: weighted role/skill/experience/location/preference signals with positive and negative evidence.
Trust score starts at 50 and adjusts from verifiable signals, clamped 0-100.
Decision logic:
- BLOCK: trust < 40 or a hard safety signal.
- SKIP: hard policy violation.
- APPLY: trust >= 75, match >= 80, no hard policy violation.
- REVIEW: all other cases.

## Interfaces
### Web/API
- `GET /api/jobs` ranked jobs
- `GET /api/jobs/{job_id}` details
- `GET /api/profile` current Career Twin
- `POST /api/answers/suggest` answer suggestion
- `GET /health`

### CLI
- `python -m onejob.cli jobs`
- `python -m onejob.cli job <id>`
- `python -m onejob.cli answer --job <id> --question "..."`

## Success Criteria
- Seeded jobs from multiple sources can collapse into a single canonical opportunity.
- At least one trusted/high-match job returns APPLY.
- A suspicious job returns BLOCK with explainable trust reasons.
- A high-match job that violates a hard salary policy returns SKIP.
- Answer engine produces evidence-backed answers and refuses unknown personal facts.
- Automated tests cover all above behaviors.

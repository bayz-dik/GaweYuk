# ONEJOB MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable ONEJOB vertical slice that unifies job records, evaluates trust and fit, applies user policy, suggests safe answers, and exposes results through web/API/CLI.

**Architecture:** Framework-agnostic Python domain modules hold models and engines. A service layer composes them over an in-memory repository. FastAPI and CLI are thin adapters. A static dashboard consumes the API.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, pytest, vanilla HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-08-20-onejob-mvp-design.md`

## Global Constraints
- No live platform scraping or auto-submit in MVP.
- No unsupported factual claims in generated application answers.
- Hard user policy constraints override match scores.
- Trust is probabilistic and must expose evidence.
- Core logic must be usable without FastAPI.

---

### Task 1: Domain Models and Normalization
**Files:**
- Create: `onejob/models.py`
- Create: `onejob/normalization.py`
- Test: `tests/test_normalization.py`

**Interfaces:**
- Produces: `RawJob`, `CanonicalJob`, `JobSource`, `normalize_job(raw: RawJob) -> CanonicalJob`.

- [ ] Write failing tests proving titles/companies/locations normalize and source provenance is retained.
- [ ] Run `pytest tests/test_normalization.py -q` and confirm RED.
- [ ] Implement minimal models and normalizer.
- [ ] Re-run test and confirm GREEN.

### Task 2: Deduplication
**Files:**
- Create: `onejob/dedupe.py`
- Test: `tests/test_dedupe.py`

**Interfaces:**
- Consumes: `CanonicalJob`.
- Produces: `deduplicate_jobs(jobs: list[CanonicalJob]) -> list[CanonicalJob]`.

- [ ] Write failing tests showing LinkedIn/JobStreet/company-site variants collapse while distinct jobs remain separate.
- [ ] Verify RED.
- [ ] Implement deterministic fingerprint + token similarity merge.
- [ ] Verify GREEN.

### Task 3: Career Twin, Policy, Match Engine
**Files:**
- Create: `onejob/profile.py`
- Create: `onejob/matching.py`
- Test: `tests/test_matching.py`

**Interfaces:**
- Produces: `CareerTwin`, `CareerPolicy`, `MatchResult`, `match_job(job, profile)`, `evaluate_policy(job, profile)`.

- [ ] Write failing tests for positive evidence, negative evidence, and hard salary rejection.
- [ ] Verify RED.
- [ ] Implement minimal deterministic matching and constraints.
- [ ] Verify GREEN.

### Task 4: Trust Engine
**Files:**
- Create: `onejob/trust.py`
- Test: `tests/test_trust.py`

**Interfaces:**
- Produces: `TrustResult`, `assess_trust(job) -> TrustResult`.

- [ ] Write failing tests for official-source confidence and payment/contact red flags.
- [ ] Verify RED.
- [ ] Implement explainable trust scoring with hard-risk flags.
- [ ] Verify GREEN.

### Task 5: Answer Engine and Decision Engine
**Files:**
- Create: `onejob/answers.py`
- Create: `onejob/decision.py`
- Test: `tests/test_answers.py`
- Test: `tests/test_decision.py`

**Interfaces:**
- Produces: `suggest_answer(question, job, profile)`, `decide(match, trust, policy_result)`.

- [ ] Write failing tests for factual answer, contextual supported narrative, unknown fact refusal, APPLY/BLOCK/SKIP decisions.
- [ ] Verify RED.
- [ ] Implement answer classifier/templates and decision rules.
- [ ] Verify GREEN.

### Task 6: Seed Repository and Service Layer
**Files:**
- Create: `onejob/repository.py`
- Create: `onejob/service.py`
- Create: `onejob/data/demo_jobs.json`
- Create: `onejob/data/demo_profile.json`
- Test: `tests/test_service.py`

**Interfaces:**
- Produces: `OneJobService.list_jobs()`, `get_job(id)`, `suggest_answer(id, question)`.

- [ ] Write failing end-to-end service test.
- [ ] Verify RED.
- [ ] Seed representative multi-source data and compose engines.
- [ ] Verify GREEN.

### Task 7: FastAPI, CLI, Dashboard
**Files:**
- Create: `onejob/api.py`
- Create: `onejob/cli.py`
- Create: `onejob/static/index.html`
- Create: `onejob/static/app.js`
- Create: `onejob/static/styles.css`
- Create: `requirements.txt`
- Create: `README.md`
- Test: `tests/test_api.py`

**Interfaces:**
- HTTP endpoints and Termux-friendly commands from the design spec.

- [ ] Write failing API smoke tests.
- [ ] Verify RED.
- [ ] Implement API/CLI/static dashboard adapters.
- [ ] Verify all tests GREEN with `pytest -q`.
- [ ] Run CLI smoke commands.
- [ ] Run FastAPI locally and curl `/health` and `/api/jobs`.

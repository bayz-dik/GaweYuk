from __future__ import annotations
from onejob.answers import suggest_answer
from onejob.decision import decide
from onejob.dedupe import deduplicate_jobs
from onejob.matching import evaluate_policy, match_job
from onejob.normalization import normalize_job
from onejob.repository import DemoRepository
from onejob.trust import assess_trust


class CareerTwinQueryNotConfigured(RuntimeError):
    pass

class OneJobService:
    def __init__(
        self,
        repo: DemoRepository,
        *,
        career_twin_query=None,
        career_context_service=None,
        has_active_intent=None,
    ):
        self.repo = repo
        self.career_twin_query = career_twin_query
        self.career_context_service = career_context_service
        self.has_active_intent = has_active_intent
        self.profile = repo.load_profile()
        self.jobs = deduplicate_jobs([normalize_job(raw) for raw in repo.load_jobs()])

    @classmethod
    def demo(cls) -> 'OneJobService':
        return cls(DemoRepository())

    def _evaluate(self, job):
        match = match_job(job, self.profile)
        policy = evaluate_policy(job, self.profile)
        trust = assess_trust(job)
        decision = decide(match, trust, policy)
        return {
            'id': job.id,
            'title': job.title,
            'company': job.company,
            'location': job.location,
            'salary_min': job.salary_min,
            'salary_max': job.salary_max,
            'sources': [s.model_dump() for s in job.sources],
            'match_score': match.score,
            'trust_score': trust.score,
            'decision': decision.status,
            'decision_reasons': decision.reasons,
            'positive_evidence': match.positive_evidence,
            'negative_evidence': match.negative_evidence,
            'trust_positive': trust.positive_reasons,
            'trust_risks': trust.risk_reasons,
        }

    def list_jobs(self) -> list[dict]:
        ranked = [self._evaluate(j) for j in self.jobs]
        priority = {'APPLY': 4, 'REVIEW': 3, 'SKIP': 2, 'BLOCK': 1}
        ranked.sort(key=lambda x: (priority[x['decision']], x['match_score'], x['trust_score']), reverse=True)
        return ranked

    def get_job(self, job_id: str) -> dict:
        job = next((j for j in self.jobs if j.id == job_id), None)
        if job is None:
            raise KeyError(job_id)
        data = self._evaluate(job)
        data['description'] = job.description
        data['skills'] = job.skills
        return data

    def suggest_answer(self, job_id: str, question: str) -> dict:
        job = next((j for j in self.jobs if j.id == job_id), None)
        if job is None:
            raise KeyError(job_id)
        return suggest_answer(question, job, self.profile).model_dump()

    def profile_view(self) -> dict:
        return self.profile.model_dump()

    def evaluate_job_contextual(
        self,
        job_id: str,
        *,
        twin_id: str,
        evaluated_at,
        selected_target_id: str | None = None,
    ) -> dict:
        """Contextual evaluation path used when a Career Intent exists.

        A contextual subsystem technical failure propagates rather than
        silently falling back to the legacy matching path.
        """
        job = next((j for j in self.jobs if j.id == job_id), None)
        if job is None:
            raise KeyError(job_id)

        if self.career_context_service is None:
            raise CareerTwinQueryNotConfigured(
                "contextual evaluation requested without a context service"
            )

        from onejob.career_context.matching_adapter import (
            build_evaluation_context,
            match_with_context,
        )
        from onejob.career_context.policy import evaluate_policy_gate

        outcome = self.career_context_service.resolve(
            twin_id=twin_id,
            job=job,
            evaluated_at=evaluated_at,
            selected_target_id=selected_target_id,
        )
        if getattr(outcome, "requires_user_selection", False):
            return {
                "id": job.id,
                "scope": "AMBIGUOUS",
                "requires_user_selection": True,
                "alternatives": outcome.alternatives,
            }

        view = self.career_context_service.materialize(outcome)
        gate = evaluate_policy_gate(view, job)
        context = build_evaluation_context(
            twin_projection=self.profile.model_dump(),
            view=view,
            assessments=[],
            policy_gate=gate,
        )
        result = match_with_context(job, self.profile, context)
        return {
            "id": job.id,
            "scope": view.scope.value,
            "resolved_view_id": view.resolved_view_id,
            "intent_version_id": view.intent_version_id,
            "target_version_id": view.target_version_id,
            "policy_gate": result.policy_gate.status.value,
            "decision": result.decision,
            "match_score": result.match_score,
            "strong_tradeoffs": result.strong_tradeoffs,
            "soft_signals": result.soft_signals,
        }

    def career_twin_view(self) -> dict:
        if self.career_twin_query is None:
            raise CareerTwinQueryNotConfigured(
                "Career Twin v2 query is not configured"
            )

        raw = self.career_twin_query.safe_view()

        safe_claim_fields = (
            "claim_id",
            "entity_id",
            "predicate",
            "approval_state",
            "lifecycle_state",
            "provenance_trust_tier",
            "claim_confidence",
        )

        claims = [
            {
                key: claim[key]
                for key in safe_claim_fields
                if key in claim
            }
            for claim in raw.get("claims", [])
        ]

        # Explicit top-level allowlist as another
        # privacy boundary. Unknown fields are dropped.
        return {
            "twin_id": raw.get("twin_id"),
            "projection_version": raw.get(
                "projection_version"
            ),
            "input_fingerprint": raw.get(
                "input_fingerprint"
            ),
            "entities": raw.get("entities", {}),
            "claims": claims,
        }

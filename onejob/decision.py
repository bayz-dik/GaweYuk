from pydantic import BaseModel, Field
from onejob.matching import MatchResult, PolicyResult
from onejob.trust import TrustResult

class DecisionResult(BaseModel):
    status: str
    reasons: list[str] = Field(default_factory=list)

def decide(match: MatchResult, trust: TrustResult, policy_result: PolicyResult) -> DecisionResult:
    if trust.hard_block or trust.score < 40:
        return DecisionResult(status='BLOCK', reasons=trust.risk_reasons or ['Trust below safety threshold'])
    if not policy_result.allowed:
        return DecisionResult(status='SKIP', reasons=policy_result.reasons)
    if trust.score >= 75 and match.score >= 80:
        return DecisionResult(status='APPLY', reasons=['High match and trust with no hard policy violation'])
    return DecisionResult(status='REVIEW', reasons=['Requires human review before application'])

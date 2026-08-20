from onejob.decision import decide
from onejob.matching import MatchResult, PolicyResult
from onejob.trust import TrustResult


def test_decision_apply_for_high_quality_job():
    result = decide(MatchResult(score=91, positive_evidence=[], negative_evidence=[]), TrustResult(score=92, positive_reasons=[], risk_reasons=[], hard_block=False), PolicyResult(allowed=True, reasons=[]))
    assert result.status == 'APPLY'


def test_decision_block_for_hard_trust_risk():
    result = decide(MatchResult(score=99, positive_evidence=[], negative_evidence=[]), TrustResult(score=20, positive_reasons=[], risk_reasons=['payment request'], hard_block=True), PolicyResult(allowed=True, reasons=[]))
    assert result.status == 'BLOCK'


def test_decision_skip_for_policy_violation():
    result = decide(MatchResult(score=99, positive_evidence=[], negative_evidence=[]), TrustResult(score=95, positive_reasons=[], risk_reasons=[], hard_block=False), PolicyResult(allowed=False, reasons=['salary']))
    assert result.status == 'SKIP'

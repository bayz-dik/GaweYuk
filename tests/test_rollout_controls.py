from onejob.trust_engine.models import TrustClassification
from onejob.trust_engine.rollout import (
    RolloutPhase,
    load_rollout_controls,
)


def test_default_rollout_is_shadow_and_fail_closed():
    controls = load_rollout_controls({})

    assert controls.phase is RolloutPhase.SHADOW
    assert not controls.critical_enforcement_enabled
    assert not controls.assisted_enforcement_enabled
    assert not controls.autopilot_enabled
    assert not controls.sensitive_document_automation
    assert not controls.payment_actions
    assert not controls.credential_actions


def test_invalid_rollout_phase_fails_closed_to_shadow():
    controls = load_rollout_controls(
        {"TRUST_ROLLOUT_PHASE": "definitely-not-valid"}
    )

    assert controls.phase is RolloutPhase.SHADOW
    assert not controls.critical_enforcement_enabled
    assert not controls.assisted_enforcement_enabled
    assert not controls.autopilot_enabled


def test_critical_phase_only_enables_l3_l4_enforcement():
    controls = load_rollout_controls(
        {"TRUST_ROLLOUT_PHASE": "CRITICAL"}
    )

    assert controls.critical_enforcement_enabled
    assert not controls.assisted_enforcement_enabled
    assert not controls.autopilot_enabled

    assert controls.enforces(
        TrustClassification.ABSOLUTE_BLOCK
    )
    assert controls.enforces(
        TrustClassification.AUTOMATION_BLOCKED
    )
    assert not controls.enforces(
        TrustClassification.REVIEW_REQUIRED
    )


def test_assisted_phase_enables_review_enforcement_but_not_autopilot():
    controls = load_rollout_controls(
        {
            "TRUST_ROLLOUT_PHASE": "ASSISTED",
            "AUTOPILOT_ENABLED": "true",
        }
    )

    assert controls.critical_enforcement_enabled
    assert controls.assisted_enforcement_enabled
    assert not controls.autopilot_enabled
    assert controls.enforces(
        TrustClassification.REVIEW_REQUIRED
    )


def test_autopilot_phase_still_requires_explicit_autopilot_switch():
    disabled = load_rollout_controls(
        {"TRUST_ROLLOUT_PHASE": "AUTOPILOT"}
    )
    enabled = load_rollout_controls(
        {
            "TRUST_ROLLOUT_PHASE": "AUTOPILOT",
            "AUTOPILOT_ENABLED": "true",
        }
    )

    assert not disabled.autopilot_enabled
    assert enabled.autopilot_enabled


def test_sensitive_document_automation_requires_phase_and_explicit_switch():
    shadow = load_rollout_controls(
        {
            "TRUST_ROLLOUT_PHASE": "SHADOW",
            "SENSITIVE_DOCUMENT_AUTOMATION": "true",
        }
    )
    assisted_off = load_rollout_controls(
        {"TRUST_ROLLOUT_PHASE": "ASSISTED"}
    )
    assisted_on = load_rollout_controls(
        {
            "TRUST_ROLLOUT_PHASE": "ASSISTED",
            "SENSITIVE_DOCUMENT_AUTOMATION": "true",
        }
    )

    assert not shadow.sensitive_document_automation
    assert not assisted_off.sensitive_document_automation
    assert assisted_on.sensitive_document_automation


def test_payment_and_credential_actions_are_permanently_false():
    controls = load_rollout_controls(
        {
            "TRUST_ROLLOUT_PHASE": "AUTOPILOT",
            "PAYMENT_ACTIONS": "true",
            "CREDENTIAL_ACTIONS": "true",
            "AUTOPILOT_ENABLED": "true",
        }
    )

    assert not controls.payment_actions
    assert not controls.credential_actions


def test_safety_switches_keep_permanent_kill_switches_off():
    controls = load_rollout_controls(
        {
            "TRUST_ROLLOUT_PHASE": "AUTOPILOT",
            "AUTOPILOT_ENABLED": "true",
            "SENSITIVE_DOCUMENT_AUTOMATION": "true",
            "PAYMENT_ACTIONS": "true",
            "CREDENTIAL_ACTIONS": "true",
        }
    )

    switches = controls.to_safety_switches()

    assert switches.autopilot_enabled
    assert switches.sensitive_document_automation
    assert not switches.payment_actions
    assert not switches.credential_actions


def test_boolean_parser_does_not_treat_arbitrary_text_as_true():
    controls = load_rollout_controls(
        {
            "TRUST_ROLLOUT_PHASE": "AUTOPILOT",
            "AUTOPILOT_ENABLED": "yes-please",
        }
    )

    assert not controls.autopilot_enabled

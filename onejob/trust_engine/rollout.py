from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from .authorization import SafetySwitches
from .models import TrustClassification


class RolloutPhase(StrEnum):
    SHADOW = "SHADOW"
    CRITICAL = "CRITICAL"
    ASSISTED = "ASSISTED"
    AUTOPILOT = "AUTOPILOT"


_TRUE_VALUES = frozenset({"1", "true", "on"})


def _env_true(
    env: Mapping[str, str],
    key: str,
) -> bool:
    return env.get(key, "").strip().lower() in _TRUE_VALUES


def _phase(
    env: Mapping[str, str],
) -> RolloutPhase:
    raw = env.get(
        "TRUST_ROLLOUT_PHASE",
        RolloutPhase.SHADOW.value,
    ).strip().upper()

    try:
        return RolloutPhase(raw)
    except ValueError:
        return RolloutPhase.SHADOW


@dataclass(frozen=True)
class RolloutControls:
    phase: RolloutPhase
    critical_enforcement_enabled: bool
    assisted_enforcement_enabled: bool
    autopilot_enabled: bool
    sensitive_document_automation: bool

    # Security invariants. These are intentionally not
    # configurable from environment variables.
    payment_actions: bool = False
    credential_actions: bool = False

    def enforces(
        self,
        classification: TrustClassification,
    ) -> bool:
        if self.phase is RolloutPhase.SHADOW:
            return False

        if classification in {
            TrustClassification.ABSOLUTE_BLOCK,
            TrustClassification.AUTOMATION_BLOCKED,
        }:
            return self.critical_enforcement_enabled

        if (
            classification
            is TrustClassification.REVIEW_REQUIRED
        ):
            return self.assisted_enforcement_enabled

        return (
            self.phase is RolloutPhase.AUTOPILOT
            and self.autopilot_enabled
        )

    def to_safety_switches(
        self,
    ) -> SafetySwitches:
        return SafetySwitches(
            autopilot_enabled=self.autopilot_enabled,
            sensitive_document_automation=(
                self.sensitive_document_automation
            ),
            payment_actions=False,
            credential_actions=False,
        )


def load_rollout_controls(
    env: Mapping[str, str],
) -> RolloutControls:
    phase = _phase(env)

    critical = phase in {
        RolloutPhase.CRITICAL,
        RolloutPhase.ASSISTED,
        RolloutPhase.AUTOPILOT,
    }

    assisted = phase in {
        RolloutPhase.ASSISTED,
        RolloutPhase.AUTOPILOT,
    }

    autopilot = (
        phase is RolloutPhase.AUTOPILOT
        and _env_true(env, "AUTOPILOT_ENABLED")
    )

    sensitive_documents = (
        phase in {
            RolloutPhase.ASSISTED,
            RolloutPhase.AUTOPILOT,
        }
        and _env_true(
            env,
            "SENSITIVE_DOCUMENT_AUTOMATION",
        )
    )

    return RolloutControls(
        phase=phase,
        critical_enforcement_enabled=critical,
        assisted_enforcement_enabled=assisted,
        autopilot_enabled=autopilot,
        sensitive_document_automation=(
            sensitive_documents
        ),
        payment_actions=False,
        credential_actions=False,
    )

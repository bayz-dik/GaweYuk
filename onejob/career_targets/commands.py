from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from onejob.career_intent.repositories import CareerIntentRepository
from onejob.career_targets.models import (
    OverrideOperation,
    SavedCareerTargetRecord,
    SavedCareerTargetVersionRecord,
    TargetIntentOverrideRecord,
    TargetLifecycle,
)
from onejob.career_targets.repositories import (
    SavedCareerTargetRepository,
    StaleTargetState,
)
from onejob.career_intent.models import IntentStrength
from onejob.career_twin.errors import AuthorizationDenied, CareerTwinError
from onejob.career_twin.events import CareerEvent
from onejob.career_twin.idempotency import (
    request_fingerprint,
    reserve_idempotency,
)
from onejob.career_twin.repositories import (
    CareerEventRepository,
    IdempotencyRepository,
)
from onejob.persistence.db import Database


class IdFactory(Protocol):
    def __call__(self, kind: str) -> str:
        ...


Actor = dict


class StaleTargetVersion(CareerTwinError):
    pass


class InvalidLifecycleTransition(CareerTwinError):
    pass


def _require_owner(actor: Actor, twin_id: str) -> None:
    if actor is None:
        raise AuthorizationDenied("missing actor context")
    if actor.get("twin_id") != twin_id:
        raise AuthorizationDenied("actor not authorized for twin")
    if not actor.get("is_owner"):
        raise AuthorizationDenied("actor is not the twin owner")
    if actor.get("actor_type", "USER") != "USER":
        raise AuthorizationDenied("only a user actor may manage targets")


@dataclass(frozen=True)
class NewTargetOverride:
    predicate: str
    operation: str
    value: Any | None = None
    strength: str | None = None
    overrides_statement_id: str | None = None
    explicit_exception_authority: str | None = None
    effective_from: datetime | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class CreateSavedCareerTargetCommand:
    actor_id: str
    twin_id: str
    idempotency_key: str
    display_name: str
    role_focus: list[str]
    domain_focus: list[str]
    explicit_keywords: list[str]
    scope_definition: dict[str, Any]
    overrides: list[NewTargetOverride]


@dataclass(frozen=True)
class ReviseSavedCareerTargetCommand:
    actor_id: str
    twin_id: str
    target_id: str
    idempotency_key: str
    expected_active_version_id: str | None
    display_name: str
    role_focus: list[str]
    domain_focus: list[str]
    explicit_keywords: list[str]
    scope_definition: dict[str, Any]
    overrides: list[NewTargetOverride]


@dataclass(frozen=True)
class SetTargetLifecycleCommand:
    actor_id: str
    twin_id: str
    target_id: str
    idempotency_key: str
    action: str  # PAUSE | RESUME | ARCHIVE


@dataclass(frozen=True)
class TargetResult:
    target_id: str
    target_version_id: str
    version_number: int
    replay: bool = False


@dataclass(frozen=True)
class LifecycleResult:
    target_id: str
    lifecycle: str
    replay: bool = False


_LIFECYCLE_TRANSITIONS = {
    "PAUSE": (TargetLifecycle.ACTIVE, TargetLifecycle.PAUSED),
    "RESUME": (TargetLifecycle.PAUSED, TargetLifecycle.ACTIVE),
    "ARCHIVE": (None, TargetLifecycle.ARCHIVED),
}


class TargetCommandService:
    def __init__(self, db: Database, *, id_factory: IdFactory):
        self.db = db
        self.id_factory = id_factory
        self.targets = SavedCareerTargetRepository()
        self.intents = CareerIntentRepository()
        self.events = CareerEventRepository()
        self.idempotency = IdempotencyRepository()

    def _append_event(self, conn, *, twin_id, event_type, subject_id, payload, now):
        self.events.append_with_outbox(
            conn,
            CareerEvent(
                event_id=self.id_factory("event"),
                twin_id=twin_id,
                event_type=event_type,
                subject_id=subject_id,
                occurred_at=now,
                payload=payload,
            ),
        )

    def _record_result(self, conn, key, reference):
        conn.execute(
            "UPDATE career_idempotency_keys SET result_reference = ? WHERE idempotency_key = ?",
            (reference, key),
        )

    def _build_overrides(
        self, target_version_id: str, overrides: list[NewTargetOverride]
    ) -> list[TargetIntentOverrideRecord]:
        result = []
        for o in overrides:
            result.append(
                TargetIntentOverrideRecord(
                    override_id=self.id_factory("override"),
                    target_version_id=target_version_id,
                    predicate=o.predicate,
                    operation=OverrideOperation(o.operation),
                    value=o.value,
                    strength=IntentStrength(o.strength) if o.strength else None,
                    effective_from=o.effective_from,
                    expires_at=o.expires_at,
                    overrides_statement_id=o.overrides_statement_id,
                    explicit_exception_authority=o.explicit_exception_authority,
                )
            )
        return result

    def create_target(
        self, command: CreateSavedCareerTargetCommand, *, actor: Actor, now: datetime
    ) -> TargetResult:
        _require_owner(actor, command.twin_id)

        fingerprint = request_fingerprint(
            {
                "kind": "create_target",
                "twin_id": command.twin_id,
                "display_name": command.display_name,
                "role_focus": sorted(command.role_focus),
                "domain_focus": sorted(command.domain_focus),
                "explicit_keywords": sorted(command.explicit_keywords),
                "scope_definition": command.scope_definition,
                "overrides": [o.__dict__ for o in command.overrides],
            }
        )

        with self.db.transaction() as conn:
            outcome = reserve_idempotency(
                conn,
                self.idempotency,
                idempotency_key=command.idempotency_key,
                fingerprint=fingerprint,
                now=now,
            )
            if outcome.replay:
                version = self.targets.get_version(conn, outcome.result_reference)
                return TargetResult(
                    target_id=version.target_id,
                    target_version_id=version.target_version_id,
                    version_number=version.version_number,
                    replay=True,
                )

            target_id = self.id_factory("target")
            target_version_id = self.id_factory("target_version")

            self.targets.create_target(
                conn,
                target=SavedCareerTargetRecord(
                    target_id=target_id,
                    twin_id=command.twin_id,
                    active_version_id=None,
                    lifecycle=TargetLifecycle.ACTIVE,
                    created_at=now,
                    created_by_actor_id=command.actor_id,
                ),
            )
            version = SavedCareerTargetVersionRecord(
                target_version_id=target_version_id,
                target_id=target_id,
                version_number=1,
                supersedes_version_id=None,
                display_name=command.display_name,
                role_focus=list(command.role_focus),
                domain_focus=list(command.domain_focus),
                explicit_keywords=list(command.explicit_keywords),
                scope_definition=dict(command.scope_definition),
                created_at=now,
                input_fingerprint=fingerprint,
            )
            overrides = self._build_overrides(target_version_id, command.overrides)
            self.targets.append_version(conn, version=version, overrides=overrides)
            self.targets.move_active_pointer(
                conn,
                target_id=target_id,
                expected_active_version_id=None,
                new_active_version_id=target_version_id,
            )
            self._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="SavedCareerTargetCreated",
                subject_id=target_id,
                payload={"target_id": target_id},
                now=now,
            )
            self._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="SavedCareerTargetVersionCreated",
                subject_id=target_version_id,
                payload={"target_id": target_id, "target_version_id": target_version_id},
                now=now,
            )
            self._record_result(conn, command.idempotency_key, target_version_id)

            return TargetResult(
                target_id=target_id,
                target_version_id=target_version_id,
                version_number=1,
            )

    def revise_target(
        self, command: ReviseSavedCareerTargetCommand, *, actor: Actor, now: datetime
    ) -> TargetResult:
        _require_owner(actor, command.twin_id)

        fingerprint = request_fingerprint(
            {
                "kind": "revise_target",
                "twin_id": command.twin_id,
                "target_id": command.target_id,
                "expected_active_version_id": command.expected_active_version_id,
                "display_name": command.display_name,
                "role_focus": sorted(command.role_focus),
                "domain_focus": sorted(command.domain_focus),
                "explicit_keywords": sorted(command.explicit_keywords),
                "scope_definition": command.scope_definition,
                "overrides": [o.__dict__ for o in command.overrides],
            }
        )

        with self.db.transaction() as conn:
            outcome = reserve_idempotency(
                conn,
                self.idempotency,
                idempotency_key=command.idempotency_key,
                fingerprint=fingerprint,
                now=now,
            )
            if outcome.replay:
                version = self.targets.get_version(conn, outcome.result_reference)
                return TargetResult(
                    target_id=version.target_id,
                    target_version_id=version.target_version_id,
                    version_number=version.version_number,
                    replay=True,
                )

            target = self.targets.get_owned(
                conn, target_id=command.target_id, twin_id=command.twin_id
            )
            if target is None:
                raise AuthorizationDenied("target not found or not owned")
            if target.active_version_id != command.expected_active_version_id:
                raise StaleTargetVersion(
                    "stale expected target version: "
                    f"expected={command.expected_active_version_id!r} "
                    f"actual={target.active_version_id!r}"
                )

            version_number = (
                self.targets.latest_version_number(conn, command.target_id) + 1
            )
            target_version_id = self.id_factory("target_version")
            version = SavedCareerTargetVersionRecord(
                target_version_id=target_version_id,
                target_id=command.target_id,
                version_number=version_number,
                supersedes_version_id=command.expected_active_version_id,
                display_name=command.display_name,
                role_focus=list(command.role_focus),
                domain_focus=list(command.domain_focus),
                explicit_keywords=list(command.explicit_keywords),
                scope_definition=dict(command.scope_definition),
                created_at=now,
                input_fingerprint=fingerprint,
            )
            overrides = self._build_overrides(target_version_id, command.overrides)
            self.targets.append_version(conn, version=version, overrides=overrides)
            self.targets.move_active_pointer(
                conn,
                target_id=command.target_id,
                expected_active_version_id=command.expected_active_version_id,
                new_active_version_id=target_version_id,
            )
            self._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="SavedCareerTargetVersionCreated",
                subject_id=target_version_id,
                payload={
                    "target_id": command.target_id,
                    "target_version_id": target_version_id,
                },
                now=now,
            )
            self._record_result(conn, command.idempotency_key, target_version_id)

            return TargetResult(
                target_id=command.target_id,
                target_version_id=target_version_id,
                version_number=version_number,
            )

    def set_lifecycle(
        self, command: SetTargetLifecycleCommand, *, actor: Actor, now: datetime
    ) -> LifecycleResult:
        _require_owner(actor, command.twin_id)

        if command.action not in _LIFECYCLE_TRANSITIONS:
            raise InvalidLifecycleTransition(command.action)

        fingerprint = request_fingerprint(
            {
                "kind": "set_target_lifecycle",
                "twin_id": command.twin_id,
                "target_id": command.target_id,
                "action": command.action,
            }
        )

        expected, new_state = _LIFECYCLE_TRANSITIONS[command.action]

        with self.db.transaction() as conn:
            outcome = reserve_idempotency(
                conn,
                self.idempotency,
                idempotency_key=command.idempotency_key,
                fingerprint=fingerprint,
                now=now,
            )
            if outcome.replay:
                return LifecycleResult(
                    target_id=command.target_id,
                    lifecycle=new_state.value,
                    replay=True,
                )

            target = self.targets.get_owned(
                conn, target_id=command.target_id, twin_id=command.twin_id
            )
            if target is None:
                raise AuthorizationDenied("target not found or not owned")

            # Archive is terminal: cannot resume/pause an archived target.
            if target.lifecycle is TargetLifecycle.ARCHIVED:
                raise InvalidLifecycleTransition(
                    "archived target is terminal"
                )

            if expected is None:
                # ARCHIVE allowed from ACTIVE or PAUSED.
                try:
                    self.targets.set_lifecycle(
                        conn,
                        target_id=command.target_id,
                        expected_lifecycle=target.lifecycle,
                        new_lifecycle=new_state,
                    )
                except StaleTargetState as exc:
                    raise InvalidLifecycleTransition(str(exc)) from exc
            else:
                try:
                    self.targets.set_lifecycle(
                        conn,
                        target_id=command.target_id,
                        expected_lifecycle=expected,
                        new_lifecycle=new_state,
                    )
                except StaleTargetState as exc:
                    raise InvalidLifecycleTransition(str(exc)) from exc

            self._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="SavedCareerTargetLifecycleChanged",
                subject_id=command.target_id,
                payload={"target_id": command.target_id, "lifecycle": new_state.value},
                now=now,
            )
            self._record_result(conn, command.idempotency_key, command.target_id)

            return LifecycleResult(
                target_id=command.target_id, lifecycle=new_state.value
            )

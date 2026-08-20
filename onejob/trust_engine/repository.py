from __future__ import annotations

from datetime import datetime
import json
import sqlite3

from .models import (
    ConsentGrant,
    DetectionMethod,
    DimensionScore,
    DimensionState,
    GateHit,
    RecruitmentStage,
    SignalLevel,
    SignalStatus,
    TrustClassification,
    TrustDecision,
    TrustDimension,
    TrustSignal,
)


TRUST_SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_signals (
    signal_id TEXT PRIMARY KEY,
    canonical_job_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    level TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    detection_method TEXT NOT NULL,
    context_stage TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    resolved_at TEXT,
    resolution_reason TEXT,
    FOREIGN KEY(canonical_job_id)
        REFERENCES canonical_jobs(canonical_job_id)
);

CREATE TABLE IF NOT EXISTS trust_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    canonical_job_id TEXT NOT NULL,
    recruitment_stage TEXT NOT NULL,
    overall_score REAL NOT NULL,
    trust_confidence REAL NOT NULL,
    classification TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    valid_until TEXT,
    input_fingerprint TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    active_signal_ids_json TEXT NOT NULL,
    unknown_dimensions_json TEXT NOT NULL,
    not_applicable_dimensions_json TEXT NOT NULL,
    allowed_actions_json TEXT NOT NULL,
    blocked_actions_json TEXT NOT NULL,
    override_policy TEXT NOT NULL,
    primary_reason_codes_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    UNIQUE(
        canonical_job_id,
        input_fingerprint,
        policy_version
    ),
    FOREIGN KEY(canonical_job_id)
        REFERENCES canonical_jobs(canonical_job_id)
);

CREATE TABLE IF NOT EXISTS trust_dimension_scores (
    evaluation_id TEXT NOT NULL,
    dimension_name TEXT NOT NULL,
    state TEXT NOT NULL,
    score REAL,
    confidence REAL,
    reason_codes_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    PRIMARY KEY(evaluation_id, dimension_name),
    FOREIGN KEY(evaluation_id)
        REFERENCES trust_evaluations(evaluation_id)
);

CREATE TABLE IF NOT EXISTS trust_gate_hits (
    evaluation_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    gate_code TEXT NOT NULL,
    level TEXT NOT NULL,
    effect TEXT NOT NULL,
    override_policy TEXT NOT NULL,
    PRIMARY KEY(evaluation_id, signal_id, gate_code),
    FOREIGN KEY(evaluation_id)
        REFERENCES trust_evaluations(evaluation_id),
    FOREIGN KEY(signal_id)
        REFERENCES trust_signals(signal_id)
);

CREATE TABLE IF NOT EXISTS trust_evaluation_attempts (
    attempt_id TEXT PRIMARY KEY,
    canonical_job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    error_code TEXT,
    input_fingerprint TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trust_consents (
    consent_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    canonical_job_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    recruitment_stage TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY(canonical_job_id)
        REFERENCES canonical_jobs(canonical_job_id)
);

CREATE TABLE IF NOT EXISTS trust_action_events (
    action_event_id TEXT PRIMARY KEY,
    canonical_job_id TEXT NOT NULL,
    evaluation_id TEXT,
    action_type TEXT NOT NULL,
    requested_mode TEXT NOT NULL,
    result TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    consent_id TEXT,
    override_id TEXT,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY(canonical_job_id)
        REFERENCES canonical_jobs(canonical_job_id),
    FOREIGN KEY(evaluation_id)
        REFERENCES trust_evaluations(evaluation_id)
);

CREATE TABLE IF NOT EXISTS trust_entity_links (
    link_id TEXT PRIMARY KEY,
    from_entity_type TEXT NOT NULL,
    from_entity_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    to_entity_type TEXT NOT NULL,
    to_entity_id TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    status TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trust_signals_job_status_level
ON trust_signals(
    canonical_job_id,
    status,
    level
);

CREATE INDEX IF NOT EXISTS idx_trust_evaluations_job_time
ON trust_evaluations(
    canonical_job_id,
    evaluated_at
);

CREATE INDEX IF NOT EXISTS idx_trust_action_events_job_time
ON trust_action_events(
    canonical_job_id,
    occurred_at
);

CREATE INDEX IF NOT EXISTS idx_trust_consents_job_scope_expiry
ON trust_consents(
    canonical_job_id,
    scope,
    expires_at
);
"""


def _json(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


def _loads(value: str):
    return json.loads(value)


class TrustRepository:
    def ensure_schema(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        conn.executescript(TRUST_SCHEMA)

    def upsert_signal(
        self,
        conn: sqlite3.Connection,
        signal: TrustSignal,
    ) -> TrustSignal:
        existing = conn.execute(
            """
            SELECT first_seen_at
            FROM trust_signals
            WHERE signal_id = ?
            """,
            (signal.signal_id,),
        ).fetchone()

        first_seen = (
            existing["first_seen_at"]
            if existing is not None
            else signal.first_seen_at.isoformat()
        )

        conn.execute(
            """
            INSERT INTO trust_signals (
                signal_id,
                canonical_job_id,
                signal_type,
                level,
                status,
                confidence,
                detection_method,
                context_stage,
                evidence_refs_json,
                extractor_version,
                fingerprint,
                first_seen_at,
                last_seen_at,
                resolved_at,
                resolution_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(signal_id) DO UPDATE SET
                signal_type = excluded.signal_type,
                level = excluded.level,
                status = excluded.status,
                confidence = excluded.confidence,
                detection_method = excluded.detection_method,
                context_stage = excluded.context_stage,
                evidence_refs_json = excluded.evidence_refs_json,
                extractor_version = excluded.extractor_version,
                fingerprint = excluded.fingerprint,
                last_seen_at = excluded.last_seen_at,
                resolved_at = excluded.resolved_at,
                resolution_reason = excluded.resolution_reason
            """,
            (
                signal.signal_id,
                signal.canonical_job_id,
                signal.signal_type,
                signal.level.value,
                signal.status.value,
                signal.confidence,
                signal.detection_method.value,
                signal.context_stage.value,
                _json(signal.evidence_refs),
                signal.extractor_version,
                signal.fingerprint,
                first_seen,
                signal.last_seen_at.isoformat(),
                (
                    signal.resolved_at.isoformat()
                    if signal.resolved_at
                    else None
                ),
                signal.resolution_reason,
            ),
        )

        row = conn.execute(
            """
            SELECT *
            FROM trust_signals
            WHERE signal_id = ?
            """,
            (signal.signal_id,),
        ).fetchone()

        return self._signal_from_row(row)

    def resolve_signal(
        self,
        conn: sqlite3.Connection,
        signal_id: str,
        *,
        resolved_at: datetime,
        reason: str,
    ) -> None:
        cursor = conn.execute(
            """
            UPDATE trust_signals
            SET
                status = ?,
                resolved_at = ?,
                resolution_reason = ?
            WHERE signal_id = ?
            """,
            (
                SignalStatus.RESOLVED.value,
                resolved_at.isoformat(),
                reason,
                signal_id,
            ),
        )

        if cursor.rowcount != 1:
            raise KeyError(signal_id)

    def append_evaluation(
        self,
        conn: sqlite3.Connection,
        decision: TrustDecision,
    ) -> None:
        conn.execute(
            """
            INSERT INTO trust_evaluations (
                evaluation_id,
                canonical_job_id,
                recruitment_stage,
                overall_score,
                trust_confidence,
                classification,
                evaluated_at,
                valid_until,
                input_fingerprint,
                policy_version,
                active_signal_ids_json,
                unknown_dimensions_json,
                not_applicable_dimensions_json,
                allowed_actions_json,
                blocked_actions_json,
                override_policy,
                primary_reason_codes_json,
                evidence_refs_json
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                decision.evaluation_id,
                decision.canonical_job_id,
                decision.recruitment_stage.value,
                decision.overall_score,
                decision.confidence,
                decision.classification.value,
                decision.evaluated_at.isoformat(),
                (
                    decision.valid_until.isoformat()
                    if decision.valid_until
                    else None
                ),
                decision.input_fingerprint,
                decision.policy_version,
                _json(decision.risk_signal_ids),
                _json(
                    tuple(
                        item.value
                        for item in decision.unknown_dimensions
                    )
                ),
                _json(
                    tuple(
                        item.value
                        for item
                        in decision.not_applicable_dimensions
                    )
                ),
                _json(decision.allowed_actions),
                _json(decision.blocked_actions),
                decision.override_policy,
                _json(decision.primary_reasons),
                _json(decision.evidence_refs),
            ),
        )

        for dimension, score in decision.dimensions.items():
            conn.execute(
                """
                INSERT INTO trust_dimension_scores (
                    evaluation_id,
                    dimension_name,
                    state,
                    score,
                    confidence,
                    reason_codes_json,
                    evidence_refs_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.evaluation_id,
                    dimension.value,
                    score.state.value,
                    score.score,
                    score.confidence,
                    _json(score.reason_codes),
                    _json(score.evidence_refs),
                ),
            )

        for gate in decision.hard_gates:
            conn.execute(
                """
                INSERT INTO trust_gate_hits (
                    evaluation_id,
                    signal_id,
                    gate_code,
                    level,
                    effect,
                    override_policy
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.evaluation_id,
                    gate.signal_id,
                    gate.gate_code,
                    gate.level.value,
                    gate.effect.value,
                    gate.override_policy,
                ),
            )

    def latest_evaluation(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
    ) -> TrustDecision | None:
        row = conn.execute(
            """
            SELECT *
            FROM trust_evaluations
            WHERE canonical_job_id = ?
            ORDER BY evaluated_at DESC, rowid DESC
            LIMIT 1
            """,
            (canonical_job_id,),
        ).fetchone()

        if row is None:
            return None

        dimension_rows = conn.execute(
            """
            SELECT *
            FROM trust_dimension_scores
            WHERE evaluation_id = ?
            """,
            (row["evaluation_id"],),
        ).fetchall()

        gate_rows = conn.execute(
            """
            SELECT *
            FROM trust_gate_hits
            WHERE evaluation_id = ?
            """,
            (row["evaluation_id"],),
        ).fetchall()

        dimensions = {}
        for item in dimension_rows:
            dimension = TrustDimension(
                item["dimension_name"]
            )
            dimensions[dimension] = DimensionScore(
                dimension=dimension,
                state=DimensionState(item["state"]),
                score=item["score"],
                confidence=item["confidence"],
                reason_codes=tuple(
                    _loads(item["reason_codes_json"])
                ),
                evidence_refs=tuple(
                    _loads(item["evidence_refs_json"])
                ),
            )

        gates = tuple(
            GateHit(
                signal_id=item["signal_id"],
                gate_code=item["gate_code"],
                level=SignalLevel(item["level"]),
                effect=TrustClassification(
                    item["effect"]
                ),
                override_policy=item["override_policy"],
            )
            for item in gate_rows
        )

        return TrustDecision(
            evaluation_id=row["evaluation_id"],
            canonical_job_id=row["canonical_job_id"],
            recruitment_stage=RecruitmentStage(
                row["recruitment_stage"]
            ),
            overall_score=row["overall_score"],
            confidence=row["trust_confidence"],
            dimensions=dimensions,
            classification=TrustClassification(
                row["classification"]
            ),
            hard_gates=gates,
            risk_signal_ids=tuple(
                _loads(row["active_signal_ids_json"])
            ),
            unknown_dimensions=tuple(
                TrustDimension(value)
                for value in _loads(
                    row["unknown_dimensions_json"]
                )
            ),
            not_applicable_dimensions=tuple(
                TrustDimension(value)
                for value in _loads(
                    row[
                        "not_applicable_dimensions_json"
                    ]
                )
            ),
            allowed_actions=tuple(
                _loads(row["allowed_actions_json"])
            ),
            blocked_actions=tuple(
                _loads(row["blocked_actions_json"])
            ),
            override_policy=row["override_policy"],
            primary_reasons=tuple(
                _loads(row["primary_reason_codes_json"])
            ),
            evidence_refs=tuple(
                _loads(row["evidence_refs_json"])
            ),
            evaluated_at=datetime.fromisoformat(
                row["evaluated_at"]
            ),
            valid_until=(
                datetime.fromisoformat(row["valid_until"])
                if row["valid_until"]
                else None
            ),
            input_fingerprint=row["input_fingerprint"],
            policy_version=row["policy_version"],
        )

    def grant_consent(
        self,
        conn: sqlite3.Connection,
        consent: ConsentGrant,
    ) -> None:
        conn.execute(
            """
            INSERT INTO trust_consents (
                consent_id,
                user_id,
                canonical_job_id,
                company_id,
                scope,
                recruitment_stage,
                issued_at,
                expires_at,
                revoked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                consent.consent_id,
                consent.user_id,
                consent.canonical_job_id,
                consent.company_id,
                consent.scope,
                consent.recruitment_stage.value,
                consent.issued_at.isoformat(),
                consent.expires_at.isoformat(),
                (
                    consent.revoked_at.isoformat()
                    if consent.revoked_at
                    else None
                ),
            ),
        )

    def get_valid_consent(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str,
        canonical_job_id: str,
        scope: str,
        now: datetime,
    ) -> ConsentGrant | None:
        row = conn.execute(
            """
            SELECT *
            FROM trust_consents
            WHERE
                user_id = ?
                AND canonical_job_id = ?
                AND scope = ?
                AND revoked_at IS NULL
                AND issued_at <= ?
                AND expires_at > ?
            ORDER BY issued_at DESC
            LIMIT 1
            """,
            (
                user_id,
                canonical_job_id,
                scope,
                now.isoformat(),
                now.isoformat(),
            ),
        ).fetchone()

        if row is None:
            return None

        return ConsentGrant(
            consent_id=row["consent_id"],
            user_id=row["user_id"],
            canonical_job_id=row["canonical_job_id"],
            company_id=row["company_id"],
            scope=row["scope"],
            recruitment_stage=RecruitmentStage(
                row["recruitment_stage"]
            ),
            issued_at=datetime.fromisoformat(
                row["issued_at"]
            ),
            expires_at=datetime.fromisoformat(
                row["expires_at"]
            ),
            revoked_at=(
                datetime.fromisoformat(row["revoked_at"])
                if row["revoked_at"]
                else None
            ),
        )

    def append_action_event(
        self,
        conn: sqlite3.Connection,
        *,
        action_event_id: str,
        canonical_job_id: str,
        evaluation_id: str | None,
        action_type: str,
        requested_mode: str,
        result: str,
        reason_codes: tuple[str, ...],
        consent_id: str | None,
        override_id: str | None,
        occurred_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO trust_action_events (
                action_event_id,
                canonical_job_id,
                evaluation_id,
                action_type,
                requested_mode,
                result,
                reason_codes_json,
                consent_id,
                override_id,
                occurred_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_event_id,
                canonical_job_id,
                evaluation_id,
                action_type,
                requested_mode,
                result,
                _json(reason_codes),
                consent_id,
                override_id,
                occurred_at.isoformat(),
            ),
        )

    def _signal_from_row(
        self,
        row: sqlite3.Row,
    ) -> TrustSignal:
        return TrustSignal(
            signal_id=row["signal_id"],
            canonical_job_id=row["canonical_job_id"],
            signal_type=row["signal_type"],
            level=SignalLevel(row["level"]),
            status=SignalStatus(row["status"]),
            confidence=row["confidence"],
            detection_method=DetectionMethod(
                row["detection_method"]
            ),
            context_stage=RecruitmentStage(
                row["context_stage"]
            ),
            evidence_refs=tuple(
                _loads(row["evidence_refs_json"])
            ),
            extractor_version=row["extractor_version"],
            fingerprint=row["fingerprint"],
            first_seen_at=datetime.fromisoformat(
                row["first_seen_at"]
            ),
            last_seen_at=datetime.fromisoformat(
                row["last_seen_at"]
            ),
            resolved_at=(
                datetime.fromisoformat(row["resolved_at"])
                if row["resolved_at"]
                else None
            ),
            resolution_reason=row["resolution_reason"],
        )


def _trust_repo_list_active_signals(
    self,
    conn,
    canonical_job_id: str,
):
    rows = conn.execute(
        """
        SELECT *
        FROM trust_signals
        WHERE
            canonical_job_id = ?
            AND status = ?
        ORDER BY signal_id
        """,
        (
            canonical_job_id,
            SignalStatus.ACTIVE.value,
        ),
    ).fetchall()

    return tuple(
        self._signal_from_row(row)
        for row in rows
    )


def _trust_repo_record_attempt(
    self,
    conn,
    *,
    attempt_id: str,
    canonical_job_id: str,
    status: str,
    error_code: str | None,
    input_fingerprint: str | None,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO trust_evaluation_attempts (
            attempt_id,
            canonical_job_id,
            status,
            error_code,
            input_fingerprint,
            started_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attempt_id,
            canonical_job_id,
            status,
            error_code,
            input_fingerprint,
            started_at.isoformat(),
            finished_at.isoformat(),
        ),
    )


TrustRepository.list_active_signals = (
    _trust_repo_list_active_signals
)

TrustRepository.record_attempt = (
    _trust_repo_record_attempt
)

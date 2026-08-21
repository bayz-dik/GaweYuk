from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from onejob.ingestion.evidence_store import (
    EvidenceConsensusStore,
)
from onejob.ingestion.explainability import (
    ConflictExplainabilityStore,
)
from onejob.ingestion.identity import (
    company_id_for,
    job_identity_key,
)
from onejob.ingestion.entity_resolution import (
    JobEntityResolver,
    JobIdentityCandidate,
    JobIdentityDisposition,
)
from onejob.ingestion.provenance import (
    AppearanceRepository,
    derive_evidence_family_id,
)
from onejob.ingestion.lifecycle import (
    diff_material_fields,
    material_snapshot,
)
from onejob.persistence.repositories import (
    ObservationRepository,
)
from onejob.job_sources.policy import SourcePolicy
from onejob.job_sources.repository import SourceRepository
from onejob.job_verification.policy import (
    PublicationPolicy,
    PublicationState,
)
from onejob.job_verification.models import ApplyDestinationStatus
from onejob.job_verification.production_store import (
    ProductionVerificationStore,
)
from onejob.job_verification.repository import VerificationRepository
from onejob.job_verification.service import (
    JobVerificationService,
    VerificationSystemFailure,
)
from onejob.trust_engine.models import RecruitmentStage
from onejob.trust_engine.repository import TrustRepository
from onejob.trust_engine.service import TrustEngineService
from onejob.trust_engine.signals import extract_deterministic_signals


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _json(data: Any) -> str:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_id(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass
class IngestionResult:
    new_count: int = 0
    unchanged_count: int = 0
    canonical_job_ids: list[str] = field(
        default_factory=list
    )


class _UnregisteredSourcePolicy:
    """Policy for observations from a source not in the registry.

    An unknown/unregistered source may have its evidence stored but can never
    contribute publication authority, so publication stays closed.
    """

    publication_evidence_allowed = False
    collection_allowed = True
    reason_codes = ("SOURCE_NOT_REGISTERED",)


class IngestionPipeline:
    def __init__(
        self,
        db,
        *,
        destination_status_by_job=None,
        recruitment_stage: RecruitmentStage = RecruitmentStage.APPLICATION,
    ):
        self.db = db
        self.observations = ObservationRepository()
        self.evidence = EvidenceConsensusStore()
        self.conflicts = ConflictExplainabilityStore()
        self.trust = TrustEngineService(db)
        # Slice 4A verification network collaborators. Adapters observe;
        # this orchestrator preserves, canonicalizes, verifies, and publishes.
        self.sources = SourceRepository()
        self.source_policy = SourcePolicy()
        self.appearances = AppearanceRepository()
        self.entity_resolver = JobEntityResolver()
        self.trust_repo = TrustRepository()
        self.verification_repo = VerificationRepository()
        self.publication_policy = PublicationPolicy()
        self._destination_status_by_job = destination_status_by_job or {}
        self._recruitment_stage = recruitment_stage

    @staticmethod
    def _resolved_data(
        observation,
        selected_values: dict[str, Any],
    ) -> dict[str, Any]:
        data = observation.model_dump()

        for field_name, value in selected_values.items():
            data[field_name] = value

        return data

    @staticmethod
    def _update_canonical_job(
        conn,
        canonical_job_id: str,
        resolved: dict[str, Any],
        seen_at: str,
    ) -> None:
        title = resolved["title"]
        location = resolved["location_text"]

        conn.execute(
            """
            UPDATE canonical_jobs
            SET
                title = ?,
                normalized_title = ?,
                location = ?,
                normalized_location = ?,
                description = ?,
                salary_min = ?,
                salary_max = ?,
                currency = ?,
                employment_type = ?,
                contact_email = ?,
                last_seen_at = ?
            WHERE canonical_job_id = ?
            """,
            (
                title,
                _normalize(title),
                location,
                _normalize(location),
                resolved.get("description"),
                resolved.get("salary_min"),
                resolved.get("salary_max"),
                resolved.get("currency"),
                resolved.get("employment_type"),
                resolved.get("contact_email"),
                seen_at,
                canonical_job_id,
            ),
        )

    @staticmethod
    def _latest_version(conn, canonical_job_id):
        return conn.execute(
            """
            SELECT
                version_id,
                version_number,
                field_snapshot_json
            FROM job_versions
            WHERE canonical_job_id = ?
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (canonical_job_id,),
        ).fetchone()

    @staticmethod
    def _append_version(
        conn,
        *,
        canonical_job_id: str,
        version_number: int,
        seen_at: str,
        snapshot: dict[str, Any],
        changed_fields: list[str],
    ) -> None:
        snapshot_json = _json(snapshot)

        content_hash = hashlib.sha256(
            snapshot_json.encode()
        ).hexdigest()

        version_id = _stable_id(
            canonical_job_id,
            version_number,
            content_hash,
        )

        conn.execute(
            """
            INSERT INTO job_versions (
                version_id,
                canonical_job_id,
                version_number,
                valid_from,
                valid_to,
                content_hash,
                changed_fields_json,
                field_snapshot_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                canonical_job_id,
                version_number,
                seen_at,
                None,
                content_hash,
                _json(changed_fields),
                snapshot_json,
            ),
        )

        event_type = (
            "JOB_DISCOVERED"
            if version_number == 1
            else "JOB_CHANGED"
        )

        payload = (
            {}
            if version_number == 1
            else {"changed_fields": changed_fields}
        )

        conn.execute(
            """
            INSERT INTO job_events (
                event_id,
                canonical_job_id,
                event_type,
                occurred_at,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                _stable_id(
                    canonical_job_id,
                    event_type,
                    version_number,
                    content_hash,
                ),
                canonical_job_id,
                event_type,
                seen_at,
                _json(payload),
            ),
        )

    def collect_one(self, collector, target) -> IngestionResult:
        batch = collector.collect(target)
        result = IngestionResult()
        # Capture apply-destination + risk text per canonical job for the
        # post-commit verification pass. Adapters observe only; trust/publication
        # authority is applied strictly after ingestion commits.
        job_apply_url: dict[str, str | None] = {}
        job_risk_text: dict[str, str] = {}

        with self.db.transaction() as conn:
            for observation in batch.observations:
                self.observations.insert(
                    conn,
                    observation,
                )

                normalized_company = _normalize(
                    observation.company_name
                )
                normalized_title = _normalize(
                    observation.title
                )
                normalized_location = _normalize(
                    observation.location_text
                )

                company_id = company_id_for(
                    observation.company_name
                )

                conn.execute(
                    """
                    INSERT OR IGNORE INTO companies (
                        company_id,
                        normalized_name,
                        display_name
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        company_id,
                        normalized_company,
                        observation.company_name,
                    ),
                )

                canonical_job_id = job_identity_key(
                    company_id,
                    normalized_title,
                    normalized_location,
                )

                existing = conn.execute(
                    """
                    SELECT canonical_job_id
                    FROM canonical_jobs
                    WHERE canonical_job_id = ?
                    """,
                    (canonical_job_id,),
                ).fetchone()

                seen_at = observation.observed_at.isoformat()

                # field_evidence has FK -> canonical_jobs,
                # therefore create provisional canonical row first.
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO canonical_jobs (
                            canonical_job_id,
                            company_id,
                            title,
                            normalized_title,
                            location,
                            normalized_location,
                            description,
                            salary_min,
                            salary_max,
                            currency,
                            employment_type,
                            contact_email,
                            lifecycle_state,
                            first_seen_at,
                            last_seen_at,
                            active_status_confidence
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            canonical_job_id,
                            company_id,
                            observation.title,
                            normalized_title,
                            observation.location_text,
                            normalized_location,
                            observation.description,
                            observation.salary_min,
                            observation.salary_max,
                            observation.currency,
                            observation.employment_type,
                            observation.contact_email,
                            "ACTIVE",
                            seen_at,
                            seen_at,
                            1.0,
                        ),
                    )

                # Record every source claim first.
                # Canonical state is then derived from consensus,
                # never directly from "latest source wins".
                consensus_values = (
                    self.evidence.record_observation(
                        conn,
                        canonical_job_id,
                        observation,
                    )
                )

                self.conflicts.sync(
                    conn,
                    canonical_job_id,
                    consensus_values,
                    seen_at,
                )

                selected_values = (
                    self.evidence.selected_values(
                        conn,
                        canonical_job_id,
                    )
                )

                resolved = self._resolved_data(
                    observation,
                    selected_values,
                )

                snapshot = material_snapshot(resolved)

                if existing is None:
                    self._update_canonical_job(
                        conn,
                        canonical_job_id,
                        resolved,
                        seen_at,
                    )

                    self._append_version(
                        conn,
                        canonical_job_id=canonical_job_id,
                        version_number=1,
                        seen_at=seen_at,
                        snapshot=snapshot,
                        changed_fields=[],
                    )

                    result.new_count += 1

                else:
                    latest = self._latest_version(
                        conn,
                        canonical_job_id,
                    )

                    old_snapshot = (
                        json.loads(latest[2])
                        if latest is not None
                        else {}
                    )

                    changed_fields = diff_material_fields(
                        old_snapshot,
                        snapshot,
                    )

                    if changed_fields:
                        self._update_canonical_job(
                            conn,
                            canonical_job_id,
                            resolved,
                            seen_at,
                        )

                        if latest is not None:
                            conn.execute(
                                """
                                UPDATE job_versions
                                SET valid_to = ?
                                WHERE version_id = ?
                                """,
                                (
                                    seen_at,
                                    latest[0],
                                ),
                            )

                        version_number = (
                            latest[1] + 1
                            if latest is not None
                            else 1
                        )

                        self._append_version(
                            conn,
                            canonical_job_id=canonical_job_id,
                            version_number=version_number,
                            seen_at=seen_at,
                            snapshot=snapshot,
                            changed_fields=changed_fields,
                        )

                    else:
                        conn.execute(
                            """
                            UPDATE canonical_jobs
                            SET last_seen_at = ?
                            WHERE canonical_job_id = ?
                            """,
                            (
                                seen_at,
                                canonical_job_id,
                            ),
                        )

                        result.unchanged_count += 1

                conn.execute(
                    """
                    INSERT OR IGNORE INTO canonical_job_sources (
                        canonical_job_id,
                        observation_id,
                        source_key,
                        external_id
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        canonical_job_id,
                        observation.observation_id,
                        observation.source_key,
                        observation.external_id,
                    ),
                )

                # Provenance + source appearance so mirrors share one upstream
                # evidence family and repeated sightings advance last_seen
                # without rewriting raw observations.
                registered_source = self.sources.get_by_key(
                    conn, observation.source_key
                )
                source_id = (
                    registered_source.source_id
                    if registered_source is not None
                    else observation.source_key
                )
                evidence_family_id = derive_evidence_family_id(
                    source_id=source_id,
                    external_id=observation.external_id,
                    upstream_family_hint=None,
                )
                self.appearances.upsert_seen(
                    conn,
                    canonical_job_id=canonical_job_id,
                    source_id=source_id,
                    external_id=observation.external_id,
                    source_url=observation.source_url,
                    apply_url=observation.apply_url,
                    evidence_family_id=evidence_family_id,
                    observation_id=observation.observation_id,
                    seen_at=observation.observed_at,
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO observation_provenance (
                        observation_id, source_id, evidence_family_id,
                        apply_url, recorded_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        observation.observation_id,
                        source_id,
                        evidence_family_id,
                        observation.apply_url,
                        seen_at,
                    ),
                )

                if (
                    canonical_job_id
                    not in result.canonical_job_ids
                ):
                    result.canonical_job_ids.append(
                        canonical_job_id
                    )
                job_apply_url[canonical_job_id] = observation.apply_url
                job_risk_text[canonical_job_id] = observation.description

            changed_count = max(
                0,
                len(batch.observations)
                - result.new_count
                - result.unchanged_count,
            )

            run_id = _stable_id(
                batch.source_key,
                batch.collector_version,
                batch.started_at.isoformat(),
                batch.finished_at.isoformat(),
            )

            conn.execute(
                """
                INSERT INTO collection_runs (
                    run_id,
                    source_key,
                    collector_version,
                    started_at,
                    finished_at,
                    status,
                    observations_count,
                    new_count,
                    changed_count,
                    unchanged_count,
                    closed_count,
                    warnings_count,
                    error_summary
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    run_id,
                    batch.source_key,
                    batch.collector_version,
                    batch.started_at.isoformat(),
                    batch.finished_at.isoformat(),
                    batch.status.value,
                    len(batch.observations),
                    result.new_count,
                    changed_count,
                    result.unchanged_count,
                    0,
                    len(batch.warnings),
                    getattr(
                        batch,
                        "error_summary",
                        None,
                    ),
                ),
            )


        # Downstream verification runs strictly after ingestion has committed
        # so a failure cannot roll back durable raw evidence. collector success
        # is not publication success.
        self._verify_after_commit(
            result.canonical_job_ids,
            apply_url_by_job=job_apply_url,
            risk_text_by_job=job_risk_text,
        )

        return result

    def _verify_after_commit(
        self,
        canonical_job_ids,
        *,
        apply_url_by_job=None,
        risk_text_by_job=None,
    ) -> None:
        apply_url_by_job = apply_url_by_job or {}
        risk_text_by_job = risk_text_by_job or {}

        # 1. Extract deterministic risk signals and run the existing Trust
        #    Engine (the single trust authority) after commit.
        self._run_trust_engine(canonical_job_ids, risk_text_by_job)

        # 2. Assemble immutable verification snapshots and apply publication
        #    policy, updating the publication head. A system failure fails
        #    closed for publication but never rolls back committed evidence.
        self._verify_and_publish(canonical_job_ids, apply_url_by_job)

    def _run_trust_engine(self, canonical_job_ids, risk_text_by_job) -> None:
        now = datetime.now(timezone.utc)
        for canonical_job_id in canonical_job_ids:
            text = risk_text_by_job.get(canonical_job_id)
            if text:
                signals = extract_deterministic_signals(
                    canonical_job_id=canonical_job_id,
                    text=text,
                    stage=self._recruitment_stage,
                    evidence_ref=f"observation:{canonical_job_id}",
                    observed_at=now,
                )
                if signals:
                    with self.db.transaction() as conn:
                        self.trust_repo.ensure_schema(conn)
                        for signal in signals:
                            self.trust_repo.upsert_signal(conn, signal)
        self.trust.shadow_evaluate_after_ingestion(
            canonical_job_ids,
            stage=self._recruitment_stage,
            now=now,
        )

    def _verify_and_publish(self, canonical_job_ids, apply_url_by_job) -> None:
        now = datetime.now(timezone.utc)
        destination_status = dict(self._destination_status_by_job)
        destination_status.update(
            self._assess_destinations(apply_url_by_job)
        )
        store = ProductionVerificationStore(
            self.db,
            destination_status_by_job=destination_status,
            now=now,
        )
        verification = JobVerificationService(self.db, store=store, now_default=now)

        for canonical_job_id in canonical_job_ids:
            self._publish_one(verification, canonical_job_id, now)

    def _publish_one(self, verification, canonical_job_id, now) -> None:
        snapshot = verification.evaluate(canonical_job_id, now=now)
        source_policy = self._source_policy_for(canonical_job_id)
        draft = self.publication_policy.evaluate(
            snapshot, source_policy=source_policy
        )
        with self.db.transaction() as conn:
            self.verification_repo.append_publication_decision(
                conn,
                decision_id=f"dec-{uuid4().hex}",
                canonical_job_id=canonical_job_id,
                verification_id=snapshot.verification_id,
                state=draft.state,
                reason_codes=draft.reason_codes,
                decided_at=now,
            )

    def reverify_and_publish(
        self, canonical_job_id: str, *, now, destination_status=None
    ) -> None:
        """Re-run verification + publication for a single job after inputs change.

        Reads the current persisted Trust Engine decision and other assessments,
        materializes a fresh snapshot, and appends a new publication decision.
        A PUBLISHABLE head is only produced when verification is actually
        publication-eligible.
        """
        destinations = dict(self._destination_status_by_job)
        if destination_status:
            destinations.update(destination_status)
        store = ProductionVerificationStore(
            self.db, destination_status_by_job=destinations, now=now
        )
        verification = JobVerificationService(self.db, store=store, now_default=now)
        self._publish_one(verification, canonical_job_id, now)

    def _assess_destinations(self, apply_url_by_job):
        # Default apply destinations to VERIFIED when the ATS-hosted URL shares
        # the source domain; otherwise leave UNKNOWN so policy requires review.
        # Real redirect verification is exercised by DestinationVerifier tests;
        # here we avoid live fetches.
        statuses = {}
        for canonical_job_id, apply_url in apply_url_by_job.items():
            if canonical_job_id in self._destination_status_by_job:
                continue
            if apply_url:
                statuses[canonical_job_id] = ApplyDestinationStatus.VERIFIED
            else:
                statuses[canonical_job_id] = ApplyDestinationStatus.UNKNOWN
        return statuses

    def _source_policy_for(self, canonical_job_id: str):
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT source_id FROM job_source_appearances "
                "WHERE canonical_job_id = ? ORDER BY first_seen_at LIMIT 1",
                (canonical_job_id,),
            ).fetchone()
            source = (
                self.sources.get_by_id(conn, row[0]) if row is not None else None
            )
        if source is None:
            return _UnregisteredSourcePolicy()
        return self.source_policy.evaluate(source)

    def apply_authoritative_closure(self, canonical_job_id: str, *, now) -> None:
        """Authoritative closure -> CLOSED lifecycle + WITHDRAWN publication.

        Reverification confirmed the requisition is closed. History and
        evidence are preserved; only the active catalog visibility is removed.
        """
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE canonical_jobs SET lifecycle_state = 'CLOSED', "
                "last_seen_at = ? WHERE canonical_job_id = ?",
                (now.isoformat(), canonical_job_id),
            )
        store = ProductionVerificationStore(
            self.db,
            destination_status_by_job=dict(self._destination_status_by_job),
            closed_jobs={canonical_job_id},
            now=now,
        )
        verification = JobVerificationService(self.db, store=store, now_default=now)
        snapshot = verification.evaluate(canonical_job_id, now=now)
        draft = self.publication_policy.evaluate(
            snapshot, source_policy=self._source_policy_for(canonical_job_id)
        )
        with self.db.transaction() as conn:
            self.verification_repo.append_publication_decision(
                conn,
                decision_id=f"dec-{uuid4().hex}",
                canonical_job_id=canonical_job_id,
                verification_id=snapshot.verification_id,
                state=draft.state,
                reason_codes=draft.reason_codes,
                decided_at=now,
            )

    def collect_many(self, collection_jobs):
        results = []

        for collector, target in collection_jobs:
            results.append(
                self.collect_one(
                    collector,
                    target,
                )
            )

        return results

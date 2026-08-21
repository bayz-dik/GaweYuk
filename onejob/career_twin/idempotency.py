from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from onejob.career_twin.errors import IdempotencyConflict
from onejob.career_twin.repositories import IdempotencyRepository


def request_fingerprint(payload: object) -> str:
    """Deterministic fingerprint of a command request payload.

    Mappings are hashed order-independently via sorted keys so that logically
    identical requests produce the same fingerprint.
    """
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class IdempotencyOutcome:
    replay: bool
    result_reference: str | None


def reserve_idempotency(
    conn: sqlite3.Connection,
    repo: IdempotencyRepository,
    *,
    idempotency_key: str,
    fingerprint: str,
    now: datetime,
) -> IdempotencyOutcome:
    """Reserve an idempotency key inside the current transaction.

    - New key: reserve and report replay=False.
    - Same key + same request: report replay=True with the stored result
      reference so the caller can return the original result.
    - Same key + different request: raise IdempotencyConflict.
    """
    existing = repo.get(conn, idempotency_key)

    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise IdempotencyConflict(
                f"idempotency key reused with different request: "
                f"{idempotency_key}"
            )
        return IdempotencyOutcome(
            replay=True,
            result_reference=existing.result_reference,
        )

    repo.store(
        conn,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        result_reference=None,
        now=now,
    )
    return IdempotencyOutcome(replay=False, result_reference=None)

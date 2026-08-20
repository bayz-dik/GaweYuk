from __future__ import annotations

import hashlib
import json


def canonical_payload_hash(item: dict) -> str:
    payload = json.dumps(
        item,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    return hashlib.sha256(payload).hexdigest()


def stable_observation_id(
    source_key: str,
    external_id: str,
    payload_hash: str,
) -> str:
    raw = (
        f"{source_key}|{external_id}|{payload_hash}"
    ).encode()

    return hashlib.sha256(raw).hexdigest()

from __future__ import annotations


def evidence_family_for(
    source_key: str,
    upstream_family: dict[str, str] | None = None,
) -> str:
    if upstream_family and source_key in upstream_family:
        return upstream_family[source_key]
    return source_key

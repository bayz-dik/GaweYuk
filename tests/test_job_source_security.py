import pytest

from onejob.job_verification.destination import (
    SafeFetchPolicy,
    UnsafeFetchTarget,
)


def _resolver(mapping=None):
    mapping = mapping or {}

    def resolve(host: str) -> list[str]:
        return mapping.get(host, ["93.184.216.34"])

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.1.2.3/x",
        "http://172.16.0.1/x",
        "http://192.168.0.1/x",
        "http://0.0.0.0/x",
        "http://[fe80::1]/x",
        "file:///etc/passwd",
        "gopher://example.com/",
        "https://admin:secret@example.com/",
    ],
)
def test_ssrf_targets_rejected(url):
    with pytest.raises(UnsafeFetchTarget):
        SafeFetchPolicy(resolver=_resolver()).validate_url(url)


def test_credentials_never_appear_in_assessment():
    from onejob.job_verification.destination import DestinationVerifier

    verifier = DestinationVerifier(
        fetch_policy=SafeFetchPolicy(resolver=_resolver())
    )
    # A URL without userinfo (userinfo already rejected by policy); ensure the
    # serialized assessment carries no Authorization/cookie/token fields.
    assessment = verifier.verify(
        "https://jobs.example.com/apply",
        allowed_domains=("jobs.example.com",),
        fetcher=lambda url: [url],
    )
    payload = assessment.model_dump()
    serialized = str(payload).lower()
    for secret_marker in ("authorization", "cookie", "api_key", "secret", "token"):
        assert secret_marker not in serialized

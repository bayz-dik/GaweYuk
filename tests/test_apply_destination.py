import pytest

from onejob.job_verification.destination import (
    ApplyDestinationStatus,
    DestinationVerifier,
    SafeFetchPolicy,
    UnsafeFetchTarget,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/private",
        "http://192.168.1.1/private",
        "http://[::1]/admin",
        "file:///etc/passwd",
        "ftp://example.com/jobs",
        "https://user:pass@example.com/jobs",
    ],
)
def test_fetch_policy_rejects_private_or_non_http_targets(url):
    with pytest.raises(UnsafeFetchTarget):
        SafeFetchPolicy(resolver=_fake_resolver()).validate_url(url)


def _fake_resolver(mapping=None):
    mapping = mapping or {}

    def resolve(host: str) -> list[str]:
        if host in mapping:
            return mapping[host]
        # Default public IP for unknown public hostnames.
        return ["93.184.216.34"]

    return resolve


def test_public_https_url_is_allowed():
    # Should not raise.
    SafeFetchPolicy(resolver=_fake_resolver()).validate_url(
        "https://jobs.example.com/apply"
    )


def test_dns_resolving_to_private_ip_is_rejected():
    resolver = _fake_resolver({"evil.example.com": ["10.0.0.5"]})
    with pytest.raises(UnsafeFetchTarget):
        SafeFetchPolicy(resolver=resolver).validate_url(
            "https://evil.example.com/apply"
        )


def test_verified_relationship_destination_is_verified():
    verifier = DestinationVerifier(
        fetch_policy=SafeFetchPolicy(resolver=_fake_resolver())
    )
    assessment = verifier.verify(
        "https://careers.contoh.co.id/apply/1",
        allowed_domains=("careers.contoh.co.id",),
        fetcher=_no_redirect_fetcher(),
    )
    assert assessment.destination_status is ApplyDestinationStatus.VERIFIED
    assert assessment.resolved_domain == "careers.contoh.co.id"


def test_unrelated_public_destination_is_allowed_external():
    verifier = DestinationVerifier(
        fetch_policy=SafeFetchPolicy(resolver=_fake_resolver())
    )
    assessment = verifier.verify(
        "https://third-party-jobs.example/apply/1",
        allowed_domains=("careers.contoh.co.id",),
        fetcher=_no_redirect_fetcher(),
    )
    assert assessment.destination_status is ApplyDestinationStatus.ALLOWED_EXTERNAL


def test_redirect_to_private_ip_is_blocked():
    def redirecting_fetcher(url):
        return ["https://evil.example.com/step", "http://169.254.169.254/meta"]

    resolver = _fake_resolver({"evil.example.com": ["93.184.216.34"]})
    verifier = DestinationVerifier(fetch_policy=SafeFetchPolicy(resolver=resolver))
    assessment = verifier.verify(
        "https://jobs.example.com/apply",
        allowed_domains=(),
        fetcher=redirecting_fetcher,
    )
    assert assessment.destination_status is ApplyDestinationStatus.BLOCKED


def test_none_apply_url_is_unknown():
    verifier = DestinationVerifier(
        fetch_policy=SafeFetchPolicy(resolver=_fake_resolver())
    )
    assessment = verifier.verify(
        None, allowed_domains=(), fetcher=_no_redirect_fetcher()
    )
    assert assessment.destination_status is ApplyDestinationStatus.UNKNOWN


def _no_redirect_fetcher():
    def fetcher(url):
        return [url]

    return fetcher

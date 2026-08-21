from __future__ import annotations

import hashlib
import ipaddress
import socket
from typing import Callable
from urllib.parse import urlsplit

from onejob.job_verification.models import (
    ApplyDestinationAssessment,
    ApplyDestinationStatus,
)


class UnsafeFetchTarget(RuntimeError):
    pass


Resolver = Callable[[str], list[str]]
Fetcher = Callable[[str], list[str]]

_BLOCKED_HOSTNAMES = {"localhost"}


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    return [info[4][0] for info in infos]


class SafeFetchPolicy:
    """SSRF-resistant URL policy for any adapter or destination fetch.

    Payload-supplied URLs are untrusted input; this policy applies even when
    the originating source is trusted. DNS is resolved through an injectable
    resolver so tests never touch the network.
    """

    def __init__(self, *, resolver: Resolver | None = None):
        self._resolver = resolver or _default_resolver

    def validate_url(self, url: str) -> None:
        parts = urlsplit(url)

        if parts.scheme not in ("http", "https"):
            raise UnsafeFetchTarget(f"scheme not allowed: {parts.scheme!r}")

        # Credentials embedded in the URL are never forwarded.
        if parts.username or parts.password:
            raise UnsafeFetchTarget("userinfo credentials are not allowed")

        host = parts.hostname
        if not host:
            raise UnsafeFetchTarget("missing host")

        # Reject obvious local hostnames before DNS; a resolver stub cannot be
        # trusted to map these to safe addresses.
        if host.lower() in _BLOCKED_HOSTNAMES or host.lower().endswith(".localhost"):
            raise UnsafeFetchTarget(f"blocked hostname: {host}")

        for address in self._resolve_all(host):
            self._reject_unsafe_ip(address)

    def _resolve_all(self, host: str) -> list[str]:
        # A literal IP host is validated directly; otherwise resolve DNS.
        try:
            ipaddress.ip_address(host.strip("[]"))
            return [host.strip("[]")]
        except ValueError:
            return self._resolver(host)

    @staticmethod
    def _reject_unsafe_ip(address: str) -> None:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeFetchTarget(f"blocked network target: {address}")


def _domain_of(url: str) -> str | None:
    return urlsplit(url).hostname


def _matches_allowed(domain: str | None, allowed_domains: tuple[str, ...]) -> bool:
    if domain is None:
        return False
    for allowed in allowed_domains:
        if domain == allowed or domain.endswith("." + allowed):
            return True
    return False


class DestinationVerifier:
    """Assess the safety of a user-facing apply destination.

    Redirects are part of the verification boundary: every hop must satisfy the
    same SSRF policy, and a redirect into a private/blocked target fails closed.
    """

    def __init__(self, *, fetch_policy: SafeFetchPolicy):
        self._policy = fetch_policy

    def verify(
        self,
        apply_url: str | None,
        *,
        allowed_domains: tuple[str, ...],
        fetcher: Fetcher,
    ) -> ApplyDestinationAssessment:
        if apply_url is None:
            return ApplyDestinationAssessment(
                original_apply_url=None,
                resolved_apply_url=None,
                resolved_domain=None,
                redirect_chain_fingerprint=None,
                destination_status=ApplyDestinationStatus.UNKNOWN,
                reason_codes=("NO_APPLY_URL",),
            )

        try:
            self._policy.validate_url(apply_url)
        except UnsafeFetchTarget:
            return ApplyDestinationAssessment(
                original_apply_url=apply_url,
                resolved_apply_url=None,
                resolved_domain=None,
                redirect_chain_fingerprint=None,
                destination_status=ApplyDestinationStatus.BLOCKED,
                reason_codes=("UNSAFE_ORIGINAL_URL",),
            )

        chain = fetcher(apply_url)
        for hop in chain:
            try:
                self._policy.validate_url(hop)
            except UnsafeFetchTarget:
                return ApplyDestinationAssessment(
                    original_apply_url=apply_url,
                    resolved_apply_url=None,
                    resolved_domain=None,
                    redirect_chain_fingerprint=_fingerprint(chain),
                    destination_status=ApplyDestinationStatus.BLOCKED,
                    reason_codes=("UNSAFE_REDIRECT_TARGET",),
                )

        resolved = chain[-1] if chain else apply_url
        domain = _domain_of(resolved)

        if _matches_allowed(domain, allowed_domains):
            status = ApplyDestinationStatus.VERIFIED
            reasons = ("MATCHED_VERIFIED_DOMAIN",)
        else:
            status = ApplyDestinationStatus.ALLOWED_EXTERNAL
            reasons = ("PUBLIC_EXTERNAL_DESTINATION",)

        return ApplyDestinationAssessment(
            original_apply_url=apply_url,
            resolved_apply_url=resolved,
            resolved_domain=domain,
            redirect_chain_fingerprint=_fingerprint(chain),
            destination_status=status,
            reason_codes=reasons,
        )


def _fingerprint(chain: list[str]) -> str:
    raw = "|".join(chain).encode()
    return hashlib.sha256(raw).hexdigest()

"""Security helpers for OCI refs and local extraction paths."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from .errors import OciSecurityError
from .types import OciReferrer, OciVerificationReport

_SENSITIVE_KEYS = ("password", "token", "authorization", "bearer")
_SLSA_LEVEL_RE = re.compile(r"slsa(?:[.-_ ]level)?[=: ]+([0-9]+)", re.IGNORECASE)


def host_from_ref(ref: str) -> str:
    value = ref.strip()
    if not value:
        raise OciSecurityError("empty OCI reference")
    host = value.split("/", 1)[0].strip()
    if not host:
        raise OciSecurityError(f"invalid OCI reference: {ref!r}")
    return host.lower()


def assert_allowlisted(ref: str, allowlist_domains: tuple[str, ...]) -> None:
    if not allowlist_domains:
        return
    host = host_from_ref(ref)
    for allowed in allowlist_domains:
        key = allowed.strip().lower()
        if not key:
            continue
        if host == key or host.endswith(f".{key}"):
            return
    raise OciSecurityError(f"registry host '{host}' is not in OCI allowlist")


def safe_output_path(base_dir: Path, relative_path: str) -> Path:
    target = (base_dir / relative_path).resolve()
    root = base_dir.resolve()
    if target == root:
        return target
    if root not in target.parents:
        raise OciSecurityError(f"path traversal blocked for extracted path: {relative_path}")
    return target


def redact_token(value: str) -> str:
    if not value:
        return value
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-2:]}"


def redact_command_for_log(command: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for item in command:
        lower = item.lower()
        if skip_next:
            redacted.append("***")
            skip_next = False
            continue
        if lower in {"--password", "--token"}:
            redacted.append(item)
            skip_next = True
            continue
        if any(key in lower for key in _SENSITIVE_KEYS):
            redacted.append("***")
            continue
        if "://" in item:
            parsed = urlsplit(item)
            if parsed.password:
                safe_netloc = parsed.netloc.replace(parsed.password, "***")
                redacted.append(item.replace(parsed.netloc, safe_netloc))
                continue
        redacted.append(item)
    return redacted


def evaluate_trust_report(
    referrers: list[OciReferrer],
    *,
    strict: bool = True,
    require_signature: bool = True,
    require_sbom: bool = True,
    require_provenance: bool = True,
) -> OciVerificationReport:
    signature_valid = any(_is_signature_referrer(item) for item in referrers)
    sbom_present = any(_is_sbom_referrer(item) for item in referrers)
    provenance_present = any(_is_provenance_referrer(item) for item in referrers)
    slsa_level = _resolve_slsa_level(referrers)

    failures: list[str] = []
    if require_signature and not signature_valid:
        failures.append("missing_or_invalid_signature")
    if require_sbom and not sbom_present:
        failures.append("missing_sbom")
    if require_provenance and not provenance_present:
        failures.append("missing_provenance")

    trust_score = 0.0
    trust_score += 0.5 if signature_valid else 0.0
    trust_score += 0.2 if sbom_present else 0.0
    trust_score += 0.2 if provenance_present else 0.0
    if slsa_level is not None:
        trust_score += min(max(slsa_level, 0), 4) * 0.025
    trust_score = round(min(trust_score, 1.0), 4)

    strict_failures = tuple(failures if strict else ())
    return OciVerificationReport(
        signature_valid=signature_valid,
        sbom_present=sbom_present,
        provenance_present=provenance_present,
        slsa_level=slsa_level,
        trust_score=trust_score,
        strict_failures=strict_failures,
        referrers=tuple(referrers),
    )


def _is_signature_referrer(referrer: OciReferrer) -> bool:
    kind = f"{referrer.artifact_type} {' '.join(referrer.annotations.values())}".lower()
    return "cosign" in kind or "signature" in kind or "sigstore" in kind


def _is_sbom_referrer(referrer: OciReferrer) -> bool:
    kind = f"{referrer.artifact_type} {' '.join(referrer.annotations.values())}".lower()
    return "spdx" in kind or "cyclonedx" in kind or "sbom" in kind


def _is_provenance_referrer(referrer: OciReferrer) -> bool:
    kind = f"{referrer.artifact_type} {' '.join(referrer.annotations.values())}".lower()
    return "provenance" in kind or "slsa" in kind or "in-toto" in kind


def _resolve_slsa_level(referrers: list[OciReferrer]) -> int | None:
    detected: int | None = None
    for referrer in referrers:
        values = [referrer.artifact_type, *referrer.annotations.values()]
        for value in values:
            text = str(value)
            match = _SLSA_LEVEL_RE.search(text)
            if match:
                try:
                    level = int(match.group(1))
                except ValueError:
                    continue
                if detected is None or level > detected:
                    detected = level
    return detected

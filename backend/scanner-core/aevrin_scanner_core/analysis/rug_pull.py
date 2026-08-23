"""Rug-pull (tool drift) detection.

The official MCP SDK inspection gives us a signature per server per scan; the
tools themselves keep their own local pin state, but our containers are
disposable, so we own persistence: the backend stores the last signature
hash per (target, server, tool_name) and calls `diff_signatures` on every
scan. A drift is a rug-pull finding, the server changed what it told a
previous scan it does.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from ..classification.owasp import OwaspMcpCategory
from ..models import Finding, Location, Severity, ToolName


def hash_signature(signature: object) -> str:
    canonical = json.dumps(signature, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class PinnedSignature:
    server_name: str
    signature_hash: str


def diff_signatures(
    scan_id: UUID,
    tool: ToolName,
    previous: list[PinnedSignature],
    current: list[PinnedSignature],
) -> list[Finding]:
    """previous/current are the last-known and this-scan pins for the same
    target. Only servers present in both are compared, a server appearing
    for the first time has nothing to drift from yet."""
    previous_by_name = {p.server_name: p.signature_hash for p in previous}
    findings: list[Finding] = []
    for entry in current:
        prior_hash = previous_by_name.get(entry.server_name)
        if prior_hash is None or prior_hash == entry.signature_hash:
            continue
        findings.append(
            Finding(
                scan_id=scan_id,
                tool=tool,
                owasp_category=OwaspMcpCategory.RUG_PULL,
                severity=Severity.CRITICAL,
                title=f"Tool description changed since last scan: {entry.server_name}",
                description=(
                    f"The pinned tool description hash for '{entry.server_name}' no "
                    "longer matches what was recorded on a previous scan. This server's "
                    "behavior may have changed after install/approval, a classic rug pull."
                ),
                location=Location(tool_name_in_manifest=entry.server_name),
                remediation=(
                    "Review what changed before trusting this server further. If the "
                    "change is expected (a legitimate update), re-approve it to re-pin "
                    "the new hash."
                ),
                raw={"previous_hash": prior_hash, "current_hash": entry.signature_hash},
            )
        )
    return findings

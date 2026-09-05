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

from ..mcp.catalog import RULE_CATALOG
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
                tool=ToolName.AEVRIN_MANIFEST_RULES,
                rule_id="AS-012",
                owasp_category=RULE_CATALOG["AS-012"].owasp,
                severity=Severity.CRITICAL,
                title=RULE_CATALOG["AS-012"].title,
                description=(
                    f"The pinned tool-definition hash for '{entry.server_name}' no longer "
                    "matches what a previous scan of this same target recorded. What this "
                    "server tells an agent it does has changed since it was last reviewed."
                ),
                remediation=RULE_CATALOG["AS-012"].fix,
                evidence=[
                    f"previous signature: {prior_hash[:16]}",
                    f"current signature: {entry.signature_hash[:16]}",
                ],
                affected_tools=[entry.server_name],
                location=Location(tool_name_in_manifest=entry.server_name),
                raw={"previous_hash": prior_hash, "current_hash": entry.signature_hash},
            )
        )
    return findings

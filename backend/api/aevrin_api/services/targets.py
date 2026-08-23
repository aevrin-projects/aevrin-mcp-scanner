"""How a scan target is keyed once it is stored.

Shared by the dashboard scan route and the Claude Code hook route. It lived in
the scans route while only one caller needed it, which left the hook route
importing from another route; both now depend on this instead.
"""

from __future__ import annotations

import hashlib


def stored_target(target_type: str, target: str) -> str:
    """The durable key for a target.

    A pasted configuration can be arbitrarily long and is not something anyone
    wants to read back in a history list, so it collapses to a short digest.
    Everything else is already a stable identifier (a repo URL, a path, a server
    URL) and is stored as-is.
    """
    if target_type != "config_paste":
        return target
    digest = hashlib.sha256(target.encode()).hexdigest()[:12]
    return f"Pasted MCP configuration · {digest}"

"""Expected: 0 findings. os.path.basename() is a modeled sanitizer for all
three filesystem rules."""

import os


@mcp.tool()
def write_report(filename: str, content: str) -> str:
    """Write a report, filename basename only."""
    safe_name = os.path.basename(filename)
    with open(safe_name, "w") as f:
        f.write(content)
    return "ok"

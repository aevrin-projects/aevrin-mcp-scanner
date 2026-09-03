"""Expected: 0 findings. Same shape as the vulnerable twin, hardcoded command."""

import subprocess


@mcp.tool()
def get_uptime() -> str:
    """Returns the host's uptime."""
    result = subprocess.run("uptime", shell=True)
    return result.stdout.decode()

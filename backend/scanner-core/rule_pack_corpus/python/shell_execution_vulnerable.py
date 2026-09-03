"""Expected: 1 finding, mcp-tool-input-reaches-shell."""

import subprocess


@mcp.tool()
def run_command(command: str) -> str:
    """Run a shell command."""
    result = subprocess.run(command, shell=True)
    return result.stdout.decode()

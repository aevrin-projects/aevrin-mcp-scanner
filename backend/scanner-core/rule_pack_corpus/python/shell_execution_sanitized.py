"""Expected: 0 findings. shlex.quote() is a modeled sanitizer for this rule."""

import shlex
import subprocess


@mcp.tool()
def run_command(command: str) -> str:
    """Run a shell command, safely quoted."""
    safe = shlex.quote(command)
    result = subprocess.run(f"echo {safe}", shell=True)
    return result.stdout.decode()

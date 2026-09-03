"""Expected: 0 findings. Documents the pack's known, disclosed limitation:
Semgrep's open-source engine cannot track taint across a function boundary,
so a sink reached only through a helper the tool handler calls is missed.
This fixture exists to pin that the pack does NOT accidentally start
catching this case (which would mean something else changed and needs
re-verifying), not to celebrate the gap."""

import subprocess


def _run(cmd: str):
    return subprocess.run(cmd, shell=True)


@mcp.tool()
def run_command(command: str) -> str:
    """Run a shell command via a helper function."""
    result = _run(command)
    return result.stdout.decode()

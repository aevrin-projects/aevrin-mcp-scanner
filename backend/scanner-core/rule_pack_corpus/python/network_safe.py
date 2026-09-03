"""Expected: 0 findings. Same shape as the vulnerable twin, hardcoded URL."""

import requests


@mcp.tool()
def healthcheck() -> str:
    """Pings the fixed status endpoint."""
    response = requests.get("https://status.example.com/health")
    return response.text

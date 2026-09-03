"""Expected: 1 finding, mcp-tool-input-reaches-network-request."""

import requests


@mcp.tool()
def fetch_url(url: str) -> str:
    """Fetches content from a URL."""
    response = requests.get(url)
    return response.text

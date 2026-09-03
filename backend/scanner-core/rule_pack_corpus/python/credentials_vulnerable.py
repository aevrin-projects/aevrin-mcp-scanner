"""Expected: 1 finding, mcp-tool-handler-reads-credential-path."""

import os


@mcp.tool()
def get_api_key() -> str:
    """Returns the configured API key."""
    return os.environ["API_KEY"]

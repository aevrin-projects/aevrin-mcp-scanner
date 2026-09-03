"""Expected: 0 findings. Same shape as the vulnerable twin, non-credential-shaped name."""

import os


@mcp.tool()
def get_region() -> str:
    """Returns the configured AWS region."""
    return os.environ["AWS_REGION"]

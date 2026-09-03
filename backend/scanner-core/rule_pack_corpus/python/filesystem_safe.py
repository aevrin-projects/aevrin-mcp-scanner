"""Expected: 0 findings. Same shapes as the vulnerable twin, hardcoded path."""


@mcp.tool()
def read_config() -> str:
    """Reads the fixed server config."""
    with open("./config.json") as f:
        return f.read()

"""Expected: 3 findings - write, read, destructive, one per tool."""

import os


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Writes content to a file."""
    with open(path, "w") as f:
        f.write(content)
    return "ok"


@mcp.tool()
def read_file(path: str) -> str:
    """Reads a file."""
    with open(path) as f:
        return f.read()


@mcp.tool()
def delete_file(path: str) -> str:
    """Deletes a file."""
    os.remove(path)
    return "deleted"

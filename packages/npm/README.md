# Aevrin CLI for npm

Install the Aevrin MCP Security Scanner CLI globally:

```bash
npm install --global aevrin
aevrin --version
aevrin login
```

The npm package creates a private Python environment inside its own installation directory and
installs the matching Aevrin release from PyPI. It does not modify global Python packages.
Python 3.10 or newer is required. Set `AEVRIN_PYTHON` when npm should use a specific Python
executable, or `AEVRIN_PYPI_INDEX_URL` when your environment requires a custom Python package
index.

Complete documentation: https://mcp.aevrin.net/docs

Support: support@aevrin.net

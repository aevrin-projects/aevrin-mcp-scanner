#!/bin/bash
# Registers the Aevrin PreToolUse hook in this project's .claude/settings.json.
# Safe to re-run — merges into any existing hooks config with jq rather than
# overwriting the file.
set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SETTINGS_FILE="$PROJECT_DIR/.claude/settings.json"
SNIPPET_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/settings.snippet.json"

mkdir -p "$PROJECT_DIR/.claude"

if [[ ! -f "$SETTINGS_FILE" ]]; then
  cp "$SNIPPET_FILE" "$SETTINGS_FILE"
  echo "Created $SETTINGS_FILE with the Aevrin hook."
else
  if ! command -v jq >/dev/null 2>&1; then
    echo "jq is required to merge into an existing settings.json. Install jq, or manually merge:" >&2
    echo "$SNIPPET_FILE" >&2
    exit 1
  fi
  merged=$(jq -s '.[0] * .[1]' "$SETTINGS_FILE" "$SNIPPET_FILE")
  echo "$merged" > "$SETTINGS_FILE"
  echo "Merged the Aevrin hook into $SETTINGS_FILE."
fi

echo ""
echo "Set AEVRIN_API_KEY in your environment to activate scanning (see"
echo "your Aevrin account's API keys settings page). Without it, the hook"
echo "installs but allows everything silently."

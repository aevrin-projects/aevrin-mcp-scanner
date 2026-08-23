export const CLI_INSTALL_COMMANDS = [
  {
    id: "macos",
    label: "macOS",
    value: "brew install pipx\npipx ensurepath\npipx install aevrin",
  },
  {
    id: "linux",
    label: "Linux",
    value: "python3 -m pip install --user pipx\npython3 -m pipx ensurepath\npipx install aevrin",
  },
  {
    id: "windows",
    label: "Windows PowerShell",
    value: "py -m pip install --user pipx\npy -m pipx ensurepath\npipx install aevrin",
  },
  {
    id: "npm",
    label: "npm",
    value: "npm install --global aevrin",
  },
] as const;

export const CLI_VERIFY_COMMANDS =
  "aevrin --version\n" +
  "aevrin login";

export const API_KEY_ENV_COMMANDS = [
  {
    id: "mac-linux",
    label: "macOS and Linux",
    value:
      'export AEVRIN_API_KEY="your-secret"\n' +
      "aevrin scan https://github.com/owner/repo --upload",
  },
  {
    id: "windows-ps",
    label: "Windows PowerShell",
    value:
      '$env:AEVRIN_API_KEY="your-secret"\n' +
      "aevrin scan https://github.com/owner/repo --upload",
  },
  {
    id: "windows-cmd",
    label: "Windows Command Prompt",
    value:
      "set AEVRIN_API_KEY=your-secret\n" +
      "aevrin scan https://github.com/owner/repo --upload",
  },
] as const;

export const AGENT_INSTALL_PROMPT = `Set up the Aevrin CLI on this machine and verify the installation end to end.

1. Detect the operating system and shell. Do not use sudo and do not modify the system Python.
2. Choose exactly one installation path. If Node.js 18+ and npm are already available, run: npm install --global aevrin. Otherwise use pipx and install it with the matching command:
   - macOS: brew install pipx && pipx ensurepath
   - Linux: python3 -m pip install --user pipx && python3 -m pipx ensurepath
   - Windows PowerShell: py -m pip install --user pipx; py -m pipx ensurepath
3. For pipx, install or upgrade Aevrin with: pipx install aevrin (use pipx upgrade aevrin if already installed). For npm, use: npm install --global aevrin@latest. Do not install both variants in the same run.
4. Run: aevrin --version
5. Run: aevrin login
6. Pause while I approve the browser device-login page. Never ask me to paste a password, API key, or browser token into the terminal.
7. After approval, show me how to run a local check with: aevrin scan . --no-upload --fail-on high

Report every command you executed and its result. If a command fails, stop at that command, preserve the full non-secret error, and explain the smallest corrective action.`;

export const AGENT_HOOK_PROMPT = `Configure Aevrin's Claude Code PreToolUse security hook for this project without overwriting existing settings.

1. Verify the CLI first with: aevrin --version
2. Run: aevrin hook setup
3. Pause while I approve the browser device-login page. Never request or print the resulting credential.
4. Copy the exact PreToolUse JSON printed by Aevrin.
5. Open this project's .claude/settings.json. If it exists, preserve every existing key and hook; merge the new Bash and Write matcher entries instead of replacing the file. If it does not exist, create it.
6. Validate that the finished file is valid JSON.
7. Confirm that Bash commands using claude mcp add and full writes to .mcp.json or claude_desktop_config.json are covered. Do not claim partial Edit operations are covered.
8. Show me the final non-secret hook configuration and the file path changed.

Stop if setup fails, JSON cannot be merged safely, or an existing matcher conflicts. Do not invent paths or credentials and do not run an MCP server as part of setup.`;

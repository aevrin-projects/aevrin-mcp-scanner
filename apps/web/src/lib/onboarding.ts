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

export const AGENT_INSTALL_PROMPT = `Install the Aevrin CLI on this machine.
Use the operating system-appropriate pipx installation steps first if pipx is missing, then install Aevrin, run aevrin --version, and run aevrin login.
Tell me the exact commands you ran, and stop immediately if any command fails.`;

export const AGENT_HOOK_PROMPT = `Install and configure the Aevrin MCP security hook in this project.
Run aevrin hook setup, complete the login flow it opens, then add the PreToolUse hook it generates to my Claude Code settings so any claude mcp add command or edit to .mcp.json / claude_desktop_config.json is checked against Aevrin before the install completes.
Show me the exact hook configuration you added when you finish.`;

#!/usr/bin/env node

import { existsSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const packageMetadata = JSON.parse(readFileSync(path.join(packageRoot, "package.json"), "utf8"));
const environmentRoot = path.join(packageRoot, ".aevrin-python");
const environmentPython =
  process.platform === "win32"
    ? path.join(environmentRoot, "Scripts", "python.exe")
    : path.join(environmentRoot, "bin", "python");

export function pythonCandidates(platform = process.platform, environment = process.env) {
  const configured = environment.AEVRIN_PYTHON?.trim();
  const candidates = [];
  if (configured) candidates.push({ command: configured, prefix: [] });
  if (platform === "win32") candidates.push({ command: "py", prefix: ["-3.10"] });
  candidates.push({ command: "python3", prefix: [] }, { command: "python", prefix: [] });
  return candidates;
}

export function supportedPython(candidate) {
  const checked = spawnSync(
    candidate.command,
    [
      ...candidate.prefix,
      "-c",
      "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)",
    ],
    { stdio: "ignore", shell: false },
  );
  return checked.status === 0;
}

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit", shell: false });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`${command} exited with status ${result.status ?? "unknown"}`);
  }
}

function installedVersion() {
  if (!existsSync(environmentPython)) return null;
  const result = spawnSync(
    environmentPython,
    [
      "-c",
      "from importlib.metadata import version; print(version('aevrin'))",
    ],
    { encoding: "utf8", shell: false },
  );
  return result.status === 0 ? result.stdout.trim() : null;
}

export function install() {
  if (process.env.AEVRIN_NPM_SKIP_INSTALL === "1") {
    console.log("Aevrin Python installation skipped by AEVRIN_NPM_SKIP_INSTALL=1.");
    return;
  }

  if (installedVersion() === packageMetadata.version) return;

  const candidate = pythonCandidates().find(supportedPython);
  if (!candidate) {
    throw new Error(
      "Aevrin requires Python 3.10 or newer. Install Python, then rerun npm install -g aevrin. " +
        "Set AEVRIN_PYTHON to a specific Python executable when necessary.",
    );
  }

  console.log(`Installing Aevrin ${packageMetadata.version} into an isolated Python environment...`);
  run(candidate.command, [...candidate.prefix, "-m", "venv", environmentRoot]);

  const indexUrl =
    process.env.AEVRIN_PYPI_INDEX_URL?.trim() || "https://pypi.org/simple";
  run(environmentPython, [
    "-m",
    "pip",
    "install",
    "--disable-pip-version-check",
    "--no-cache-dir",
    "--index-url",
    indexUrl,
    `aevrin==${packageMetadata.version}`,
  ]);

  if (installedVersion() !== packageMetadata.version) {
    throw new Error("Aevrin installed, but its version could not be verified.");
  }
}

const invokedDirectly =
  process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (invokedDirectly) {
  try {
    install();
  } catch (error) {
    console.error(`Aevrin installation failed: ${error instanceof Error ? error.message : error}`);
    process.exitCode = 1;
  }
}

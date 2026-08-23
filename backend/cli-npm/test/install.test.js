import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { pythonCandidates, supportedPython } from "../scripts/install-python.js";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("npm and Python CLI versions stay aligned", () => {
  const packageVersion = JSON.parse(
    readFileSync(path.join(packageRoot, "package.json"), "utf8"),
  ).version;
  const pythonProject = readFileSync(path.join(packageRoot, "..", "cli", "pyproject.toml"), "utf8");
  const pythonVersion = pythonProject.match(/^version = "([^"]+)"/m)?.[1];
  assert.equal(packageVersion, pythonVersion);
});

test("configured Python takes precedence", () => {
  const candidates = pythonCandidates("linux", { AEVRIN_PYTHON: "/opt/python" });
  assert.deepEqual(candidates[0], { command: "/opt/python", prefix: [] });
});

test("the current machine has a supported Python runtime", () => {
  assert.ok(pythonCandidates().some(supportedPython));
});

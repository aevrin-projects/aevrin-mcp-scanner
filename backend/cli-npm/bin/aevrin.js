#!/usr/bin/env node

import { existsSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const pythonExecutable =
  process.platform === "win32"
    ? path.join(packageRoot, ".aevrin-python", "Scripts", "python.exe")
    : path.join(packageRoot, ".aevrin-python", "bin", "python");

if (!existsSync(pythonExecutable)) {
  const installer = path.join(packageRoot, "scripts", "install-python.js");
  const installed = spawnSync(process.execPath, [installer], { stdio: "inherit" });
  if (installed.error) {
    console.error(`Aevrin could not start its installer: ${installed.error.message}`);
    process.exit(1);
  }
  if (installed.status !== 0 || !existsSync(pythonExecutable)) {
    process.exit(installed.status ?? 1);
  }
}

const child = spawn(
  pythonExecutable,
  ["-m", "aevrin_cli.main", ...process.argv.slice(2)],
  { stdio: "inherit", env: process.env },
);

child.on("error", (error) => {
  console.error(`Aevrin could not start: ${error.message}`);
  process.exitCode = 1;
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.exitCode = signal === "SIGINT" ? 130 : 1;
    return;
  }
  process.exitCode = code ?? 1;
});

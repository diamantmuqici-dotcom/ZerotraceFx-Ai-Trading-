"use strict";

const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const path = require("node:path");
const { app } = require("electron");

function pythonCommand() {
  if (process.env.ZT_PYTHON) return { command: process.env.ZT_PYTHON, args: [] };
  if (process.platform === "win32") return { command: "py", args: ["-3.13"] };
  return { command: "python3", args: [] };
}

function startBackend(root) {
  const apiToken = process.env.REMOTE_API_TOKEN || crypto.randomBytes(24).toString("hex");
  const packaged = app.isPackaged;
  const python = packaged
    ? { command: path.join(process.resourcesPath, "python-app", "ZeroTraceFXAI.exe"), args: [] }
    : pythonCommand();
  const child = spawn(
    python.command,
    [...python.args, ...(packaged ? ["api"] : [path.join(root, "main.py"), "api"])],
    {
      cwd: packaged ? path.join(process.resourcesPath, "python-app") : root,
      env: {
        ...process.env,
        ACCOUNT_MODE: "LIVE",
        REAL_ONLY: "true",
        REMOTE_API_ENABLED: "true",
        REMOTE_API_HOST: "127.0.0.1",
        REMOTE_API_PORT: process.env.REMOTE_API_PORT || "8765",
        REMOTE_API_TOKEN: apiToken
      },
      stdio: ["ignore", "pipe", "pipe"]
    }
  );
  child.stdout.on("data", data => console.log(`[python] ${data}`));
  child.stderr.on("data", data => console.error(`[python] ${data}`));
  child.on("error", error => console.error("Python backend failed", error));
  return { child, apiToken, port: Number(process.env.REMOTE_API_PORT || 8765) };
}

module.exports = { startBackend };

"use strict";

const path = require("node:path");
const { app, BrowserWindow, ipcMain, Menu } = require("electron");
const { createWindow } = require("./window");
const { hardenSession } = require("./security");
const { startBackend } = require("./process");
const { installMenu } = require("./menu");
const { registerShortcuts, unregisterShortcuts } = require("./shortcuts");
const { applyWindowTheme } = require("./theme");

let mainWindow;
let backend;

async function requestApi({ method, path: route, body }) {
  const url = `http://127.0.0.1:${backend.port}${route}`;
  const response = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${backend.apiToken}`,
      ...(body ? { "Content-Type": "application/json" } : {})
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const text = await response.text();
  let payload;
  try { payload = JSON.parse(text); } catch { payload = { error: text }; }
  if (!response.ok) throw new Error(payload.error || `API ${response.status}`);
  return payload;
}

function registerIpc() {
  ipcMain.handle("api-request", (_event, request) => requestApi(request));
  ipcMain.handle("app-info", () => ({
    name: "ZeroTrace FX AI",
    version: app.getVersion(),
    mode: "LIVE",
    venue: "MetaTrader 5"
  }));
}

async function boot() {
  await app.whenReady();
  hardenSession(require("electron").session.defaultSession);
  backend = startBackend(path.join(__dirname, ".."));
  registerIpc();
  mainWindow = createWindow();
  installMenu(mainWindow);
  applyWindowTheme(mainWindow);
  registerShortcuts(mainWindow);
  mainWindow.on("closed", () => { mainWindow = null; });
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) mainWindow = createWindow(); });
}

app.on("window-all-closed", () => {
  if (backend?.child && !backend.child.killed) backend.child.kill();
  if (process.platform !== "darwin") app.quit();
});
app.on("before-quit", () => {
  unregisterShortcuts();
  if (backend?.child && !backend.child.killed) backend.child.kill();
});
boot().catch(error => {
  console.error(error);
  app.quit();
});

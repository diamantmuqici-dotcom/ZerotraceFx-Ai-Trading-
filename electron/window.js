"use strict";

const path = require("node:path");
const { BrowserWindow, screen } = require("electron");
const { isTrustedNavigation } = require("./security");

function createWindow() {
  const display = screen.getPrimaryDisplay();
  const area = display.workAreaSize;
  const width = Math.min(1760, Math.max(1180, area.width - 80));
  const height = Math.min(1120, Math.max(760, area.height - 80));
  const window = new BrowserWindow({
    width,
    height,
    minWidth: 960,
    minHeight: 640,
    show: false,
    title: "ZeroTrace FX AI",
    backgroundColor: "#080b11",
    backgroundMaterial: process.platform === "win32" ? "mica" : undefined,
    autoHideMenuBar: true,
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "hidden",
    roundedCorners: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false
    }
  });

  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, url) => {
    if (!isTrustedNavigation(url)) event.preventDefault();
  });
  window.once("ready-to-show", () => window.show());
  window.loadFile(path.join(__dirname, "..", "ui", "index.html"));
  return window;
}

module.exports = { createWindow };

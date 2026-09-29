"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("zerotrace", Object.freeze({
  request: (method, path, body) => ipcRenderer.invoke("api-request", {
    method,
    path,
    body: body || null
  }),
  appInfo: () => ipcRenderer.invoke("app-info"),
  platform: process.platform
}));

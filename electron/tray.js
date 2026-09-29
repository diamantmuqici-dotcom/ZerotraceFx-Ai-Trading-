"use strict";
const { Tray, Menu, app } = require("electron");
function installTray(window,icon){const tray=new Tray(icon);tray.setToolTip("ZeroTrace FX AI — real MT5 terminal");tray.setContextMenu(Menu.buildFromTemplate([{label:"Show terminal",click:()=>window.show()},{type:"separator"},{label:"Quit",click:()=>app.quit()}]));tray.on("click",()=>window.show());return tray;}
module.exports={installTray};

"use strict";
const { Menu } = require("electron");
function installMenu(window){const template=[{label:"View",submenu:[{role:"reload"},{role:"togglefullscreen"},{type:"separator"},{role:"toggledevtools"}]},{label:"Terminal",submenu:[{label:"Close all positions",click:()=>window.webContents.send("request-close-all")},{role:"quit"}]}];Menu.setApplicationMenu(Menu.buildFromTemplate(template));}
module.exports={installMenu};

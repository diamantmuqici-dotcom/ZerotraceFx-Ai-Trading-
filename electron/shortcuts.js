"use strict";
const { globalShortcut } = require("electron");
function registerShortcuts(window){globalShortcut.register("CommandOrControl+Shift+Z",()=>{if(window.isMinimized())window.restore();window.show();window.focus()});}
function unregisterShortcuts(){globalShortcut.unregisterAll();}
module.exports={registerShortcuts,unregisterShortcuts};

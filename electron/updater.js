"use strict";
const { net } = require("electron");
async function checkRelease(url){if(!url)return null;return new Promise(resolve=>{const request=net.request(url);request.on("response",response=>resolve({status:response.statusCode}));request.on("error",()=>resolve(null));request.end()})}
module.exports={checkRelease};

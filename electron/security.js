"use strict";

/** Apply Chromium hardening for the local terminal window. */
function hardenSession(session) {
  session.webRequest.onHeadersReceived((details, callback) => {
    const headers = details.responseHeaders || {};
    headers["Content-Security-Policy"] = [
      "default-src 'self';",
      "connect-src 'self' data:;",
      "img-src 'self' data: blob:;",
      "style-src 'self';",
      "script-src 'self';",
      "font-src 'self' data:;",
      "object-src 'none';",
      "base-uri 'none';",
      "form-action 'self'"
    ].join(" ");
    callback({ responseHeaders: headers });
  });
}

function isTrustedNavigation(url) {
  return url.startsWith("file://") || url.startsWith("devtools://");
}

module.exports = { hardenSession, isTrustedNavigation };

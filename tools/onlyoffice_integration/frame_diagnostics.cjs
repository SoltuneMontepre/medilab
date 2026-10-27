"use strict";

function collectFrameDiagnostics(page) {
  return Promise.all(page.frames().map(frame => frame.evaluate(() =>
    Array.from(document.querySelectorAll("canvas, textarea, [contenteditable]"))
      .map(el => ({tag: el.tagName, id: el.id, editable: el.getAttribute("contenteditable")})).slice(0, 20))
    .catch(() => [])));
}

module.exports = {collectFrameDiagnostics};

"use strict";

function visitEditorsInOrder(urls, openEditor) {
  // One participant finishes destruction and closure before the next mutates the shared document history.
  return urls.reduce((previous, url) => previous.then(async () => {
    const editor = await openEditor(url);
    await editor.evaluate(() => window.editor.destroyEditor());
    await editor.close();
  }), Promise.resolve());
}

module.exports = {visitEditorsInOrder};

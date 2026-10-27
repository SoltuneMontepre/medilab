/* The editor configuration is data, never executable code. Upstream events may contain credentials: never log them. */
(() => {
    "use strict";
    const page = document.getElementById("laboratory-editor");
    if (!page?.dataset.editorConfig) return;
    const status = document.getElementById("editor-status");
    const retry = document.getElementById("editor-retry");
    const messages = Object.fromEntries(
        [...document.querySelectorAll("[data-message]")].map((node) => [node.dataset.message, node.textContent]),
    );
    let dirty = false;
    let timer;
    function show(state, canRetry = false) {
        status.textContent = messages[state];
        retry.hidden = !canRetry;
    }
    function failed() {
        clearTimeout(timer);
        show("failed", true);
    }
    function expired() {
        clearTimeout(timer);
        show("expired", true);
    }
    window.onbeforeunload = (event) => {
        if (dirty) {
            event.preventDefault();
            return "true";
        }
        return undefined;
    };
    const script = document.createElement("script");
    script.src = page.dataset.scriptUrl;
    script.referrerPolicy = "no-referrer";
    script.onerror = failed;
    script.onload = () => {
        try {
            if (!window.DocsAPI?.DocEditor) return failed();
            const config = JSON.parse(page.dataset.editorConfig);
            config.width = "100%";
            config.height = "100%";
            config.events = {
                onAppReady: () => show("connecting"),
                onDocumentReady: () => {
                    clearTimeout(timer);
                    show("ready");
                },
                onDocumentStateChange: (event) => {
                    dirty = event.data === true;
                    show(dirty ? "editing" : "sent");
                },
                onError: failed,
                onWarning: failed,
                onRequestRefreshFile: expired,
                onOutdatedVersion: expired,
            };
            new window.DocsAPI.DocEditor("onlyoffice-editor", config);
        } catch {
            failed();
        }
    };
    timer = window.setTimeout(() => show("timeout", true), 30000);
    document.head.append(script);
})();

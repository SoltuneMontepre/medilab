(function () {
    "use strict";

    function boot() {
        var IconifyIcon = customElements.get("iconify-icon");
        if (!IconifyIcon || typeof IconifyIcon.addCollection !== "function") {
            console.error("[theme] iconify-icon web component is not available");
            return;
        }

        // Offline only: an empty API provider stops missing icons from being fetched from api.iconify.design.
        if (typeof IconifyIcon.addAPIProvider === "function") {
            IconifyIcon.addAPIProvider("", {
                resources: [],
                rotate: 1,
                timeout: 1,
            });
        }

        var collections = window.__medilabIconifyCollections || [];
        for (var i = 0; i < collections.length; i++) {
            IconifyIcon.addCollection(collections[i]);
        }
    }

    if (customElements.get("iconify-icon")) {
        boot();
    } else if (customElements.whenDefined) {
        customElements.whenDefined("iconify-icon").then(boot);
    }
})();

/** @odoo-module **/

import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";

const APP_ICONS_BY_XMLID = {
    "analysis.menu_sample_collection_root": "mdi:package-variant",
    "base.menu_administration": "mdi:cog",
    "base.menu_management": "mdi:apps",
};

const APP_ICONS_BY_MODULE = {
    analysis: "mdi:flask",
    commerce: "mdi:cart-outline",
    inventory: "mdi:package-variant",
    mail: "mdi:message-text",
    contacts: "mdi:account-group",
    calendar: "mdi:calendar",
    account: "mdi:receipt-text-outline",
    base: "mdi:apps",
};

function sectionMatchesAction(section, actionId, actionPath) {
    if (!section) {
        return false;
    }
    if (actionId && section.actionID == actionId) {
        return true;
    }
    if (actionPath && section.actionPath === actionPath) {
        return true;
    }
    return (section.childrenTree || []).some((child) => sectionMatchesAction(child, actionId, actionPath));
}

patch(NavBar.prototype, {
    setup() {
        super.setup();
        this.appDrawer = useState({ open: false });
        this.navHighlight = useState({ actionId: false, actionPath: false });
        this.syncNavHighlight();
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this.syncNavHighlight());
    },

    syncNavHighlight() {
        const action = this.actionService.currentController?.action;
        this.navHighlight.actionId = action?.id || false;
        this.navHighlight.actionPath = action?.path || false;
    },

    isSectionActive(section) {
        return sectionMatchesAction(section, this.navHighlight.actionId, this.navHighlight.actionPath);
    },

    getAppIcon(app) {
        const xmlid = (app?.xmlid || "").toLowerCase();
        return APP_ICONS_BY_XMLID[xmlid] || APP_ICONS_BY_MODULE[xmlid.split(".")[0]] || "mdi:apps";
    },

    toggleAppDrawer() {
        this.appDrawer.open = !this.appDrawer.open;
    },

    closeAppDrawer() {
        this.appDrawer.open = false;
    },

    async onAppDrawerClick(app) {
        this.closeAppDrawer();
        await this.menuService.selectMenu(app);
    },

    onNavBarDropdownItemSelection(menu) {
        this.closeAppDrawer();
        if (menu) {
            this.menuService.selectMenu(menu);
        }
    },
});

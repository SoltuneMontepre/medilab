/** @odoo-module **/

import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";
import { useEffect, useRef, useState } from "@odoo/owl";

const APP_ICONS_BY_XMLID = {
    "laboratory.menu_sample_collection_root": "mdi:package-variant",
    "laboratory.menu_master_data_root": "mdi:database",
    "laboratory.menu_people_root": "mdi:account-group",
    "base.menu_administration": "mdi:cog",
    "base.menu_management": "mdi:apps",
};

const APP_ICONS_BY_MODULE = {
    laboratory: "mdi:flask",
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

// Lowercases and strips Vietnamese accents so "kho" matches "Kho" and "don" matches "Đơn".
function normalizeSearch(text) {
    return (text || "")
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .replace(/đ/gi, "d")
        .toLowerCase()
        .trim();
}

patch(NavBar.prototype, {
    setup() {
        super.setup();
        this.appDrawer = useState({ open: false, query: "" });
        this.appSearchRef = useRef("appSearch");
        this.navHighlight = useState({ actionId: false, actionPath: false });
        this.syncNavHighlight();
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this.syncNavHighlight());
        useEffect(
            (open) => {
                if (open) {
                    this.appSearchRef.el?.focus();
                }
            },
            () => [this.appDrawer.open]
        );
    },

    get filteredApps() {
        const query = normalizeSearch(this.appDrawer.query);
        const apps = this.menuService.getApps();
        return query ? apps.filter((app) => normalizeSearch(app.name).includes(query)) : apps;
    },

    get currentAppId() {
        return this.menuService.getCurrentApp()?.id;
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
        this.appDrawer.query = "";
        this.appDrawer.open = !this.appDrawer.open;
    },

    closeAppDrawer() {
        this.appDrawer.open = false;
    },

    onAppDrawerKeydown(ev) {
        if (ev.key === "Escape") {
            ev.stopPropagation();
            this.closeAppDrawer();
        } else if (ev.key === "Enter" && ev.target === this.appSearchRef.el && this.filteredApps.length) {
            ev.preventDefault();
            this.onAppDrawerClick(this.filteredApps[0]);
        }
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

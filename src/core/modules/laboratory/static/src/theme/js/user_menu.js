/** @odoo-module **/

import { registry } from "@web/core/registry";

const userMenuItems = registry.category("user_menuitems");
for (const item of ["odoo_account", "install_pwa"]) {
    if (userMenuItems.contains(item)) {
        userMenuItems.remove(item);
    }
}

import { registry } from "@web/core/registry";

const userMenuItems = registry.category("user_menuitems");
for (const item of ["support", "install_pwa", "mysubscription_user_menu"]) {
    if (userMenuItems.contains(item)) {
        userMenuItems.remove(item);
    }
}

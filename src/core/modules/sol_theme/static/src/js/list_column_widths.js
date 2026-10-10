import { registry } from "@web/core/registry";

// Odoo shrinks every column to its minWidth when a list overflows, which truncates badges and tags.
const PILL_COLUMN_MIN_WIDTHS = {
    badge: [140],
    many2many_tags: [140],
    many2many_tags_avatar: [140],
};

const fieldRegistry = registry.category("fields");
for (const [widgetName, width] of Object.entries(PILL_COLUMN_MIN_WIDTHS)) {
    for (const key of [widgetName, `list.${widgetName}`]) {
        if (fieldRegistry.contains(key)) {
            const field = fieldRegistry.get(key);
            if (!field.listViewWidth) {
                field.listViewWidth = width;
            }
        }
    }
}

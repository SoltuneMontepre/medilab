import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

// Odoo 20 hardcodes "1 record" / "N records" in ListRenderer.getGroupText without translation.
patch(ListRenderer.prototype, {
  getGroupText(group) {
    return group.count <= 1
      ? _t("%s record", group.count)
      : _t("%s records", group.count);
  },
});

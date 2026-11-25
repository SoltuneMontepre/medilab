import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { HtmlField, htmlField } from "@web/views/fields/html/html_field";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

// An HTML field that opens Odoo form modals for links carrying data-res-model and data-res-id.
export class HtmlRecordLinkField extends HtmlField {
  static template = "sol_commerce.HtmlRecordLinkField";

  setup() {
    super.setup();
    this.dialog = useService("dialog");
  }

  onClick(ev) {
    const link = ev.target.closest("a[data-res-model][data-res-id]");
    if (!link) {
      return;
    }
    ev.preventDefault();
    const resModel = link.dataset.resModel;
    const resId = Number(link.dataset.resId);
    if (!resModel || !resId) {
      return;
    }
    this.dialog.add(FormViewDialog, {
      resModel,
      resId,
      title: link.textContent.trim(),
    });
  }
}

registry.category("fields").add("medilab_html_links", {
  ...htmlField,
  component: HtmlRecordLinkField,
});

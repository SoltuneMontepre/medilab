import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

// A link that switches the form's notebook to a named tab and scrolls it into view.
export class OpenTabWidget extends Component {
  static template = "sol_commerce.OpenTabWidget";
  props = useProps({
    ...standardWidgetProps,
    tab: t.string(),
    label: t.string(),
    icon: t.string().optional(),
  });

  onClick(ev) {
    ev.preventDefault();
    const form = ev.currentTarget.closest(".o_form_view");
    const link = form?.querySelector(`.o_notebook_headers .nav-link[name="${this.props.tab}"]`);
    if (!link) {
      return;
    }
    link.click();
    link.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

registry.category("view_widgets").add("medilab_open_tab", {
  component: OpenTabWidget,
  extractProps: ({ attrs }) => ({
    tab: attrs.tab || "",
    label: attrs.string || "",
    icon: attrs.icon || "",
  }),
});

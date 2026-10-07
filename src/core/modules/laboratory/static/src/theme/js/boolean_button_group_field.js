import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class BooleanButtonGroupField extends Component {
  static template = "analysis.BooleanButtonGroupField";
  static props = { ...standardFieldProps };

  get trueLabel() {
    return this.props.trueLabel || _t("Yes");
  }

  get falseLabel() {
    return this.props.falseLabel || _t("No");
  }

  get value() {
    return this.props.record.data[this.props.name];
  }

  setValue(value) {
    if (this.props.readonly) {
      return;
    }
    this.props.record.update({ [this.props.name]: value });
  }
}

registry.category("fields").add("boolean_button_group", {
  component: BooleanButtonGroupField,
  supportedTypes: ["boolean"],
  extractProps: ({ options }) => ({
    trueLabel: options.trueLabel,
    falseLabel: options.falseLabel,
  }),
});

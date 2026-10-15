import { registry } from "@web/core/registry";
import { BooleanField, booleanField } from "@web/views/fields/boolean/boolean_field";

// A checkbox that clears the same field on the other lines of its list when it is ticked.
export class ExclusiveBooleanField extends BooleanField {
  onChange(newValue) {
    super.onChange(newValue);
    if (!newValue) {
      return;
    }
    const record = this.props.record;
    const siblings = Object.values(record._parentRecord?.data ?? {}).find((value) =>
      value?.records?.includes(record),
    );
    for (const sibling of siblings?.records ?? []) {
      if (sibling !== record && sibling.data[this.props.name]) {
        sibling.update({ [this.props.name]: false });
      }
    }
  }
}

registry.category("fields").add("exclusive_boolean", {
  ...booleanField,
  component: ExclusiveBooleanField,
});

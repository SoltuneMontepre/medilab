import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/views/fields/float/float_field";

// A number field that can be left empty: clearing it saves no value instead of zero.
export class NullableFloatField extends FloatField {
  parse(value) {
    return value.trim() === "" ? false : super.parse(value);
  }
}

registry.category("fields").add("nullable_float", {
  ...floatField,
  component: NullableFloatField,
});

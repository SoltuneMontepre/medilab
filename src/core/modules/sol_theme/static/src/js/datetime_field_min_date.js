import { patch } from "@web/core/utils/patch";
import { DateTimeField } from "@web/views/fields/datetime/datetime_field";

// Allow min_date / max_date options to reference a date field on the current record.
patch(DateTimeField.prototype, {
  parseLimitDate(value) {
    const data = this.props.record?.data;
    if (value && value !== "today" && data && value in data) {
      return data[value] || "today";
    }
    return super.parseLimitDate(value);
  },
});

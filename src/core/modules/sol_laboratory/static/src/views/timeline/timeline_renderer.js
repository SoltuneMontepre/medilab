import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { percentOf } from "./timeline_utils";

const { DateTime } = luxon;

const LANE_HEIGHT = 34;
const STATUS_CLASSES = {
  open: "o_timeline_item_waiting",
  assigned: "o_timeline_item_forward",
  in_progress: "o_timeline_item_forward",
  done: "o_timeline_item_finished",
  cancelled: "o_timeline_item_stopped",
};

export class TimelineRenderer extends Component {
  static template = "sol_laboratory.TimelineRenderer";
  props = useProps({
    model: t.object(),
    openRecord: t.function(),
  });

  get model() {
    return this.props.model;
  }

  get scales() {
    return [
      { key: "day", label: _t("Day") },
      { key: "week", label: _t("Week") },
      { key: "month", label: _t("Month") },
    ];
  }

  get title() {
    const { start, end } = this.model.range;
    if (this.model.meta.scale === "day") {
      return start.toLocaleString({ weekday: "long", day: "numeric", month: "long", year: "numeric" });
    }
    if (this.model.meta.scale === "month") {
      return start.toLocaleString({ month: "long", year: "numeric" });
    }
    const last = end.minus({ days: 1 });
    return `${start.toLocaleString({ day: "numeric", month: "short" })} – ${last.toLocaleString(DateTime.DATE_MED)}`;
  }

  get ticks() {
    const { start, end } = this.model.range;
    const unit = this.model.meta.scale === "day" ? "hours" : "days";
    const count = Math.round(end.diff(start, unit)[unit]);
    const today = DateTime.local().startOf("day");
    return Array.from({ length: count }, (_, index) => {
      const tick = start.plus({ [unit]: index });
      return {
        key: tick.toMillis(),
        label: this.tickLabel(tick, unit),
        width: 100 / count,
        isToday: unit === "days" && tick.hasSame(today, "day"),
        isWeekend: unit === "days" && tick.weekday > 5,
      };
    });
  }

  tickLabel(tick, unit) {
    if (unit === "hours") {
      return tick.toFormat("HH");
    }
    if (this.model.meta.scale === "month") {
      return tick.toFormat("d");
    }
    return tick.toLocaleString({ weekday: "short", day: "numeric" });
  }

  get nowOffset() {
    const { start, end } = this.model.range;
    const now = DateTime.local();
    return now >= start && now < end ? percentOf(now.toMillis(), start.toMillis(), end.toMillis()) : null;
  }

  rowStyle(row) {
    return `height: ${row.lanes * LANE_HEIGHT + 8}px`;
  }

  itemClass(item) {
    return {
      [STATUS_CLASSES[item.status] || "o_timeline_item_forward"]: true,
      o_timeline_item_point: item.isPoint,
      o_timeline_item_overdue: item.deadline && item.deadline < DateTime.local() && !["done", "cancelled"].includes(item.status),
    };
  }

  itemStyle(item) {
    const { start, end } = this.model.range;
    const left = percentOf(item.start, start.toMillis(), end.toMillis());
    const right = percentOf(item.end, start.toMillis(), end.toMillis());
    return `left: ${left}%; width: ${right - left}%; top: ${item.lane * LANE_HEIGHT + 4}px`;
  }

  itemTooltip(item) {
    const parts = [item.name];
    if (!item.isPoint) {
      parts.push(item.startAt.toLocaleString(DateTime.DATETIME_MED));
    }
    if (item.deadline) {
      parts.push(_t("Deadline: %s", item.deadline.toLocaleString(DateTime.DATETIME_MED)));
    }
    return parts.join("\n");
  }
}

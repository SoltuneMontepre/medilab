import { Domain } from "@web/core/domain";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { Model } from "@web/model/model";
import { assignLanes } from "./timeline_utils";

const { DateTime } = luxon;

// Shares of the visible period that a record without an end, and the shortest bar, take so their names stay readable.
const POINT_SHARE = 0.12;
const MIN_SHARE = 0.05;

export class TimelineModel extends Model {
  setup(params) {
    this.meta = { ...params, focus: DateTime.local() };
    this.data = { rows: [] };
    this.searchParams = null;
  }

  async load(searchParams) {
    this.searchParams = searchParams;
    this.data = await this.fetch();
  }

  get range() {
    const start = this.meta.focus.startOf(this.meta.scale);
    return { start, end: start.plus({ [this.meta.scale + "s"]: 1 }) };
  }

  get groupField() {
    const [groupBy] = this.searchParams?.groupBy || [];
    return groupBy?.split(":")[0] || this.searchParams?.context.timeline_row_field || this.meta.rowField;
  }

  async setScale(scale) {
    this.meta.scale = scale;
    await this.reload();
  }

  async move(step) {
    this.meta.focus = this.meta.focus.plus({ [this.meta.scale + "s"]: step });
    await this.reload();
  }

  async today() {
    this.meta.focus = DateTime.local();
    await this.reload();
  }

  async reload() {
    this.data = await this.fetch();
    this.notify();
  }

  async fetch() {
    const { dateStart, dateStop, dateDeadline, statusField, resModel } = this.meta;
    const { start, end } = this.range;
    const from = serializeDateTime(start);
    const to = serializeDateTime(end);
    const planned = new Domain([
      [dateStart, "<", to],
      [dateStop, ">", from],
    ]);
    const periods = [planned];
    if (dateDeadline) {
      periods.push(
        new Domain([
          [dateStart, "=", false],
          [dateDeadline, ">=", from],
          [dateDeadline, "<", to],
        ]),
      );
    }
    const domain = Domain.and([this.searchParams.domain, Domain.or(periods)]).toList();
    const groupField = this.groupField;
    const fieldNames = [...new Set(["display_name", dateStart, dateStop, dateDeadline, statusField, groupField])];
    const records = await this.orm.searchRead(resModel, domain, fieldNames.filter(Boolean), {
      context: this.searchParams.context,
    });
    return { rows: this.makeRows(records, groupField) };
  }

  makeRows(records, groupField) {
    const { dateStart, dateStop, dateDeadline, statusField } = this.meta;
    const { start: rangeStart, end: rangeEnd } = this.range;
    const span = rangeEnd.toMillis() - rangeStart.toMillis();
    const rows = new Map();
    for (const record of records) {
      const [key, label] = this.groupOf(record[groupField], groupField);
      if (!rows.has(key)) {
        rows.set(key, { key, label, items: [] });
      }
      const deadline = record[dateDeadline] ? deserializeDateTime(record[dateDeadline]) : null;
      const startAt = record[dateStart] ? deserializeDateTime(record[dateStart]) : deadline;
      const isPoint = !record[dateStart] || !record[dateStop];
      let start = startAt.toMillis();
      let end = isPoint ? start + span * POINT_SHARE : deserializeDateTime(record[dateStop]).toMillis();
      if (isPoint) {
        start = Math.min(start, rangeEnd.toMillis() - span * POINT_SHARE);
        end = start + span * POINT_SHARE;
      }
      rows.get(key).items.push({
        id: record.id,
        name: record.display_name,
        status: record[statusField],
        startAt,
        start,
        end: Math.max(end, start + span * MIN_SHARE),
        deadline,
        isPoint,
      });
    }
    const sorted = [...rows.values()].sort((a, b) => (a.key === false ? 1 : b.key === false ? -1 : String(a.label).localeCompare(String(b.label))));
    for (const row of sorted) {
      row.lanes = assignLanes(row.items);
    }
    return sorted;
  }

  groupOf(value, groupField) {
    if (value === false || value === undefined) {
      return [false, _t("None")];
    }
    if (Array.isArray(value)) {
      return [value[0], value[1]];
    }
    const selection = this.meta.fields[groupField]?.selection;
    const option = selection?.find(([key]) => key === value);
    return [value, option ? option[1] : value];
  }

  hasData() {
    return this.data.rows.length > 0;
  }
}

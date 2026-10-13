import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { assignLanes, percentOf } from "../../views/timeline/timeline_utils";

const { DateTime } = luxon;

const TASK_MODEL = "medilab.task";
const DAY_FIRST_HOUR = 7;
const DAY_LAST_HOUR = 19;
const RIBBON_LANE_HEIGHT = 44;
const ACTIONS = {
  mine: "sol_laboratory.action_medilab_task_mine",
  finished: "sol_laboratory.action_medilab_task_finished",
  awaiting: "sol_laboratory.action_medilab_task_awaiting",
  all: "sol_laboratory.action_medilab_task",
};

export class TaskViewButtons extends Component {
  static template = "sol_laboratory.TaskViewButtons";
  props = useProps({ tile: t.string(), onOpen: t.function() });

  get views() {
    return [
      { type: "list", icon: "reorder", label: _t("List") },
      { type: "calendar", icon: "calendar_today", label: _t("Calendar") },
      { type: "timeline", icon: "view_timeline", label: _t("Timeline") },
    ];
  }
}

export class TaskDashboard extends Component {
  static template = "sol_laboratory.TaskDashboard";
  static components = { TaskViewButtons };
  props = useProps(standardActionServiceProps);

  setup() {
    this.orm = useService("orm");
    this.action = useService("action");
    this.state = proxy({ data: null, busy: false });
    onWillStart(() => this.load());
  }

  async load() {
    this.state.data = await this.orm.call(TASK_MODEL, "get_dashboard_data", []);
  }

  get data() {
    return this.state.data;
  }

  get greeting() {
    const hour = DateTime.local().hour;
    const name = this.data.person.split(" ").at(-1);
    if (hour < 12) {
      return _t("Good morning, %s", name);
    }
    if (hour < 18) {
      return _t("Good afternoon, %s", name);
    }
    return _t("Good evening, %s", name);
  }

  get todayLabel() {
    return DateTime.local().toLocaleString({ weekday: "long", day: "numeric", month: "long" });
  }

  get summary() {
    const { open_count, overdue_count, due_today_count } = this.data;
    if (!open_count) {
      return _t("Nothing open on your list.");
    }
    const parts = [_t("%s open", open_count)];
    if (overdue_count) {
      parts.push(_t("%s overdue", overdue_count));
    }
    if (due_today_count) {
      parts.push(_t("%s due today", due_today_count));
    }
    return parts.join(", ") + ".";
  }

  get ribbon() {
    const planned = this.data.planned_today.map((task) => ({
      ...task,
      startAt: deserializeDateTime(task.planned_start),
      endAt: deserializeDateTime(task.planned_end),
    }));
    const dayStart = DateTime.local().startOf("day");
    const firstHour = Math.min(DAY_FIRST_HOUR, ...planned.map((task) => this.hourIn(task.startAt, dayStart)));
    const lastHour = Math.max(DAY_LAST_HOUR, ...planned.map((task) => Math.ceil(this.hourIn(task.endAt, dayStart, true))));
    const start = dayStart.plus({ hours: Math.max(Math.floor(firstHour), 0) }).toMillis();
    const end = dayStart.plus({ hours: Math.min(lastHour, 24) }).toMillis();
    const blocks = planned.map((task) => ({ ...task, start: task.startAt.toMillis(), end: task.endAt.toMillis() }));
    const lanes = assignLanes(blocks);
    const now = DateTime.local().toMillis();
    const hours = [];
    for (let time = start; time < end; time += 3600000) {
      hours.push({ key: time, label: DateTime.fromMillis(time).toFormat("HH"), left: percentOf(time, start, end) });
    }
    return {
      hours,
      height: lanes * RIBBON_LANE_HEIGHT + 8,
      now: now >= start && now < end ? percentOf(now, start, end) : null,
      blocks: blocks.map((block) => {
        const left = percentOf(block.start, start, end);
        const right = percentOf(block.end, start, end);
        return {
          ...block,
          time: `${block.startAt.toFormat("HH:mm")}–${block.endAt.toFormat("HH:mm")}`,
          style: `left: ${left}%; width: ${right - left}%; top: ${block.lane * RIBBON_LANE_HEIGHT + 4}px`,
        };
      }),
    };
  }

  hourIn(dateTime, dayStart, isEnd = false) {
    if (dateTime < dayStart) {
      return 0;
    }
    if (!dateTime.hasSame(dayStart, "day")) {
      return isEnd ? 24 : 0;
    }
    return dateTime.hour + dateTime.minute / 60;
  }

  dueLabel(task) {
    if (!task.deadline) {
      return _t("No deadline");
    }
    const deadline = deserializeDateTime(task.deadline);
    const today = DateTime.local().startOf("day");
    const time = deadline.toFormat("HH:mm");
    if (deadline < DateTime.local()) {
      return _t("Overdue since %s", deadline.toLocaleString({ weekday: "short", day: "numeric", month: "short" }));
    }
    if (deadline.hasSame(today, "day")) {
      return _t("Due today at %s", time);
    }
    if (deadline.hasSame(today.plus({ days: 1 }), "day")) {
      return _t("Due tomorrow at %s", time);
    }
    return _t("Due %s", deadline.toLocaleString({ weekday: "short", day: "numeric", month: "short" }));
  }

  isOverdue(task) {
    return task.deadline && deserializeDateTime(task.deadline) < DateTime.local();
  }

  nextAction(task) {
    if (task.status === "assigned") {
      return { method: "action_start", label: _t("Start"), className: "btn-primary" };
    }
    if (task.status === "in_progress" && !task.closed_by_system) {
      return { method: "action_done", label: _t("Mark done"), className: "btn-success" };
    }
    return null;
  }

  async run(task, method) {
    if (this.state.busy) {
      return;
    }
    this.state.busy = true;
    try {
      await this.orm.call(TASK_MODEL, method, [[task.id]]);
      await this.load();
    } finally {
      this.state.busy = false;
    }
  }

  async openTask(task) {
    const action = await this.orm.call(TASK_MODEL, "action_open_document", [[task.id]]);
    await this.action.doAction(action);
  }

  async openTile(tile, viewType) {
    await this.action.doAction(ACTIONS[tile], viewType ? { viewType } : {});
  }
}

registry.category("actions").add("sol_laboratory.task_dashboard", TaskDashboard);

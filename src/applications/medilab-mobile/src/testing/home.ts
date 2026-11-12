import type { Task, TaskDay } from "../api";

// What the home of demo.tester reads: the person, then their day.
export const PERSON = "Nguyễn Văn An";
export const GREETING = `Xin chào, ${PERSON}`;

export function me(can?: { create_tasks: boolean; assign_tasks: boolean }) {
  return {
    status: 200,
    body: {
      name: PERSON,
      login: "demo.tester",
      department: "Hoá",
      roles: ["Tester"],
      can: can ?? { create_tasks: false, assign_tasks: false },
    },
  };
}

export function task(values: Partial<Task> = {}): Task {
  return {
    id: 7,
    name: "Sort retained samples in fridge 2",
    type: "General",
    status: "assigned",
    action: "",
    deadline: "2026-11-10T09:00:00+00:00",
    planned_start: null,
    planned_end: null,
    done_at: null,
    department: "Hoá",
    assignee: PERSON,
    location: "",
    closed_by_system: false,
    document: null,
    ...values,
  };
}

export function day(values: Partial<TaskDay> = {}) {
  return {
    status: 200,
    body: {
      person: PERSON,
      day_start: "2026-11-09T17:00:00+00:00",
      day_end: "2026-11-10T17:00:00+00:00",
      open_count: 0,
      overdue_count: 0,
      due_today_count: 0,
      finished_count: 0,
      finished_week_count: 0,
      claimable_count: 0,
      next_up: [],
      planned_today: [],
      claimable: [],
      ...values,
    },
  };
}

/** The answers the home reads once it opens. */
export function home(can?: { create_tasks: boolean; assign_tasks: boolean }) {
  return [me(can), day()] as const;
}

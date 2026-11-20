import type { Me, Task, TaskDay } from "../api";

// What the app of demo.tester reads: the person, the installed modules and their day.
export const PERSON = "Nguyễn Văn An";
export const GREETING = `Xin chào, ${PERSON}`;

type Can = Partial<Me["can"]>;

export function me(can?: Can) {
  return {
    status: 200,
    body: {
      name: PERSON,
      login: "demo.tester",
      department: "Hoá",
      roles: ["Tester"],
      can: {
        create_tasks: false,
        assign_tasks: false,
        read_handover_records: false,
        scan_samples: false,
        sign_results: false,
        ...can,
      },
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

/** The installed MediLab modules, without E-commerce unless it is named. */
export function modules(...names: string[]) {
  return { status: 200, body: { modules: ["sol_laboratory", ...names] } };
}

/** The answers the home reads once it opens: the person's day. */
export function home(values: Partial<TaskDay> = {}) {
  return [day(values)] as const;
}

/** The answers the navigation reads once the phone is signed in: the person and the installed modules. */
export function person(can?: Can, installed = modules()) {
  return [me(can), installed] as const;
}

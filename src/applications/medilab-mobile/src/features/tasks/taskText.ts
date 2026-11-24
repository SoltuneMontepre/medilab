import type { Task, TaskStatus } from "../../api";
import type { Locale, MessageKey, Translate } from "../../i18n";
import type { BadgeTone } from "../shared/Badge";

const STATUS_KEYS: Record<TaskStatus, MessageKey> = {
  open: "task.status.open",
  assigned: "task.status.assigned",
  in_progress: "task.status.in_progress",
  done: "task.status.done",
  cancelled: "task.status.cancelled",
};

// A task waiting in a queue waits for someone; one given to a person is under way.
const STATUS_TONES: Record<TaskStatus, BadgeTone> = {
  open: "warning",
  assigned: "info",
  in_progress: "info",
  done: "success",
  cancelled: "danger",
};

export function statusKey(status: TaskStatus): MessageKey {
  return STATUS_KEYS[status];
}

export function statusTone(status: TaskStatus): BadgeTone {
  return STATUS_TONES[status];
}

/** A date and time of MediLab, which is in UTC, as the phone shows it in its own time zone. */
export function formatMoment(value: string, language: Locale): string {
  return new Date(value).toLocaleString(language, { dateStyle: "short", timeStyle: "short" });
}

/** The time of day of a moment of MediLab, in the phone's time zone. */
export function formatTime(value: string, language: Locale): string {
  return new Date(value).toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit" });
}

/** Whether a task not done yet is past its deadline. */
export function isOverdue(task: Task, now: Date = new Date()): boolean {
  return task.status !== "done" && !!task.deadline && new Date(task.deadline) < now;
}

/** When a task is due, or when it was done. */
export function whenText(task: Task, t: Translate, language: Locale): string {
  const when = task.status === "done" ? task.done_at : task.deadline;
  if (!when) {
    return "";
  }
  return t(task.status === "done" ? "task.doneAt" : "task.deadline", { date: formatMoment(when, language) });
}

/** How a task is read out: its name, its document's code, its status and when it is due or was done. */
export function taskLabel(task: Task, t: Translate, language: Locale): string {
  return [task.name, task.document?.code, t(statusKey(task.status)), whenText(task, t, language)]
    .filter(Boolean)
    .join(", ");
}

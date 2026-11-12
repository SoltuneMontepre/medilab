import type { TaskStatus } from "../../api";
import type { Locale, MessageKey } from "../../i18n";

const STATUS_KEYS: Record<TaskStatus, MessageKey> = {
  open: "task.status.open",
  assigned: "task.status.assigned",
  in_progress: "task.status.in_progress",
  done: "task.status.done",
  cancelled: "task.status.cancelled",
};

export function statusKey(status: TaskStatus): MessageKey {
  return STATUS_KEYS[status];
}

/** A date and time of MediLab, which is in UTC, as the phone shows it in its own time zone. */
export function formatMoment(value: string, language: Locale): string {
  return new Date(value).toLocaleString(language, { dateStyle: "short", timeStyle: "short" });
}

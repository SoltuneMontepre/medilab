// A deadline as the person types it, in the phone's time zone: 2026-11-12 17:00.
const DEADLINE = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})$/;
// The hour a task is due by when it is picked by its day.
const DEFAULT_HOUR = 17;

function twoDigits(value: number): string {
  return String(value).padStart(2, "0");
}

/** The deadline `days` days after today at 17:00 on the phone, as the person types it. */
export function deadlineIn(days: number, now: Date = new Date()): string {
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() + days, DEFAULT_HOUR, 0);
  return `${day.getFullYear()}-${twoDigits(day.getMonth() + 1)}-${twoDigits(day.getDate())} ${twoDigits(DEFAULT_HOUR)}:00`;
}

/** The deadline a new task starts with: tomorrow at 17:00 on the phone. */
export function defaultDeadline(now: Date = new Date()): string {
  return deadlineIn(1, now);
}

/** The days a deadline is offered in one tap: today while 17:00 is still to come, tomorrow and in three days. */
export function quickDays(now: Date = new Date()): number[] {
  return now.getHours() < DEFAULT_HOUR ? [0, 1, 3] : [1, 3];
}

/** The moment of a deadline typed on the phone, or null when it is not a real date and time. */
export function parseDeadline(text: string): Date | null {
  const match = DEADLINE.exec(text.trim());
  if (!match) {
    return null;
  }
  const [year, month, day, hour, minute] = match.slice(1).map(Number);
  const moment = new Date(year, month - 1, day, hour, minute);
  const exact =
    moment.getFullYear() === year &&
    moment.getMonth() === month - 1 &&
    moment.getDate() === day &&
    moment.getHours() === hour &&
    moment.getMinutes() === minute;
  return exact ? moment : null;
}

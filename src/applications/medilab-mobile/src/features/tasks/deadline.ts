// A deadline as the person types it, in the phone's time zone: 2026-11-12 17:00.
const DEADLINE = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})$/;
// The hour a new task is due by default, on the next day.
const DEFAULT_HOUR = 17;

function twoDigits(value: number): string {
  return String(value).padStart(2, "0");
}

/** The deadline a new task starts with: tomorrow at 17:00 on the phone. */
export function defaultDeadline(now: Date = new Date()): string {
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, DEFAULT_HOUR, 0);
  return `${day.getFullYear()}-${twoDigits(day.getMonth() + 1)}-${twoDigits(day.getDate())} ${twoDigits(DEFAULT_HOUR)}:00`;
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

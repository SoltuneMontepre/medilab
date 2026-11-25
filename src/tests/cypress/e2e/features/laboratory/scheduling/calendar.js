const MINUTE = 60000;
const SLOT = 15 * MINUTE;
const RUN = 30 * MINUTE;

// Convert an attendance's local wall time using that resource's timezone, including its date's UTC offset.
export function utcTime(date, hour, zone) {
  const wall = Date.parse(`${date}T00:00:00Z`) + Math.round(hour * 60) * MINUTE;
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  });
  let utc = wall;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const parts = Object.fromEntries(formatter.formatToParts(new Date(utc)).map(({ type, value }) => [type, value]));
    const shown = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour), Number(parts.minute), Number(parts.second));
    const difference = wall - shown;
    if (!difference) return utc;
    utc += difference;
  }
  throw new Error(`The attendance time ${date} ${hour} does not exist in ${zone}.`);
}

// The attendance rows of each date, the dates in order and each date's rows in their sequence.
function rowsByDate(attendances) {
  const dates = new Map();
  attendances.forEach((attendance) => {
    [attendance.date, ...attendance.other_dates].forEach((date) => {
      if (!dates.has(date)) dates.set(date, []);
      dates.get(date).push(attendance);
    });
  });
  const sorted = [...dates].sort(([left], [right]) => left.localeCompare(right));
  sorted.forEach(([, rows]) => rows.sort((left, right) => left.sequence - right.sequence || left.id - right.id));
  return sorted;
}

// The local hours a row covers: from the cursor when all rows of its date are duration-based, around noon when only it
// is, otherwise its own hours.
function rowHours(row, cursor, durationBased) {
  if (durationBased) return [cursor, cursor + row.duration_hours];
  if (row.duration_based) return [12 - row.duration_hours / 2, 12 + row.duration_hours / 2];
  return [row.hour_from, row.hour_to];
}

// The 30-minute runs between two UTC times, an hour apart from the first quarter-hour, that no leave overlaps.
function freeSlots(begin, end, leaves) {
  const slots = [];
  for (let start = Math.ceil(begin / SLOT) * SLOT; start + RUN <= end; start += 60 * MINUTE) {
    if (leaves.some((leave) => start < Date.parse(`${leave.date_to}Z`) && start + RUN > Date.parse(`${leave.date_from}Z`))) continue;
    slots.push(new Date(start).toISOString().slice(0, 19).replace("T", " "));
  }
  return slots;
}

// get_attendances expands Odoo's dated and recurring schedules; duration-based rows are centered on noon by Odoo.
export function calendarSlots(attendances, leaves, zone) {
  const slots = [];
  for (const [date, rows] of rowsByDate(attendances)) {
    const durationBased = rows.every((row) => row.duration_based);
    let cursor = 12 - rows.reduce((total, row) => total + row.duration_hours, 0) / 2;
    for (const row of rows) {
      const [from, to] = rowHours(row, cursor, durationBased);
      cursor = to;
      slots.push(...freeSlots(utcTime(date, from, zone), utcTime(date, to, zone), leaves));
      if (slots.length >= 3) return slots.slice(0, 3);
    }
  }
  throw new Error(`The tester's ${zone} calendar has fewer than three free 30-minute attendance slots.`);
}

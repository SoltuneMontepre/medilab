const MINUTE = 60000;
const SLOT = 15 * MINUTE;
const RUN = 30 * MINUTE;

// Convert an attendance's local wall time using that resource's timezone, including its date's UTC offset.
function utcTime(date, hour, zone) {
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

// get_attendances expands Odoo's dated and recurring schedules; duration-based rows are centered on noon by Odoo.
export function calendarSlots(attendances, leaves, zone) {
  const dates = new Map();
  attendances.forEach((attendance) => {
    [attendance.date, ...attendance.other_dates].forEach((date) => {
      if (!dates.has(date)) dates.set(date, []);
      dates.get(date).push(attendance);
    });
  });
  const slots = [];
  for (const [date, rows] of [...dates].sort(([left], [right]) => left.localeCompare(right))) {
    rows.sort((left, right) => left.sequence - right.sequence || left.id - right.id);
    const durationBased = rows.every((row) => row.duration_based);
    let cursor = 12 - rows.reduce((total, row) => total + row.duration_hours, 0) / 2;
    for (const row of rows) {
      const from = durationBased ? cursor : row.duration_based ? 12 - row.duration_hours / 2 : row.hour_from;
      const to = durationBased ? cursor + row.duration_hours : row.duration_based ? 12 + row.duration_hours / 2 : row.hour_to;
      cursor = to;
      const begin = utcTime(date, from, zone);
      const end = utcTime(date, to, zone);
      for (let start = Math.ceil(begin / SLOT) * SLOT; start + RUN <= end; start += 60 * MINUTE) {
        if (leaves.some((leave) => start < Date.parse(`${leave.date_to}Z`) && start + RUN > Date.parse(`${leave.date_from}Z`))) continue;
        slots.push(new Date(start).toISOString().slice(0, 19).replace("T", " "));
        if (slots.length === 3) return slots;
      }
    }
  }
  throw new Error(`The tester's ${zone} calendar has fewer than three free 30-minute attendance slots.`);
}

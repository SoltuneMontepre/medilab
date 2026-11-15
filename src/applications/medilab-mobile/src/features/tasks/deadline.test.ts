import { defaultDeadline, parseDeadline } from "./deadline";

describe("deadline", () => {
  it("starts a new task due tomorrow at 17:00", () => {
    expect(defaultDeadline(new Date(2026, 11, 31, 10, 30))).toBe("2027-01-01 17:00");
  });

  it("reads a date and time typed on the phone in its time zone", () => {
    expect(parseDeadline(" 2026-11-12 7:05 ")).toEqual(new Date(2026, 10, 12, 7, 5));
    expect(parseDeadline("2026-11-12T17:00")).toEqual(new Date(2026, 10, 12, 17, 0));
  });

  it("refuses what is not a real date and time", () => {
    for (const text of ["", "12/11/2026 17:00", "2026-02-30 09:00", "2026-11-12 24:00", "2026-11-12"]) {
      expect(parseDeadline(text)).toBeNull();
    }
  });
});

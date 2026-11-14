// A number as the tester types it: digits with a decimal point or comma, and a minus sign for a value that may be
// negative.
const TYPED_NUMBER = /^(-?\d+)(?:[.,](\d+))?$/;
// The most decimals a result shows.
const MOST_DECIMALS = 15;

/** The typed number and the decimals it was typed with, such as 3 for 0,010; null when it is not a number. */
export function parseNumber(typed: string): { value: number; decimals: number } | null {
  const match = TYPED_NUMBER.exec(typed.trim());
  if (!match) {
    return null;
  }
  const decimals = match[2]?.length ?? 0;
  if (decimals > MOST_DECIMALS) {
    return null;
  }
  return { value: Number(`${match[1]}.${match[2] ?? "0"}`), decimals };
}

/** The value with its decimals, and never fewer than it was measured with, so changing a draft keeps its value. */
export function typedNumber(value: number, decimals: number): string {
  const written = String(value);
  const measured = written.includes("e") ? decimals : (written.split(".")[1]?.length ?? 0);
  return value.toFixed(Math.min(Math.max(decimals, measured), MOST_DECIMALS));
}

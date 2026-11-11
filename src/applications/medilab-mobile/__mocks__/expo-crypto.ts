let next = 0;

export function randomUUID(): string {
  next += 1;
  return `00000000-0000-4000-8000-${String(next).padStart(12, "0")}`;
}

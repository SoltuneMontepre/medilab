import type { ResultStatus } from "../../api";
import type { BadgeTone } from "../shared/Badge";

// A draft is the tester's own; a result waiting for a signature waits for someone.
const RESULT_TONES: Record<ResultStatus, BadgeTone> = {
  none: "muted",
  requested: "warning",
  approved: "success",
  rejected: "danger",
};

export function resultTone(status: ResultStatus): BadgeTone {
  return RESULT_TONES[status];
}

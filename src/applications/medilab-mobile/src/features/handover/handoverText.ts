import type { HandoverRecordStatus } from "../../api";
import type { MessageKey } from "../../i18n";
import type { BadgeTone } from "../shared/Badge";

// A draft waits for the customer's signature; a signed record is done.
const STATUSES: Record<HandoverRecordStatus, { label: MessageKey; tone: BadgeTone }> = {
  draft: { label: "handover.drafts", tone: "warning" },
  signed: { label: "handover.signed", tone: "success" },
};

export function handoverStatus(status: HandoverRecordStatus): { label: MessageKey; tone: BadgeTone } {
  return STATUSES[status];
}

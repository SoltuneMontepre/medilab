import type { SupportRequestStatus } from "../../api";
import type { MessageKey } from "../../i18n";
import type { BadgeTone } from "../shared/Badge";

const STATUS_KEYS: Record<SupportRequestStatus, MessageKey> = {
  open: "support.status.open",
  answered: "support.status.answered",
  closed: "support.status.closed",
};

// An open request waits for an answer; an answered one is sent; a closed one is over.
const STATUS_TONES: Record<SupportRequestStatus, BadgeTone> = {
  open: "warning",
  answered: "success",
  closed: "muted",
};

export function supportStatusKey(status: SupportRequestStatus): MessageKey {
  return STATUS_KEYS[status];
}

export function supportStatusTone(status: SupportRequestStatus): BadgeTone {
  return STATUS_TONES[status];
}

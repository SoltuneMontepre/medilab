import type { SupportRequestStatus } from "../../api";
import type { MessageKey } from "../../i18n";

const STATUS_KEYS: Record<SupportRequestStatus, MessageKey> = {
  open: "support.status.open",
  answered: "support.status.answered",
  closed: "support.status.closed",
};

export function supportStatusKey(status: SupportRequestStatus): MessageKey {
  return STATUS_KEYS[status];
}

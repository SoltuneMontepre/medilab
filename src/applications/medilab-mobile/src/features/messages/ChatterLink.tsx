import { router } from "expo-router";

import type { DocumentReference } from "../../api";
import { useT } from "../../locale";
import { chatterPath } from "../documents/documentPath";
import { LinkRow } from "../shared/LinkRow";

/** Opens the chatter of a task, a sample or a test request. */
export function ChatterLink({ document }: Readonly<{ document: DocumentReference }>) {
  const t = useT();
  return (
    <LinkRow
      icon="message-text-outline"
      testID="open-chatter"
      label={t("chatter.open")}
      onPress={() => router.push(chatterPath(document))}
    />
  );
}

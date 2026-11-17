import { router } from "expo-router";

import type { DocumentReference } from "../../api";
import { useT } from "../../locale";
import { chatterPath } from "../documents/documentPath";
import { Button } from "../shared/Button";

/** Opens the chatter of a task, a sample or a test request. */
export function ChatterButton({ document }: Readonly<{ document: DocumentReference }>) {
  const t = useT();
  return <Button testID="open-chatter" label={t("chatter.open")} onPress={() => router.push(chatterPath(document))} />;
}

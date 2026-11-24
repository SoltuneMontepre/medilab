import { useLocalSearchParams } from "expo-router";
import { useCallback } from "react";
import { Linking } from "react-native";

import { ApiError, type MediLabDocument } from "../../api";
import { useLoad } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { LoadNotice } from "../connection/LoadNotice";
import { ChatterLink } from "../messages/ChatterLink";
import { LinkRow } from "../shared/LinkRow";
import { RecordHead } from "../shared/RecordHead";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";
import { CHATTER_MODELS } from "./documentPath";

/** The document a push or a notification opens, read with the person's rights. A document they can no longer see
 * says so instead of showing an empty screen. */
export function DocumentScreen() {
  const t = useT();
  const { call } = useSession();
  const { model, id } = useLocalSearchParams<{ model: string; id: string }>();

  const read = useCallback(async () => {
    const document = await call<MediLabDocument>(`/documents/${encodeURIComponent(model)}/${encodeURIComponent(id)}`);
    if (!document) {
      throw new ApiError("not_found", "", 404);
    }
    return document;
  }, [call, model, id]);
  const { load, reload } = useLoad(read);

  const document = load.state === "ready" ? load.value : null;
  return (
    <Screen title={document?.code || document?.title || ""}>
      <LoadNotice load={load} gone={t("document.gone")} onRetry={reload} />
      {document && (
        <>
          <RecordHead title={document.title} />
          <Sheet>
            <LinkRow
              icon="open-in-new"
              label={t("document.openOnWeb")}
              testID="document-open-on-web"
              onPress={() => Linking.openURL(document.url)}
            />
            {CHATTER_MODELS.includes(document.model) && <ChatterLink document={document} />}
          </Sheet>
        </>
      )}
    </Screen>
  );
}

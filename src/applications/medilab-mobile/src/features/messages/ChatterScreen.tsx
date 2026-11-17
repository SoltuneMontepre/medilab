import { useLocalSearchParams } from "expo-router";
import { useCallback } from "react";

import type { Message } from "../../api";
import { useT } from "../../locale";
import { useSession } from "../../session";
import type { Draft } from "./Composer";
import { Thread } from "./Thread";
import { usePeople } from "./usePeople";
import { useThread } from "./useThread";

/** The chatter of a task, a sample or a test request, as the web's chatter shows it to the person, where they post a
 * note mentioning people of the laboratory; a note never reaches a customer. */
export function ChatterScreen() {
  const t = useT();
  const { call } = useSession();
  const { model, id, code } = useLocalSearchParams<{ model: string; id: string; code?: string }>();
  const path = `/documents/${encodeURIComponent(model)}/${encodeURIComponent(id)}`;
  const thread = useThread(`${path}/messages`);
  const findPeople = usePeople();

  const post = useCallback(
    (draft: Draft, key: string) =>
      call<Message>(`${path}/notes`, {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: { text: draft.text, mentions: draft.mentions },
      }),
    [call, path],
  );

  return (
    <Thread
      title={code ? t("chatter.titleOf", { code }) : t("chatter.title")}
      thread={thread}
      gone={t("document.gone")}
      empty={t("chatter.empty")}
      findPeople={findPeople}
      post={post}
    />
  );
}

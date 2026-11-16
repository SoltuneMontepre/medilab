import { useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";

import type { Conversation, Message } from "../../api";
import { useT } from "../../locale";
import { watchMessagePushes } from "../../push";
import { useSession } from "../../session";
import type { Draft } from "../messages/Composer";
import { Thread } from "../messages/Thread";
import { useThread } from "../messages/useThread";
import { Button } from "../shared/Button";

// How often an open conversation asks for new messages, besides its pushes.
export const POLL_MILLISECONDS = 10_000;

/** A conversation the person is in: its messages, read again on its pushes and about every 10 seconds while it is
 * open and marked read on the web as well, where the person writes, mentions its members and attaches photos and
 * files, and mutes or unmutes it. */
export function ConversationScreen() {
  const t = useT();
  const { call } = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  const path = `/conversations/${encodeURIComponent(id)}`;
  const thread = useThread(`${path}/messages`);
  const { newer } = thread;
  const [conversation, setConversation] = useState<Conversation | null>(null);

  useEffect(() => {
    let current = true;
    call<{ conversations: Conversation[] }>("/conversations")
      .then(
        (answer) => current && setConversation(answer?.conversations.find((item) => String(item.id) === id) ?? null),
      )
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [call, id]);

  useEffect(() => {
    const polling = setInterval(() => void newer(), POLL_MILLISECONDS);
    const pushed = watchMessagePushes((document) => String(document.id) === id && void newer());
    return () => {
      clearInterval(polling);
      pushed();
    };
  }, [newer, id]);

  // What the person sees is read, on the web as well.
  const newest = thread.load.state === "ready" ? thread.load.value.at(-1) : undefined;
  useEffect(() => {
    if (newest && !newest.mine) {
      call(`${path}/seen`, { method: "POST", body: { message_id: newest.id } }).catch(() => undefined);
    }
  }, [call, path, newest]);

  const findPeople = useCallback(
    async (query: string) =>
      (conversation?.members ?? []).filter((member) => member.name.toLowerCase().includes(query.toLowerCase())),
    [conversation],
  );

  const post = useCallback(
    (draft: Draft, key: string) =>
      call<Message>(`${path}/messages`, {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: { text: draft.text, mentions: draft.mentions, files: draft.files },
      }),
    [call, path],
  );

  async function toggleMute() {
    if (!conversation) {
      return;
    }
    const changed = await call<Conversation>(`${path}/mute`, {
      method: "PUT",
      body: { muted: !conversation.muted },
    }).catch(() => null);
    if (changed) {
      setConversation(changed);
    }
  }

  return (
    <Thread
      title={conversation?.name ?? ""}
      actions={
        conversation && (
          <Button
            testID="conversation-mute"
            label={t(conversation.muted ? "conversation.unmute" : "conversation.mute")}
            onPress={toggleMute}
          />
        )
      }
      thread={thread}
      gone={t("conversation.gone")}
      empty={t("conversation.empty")}
      findPeople={findPeople}
      post={post}
      files
    />
  );
}

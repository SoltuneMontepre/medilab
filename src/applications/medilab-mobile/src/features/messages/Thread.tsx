import type { ReactNode } from "react";
import { ScrollView, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { Message, PersonName } from "../../api";
import type { Load } from "../../load";
import { useT } from "../../locale";
import { useAction } from "../../record";
import { styles as shared } from "../../styles";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { Button } from "../shared/Button";
import { Composer, type Draft } from "./Composer";
import type { useThread } from "./useThread";
import { MessageList } from "./MessageList";

/** A screen of messages: its title and actions, the messages oldest first with the way to older ones, and where the
 * person writes. `post` sends a draft with its Idempotency-Key and answers the message posted. */
export function Thread({
  title,
  actions,
  thread,
  gone,
  empty,
  findPeople,
  post,
  files = false,
}: Readonly<{
  title: string;
  actions?: ReactNode;
  thread: ReturnType<typeof useThread>;
  gone: string;
  empty: string;
  findPeople: (query: string) => Promise<PersonName[]>;
  post: (draft: Draft, key: string) => Promise<Message | null>;
  files?: boolean;
}>) {
  const t = useT();
  const { problem, busy, run } = useAction();
  const { load } = thread;

  async function send(draft: Draft, key: string) {
    let sent = false;
    await run(async () => {
      const message = await post(draft, key);
      if (message) {
        thread.add(message);
      }
      sent = true;
    });
    return sent;
  }

  return (
    <SafeAreaView style={shared.page}>
      <ScrollView contentContainerStyle={shared.pageContent} keyboardShouldPersistTaps="handled">
        <Text style={shared.title}>{title}</Text>
        {actions}
        <LoadNotice load={load as Load<unknown>} gone={gone} onRetry={thread.read} />
        {load.state === "ready" && (
          <>
            {thread.hasOlder && <Button testID="messages-older" label={t("more")} onPress={thread.older} />}
            <MessageList messages={load.value} empty={empty} />
            <ActionProblem problem={problem?.load ?? null} gone={gone} onRetry={problem?.retry ?? (() => undefined)} />
            <Composer findPeople={findPeople} onSend={send} files={files} busy={busy} />
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

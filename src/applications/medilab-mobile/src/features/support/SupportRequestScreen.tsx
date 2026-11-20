import { randomUUID } from "expo-crypto";
import { useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError, type SupportMessage, type SupportRequestDetail } from "../../api";
import { useReloadOnReturn } from "../../focus";
import { failed, useLoad, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, radius, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { ActionBar } from "../shared/ActionBar";
import { Button } from "../shared/Button";
import { Facts, type Fact } from "../shared/Facts";
import { RecordHead } from "../shared/RecordHead";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";
import { Fact as FactLine } from "../tasks/TaskRow";
import { formatMoment } from "../tasks/taskText";
import { supportStatusKey, supportStatusTone } from "./supportText";

type Action = "take" | "answer";

/** A support request with the customer's and sales' messages, taken and answered as on the web: an answer sets the
 * request answered and notifies the customer, who reads it on the portal. Sending an answer again after a lost answer
 * posts it once. */
export function SupportRequestScreen() {
  const t = useT();
  const { call } = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  const path = `/support-requests/${encodeURIComponent(id)}`;
  const [answer, setAnswer] = useState("");
  // One key per answer, so an answer sent again is posted once.
  const [answerKey, setAnswerKey] = useState(randomUUID);
  const [problem, setProblem] = useState<{ action: Action; load: Load<never> } | null>(null);
  const [busy, setBusy] = useState(false);

  const read = useCallback(async () => {
    const request = await call<SupportRequestDetail>(path);
    if (!request) {
      throw new ApiError("not_found", "", 404);
    }
    return request;
  }, [call, path]);
  const { load, setLoad, reload, refresh } = useLoad(read);
  useReloadOnReturn(refresh);

  async function act(action: Action) {
    setProblem(null);
    setBusy(true);
    try {
      const request = await call<SupportRequestDetail>(
        `${path}/${action}`,
        action === "answer"
          ? { method: "POST", headers: { "Idempotency-Key": answerKey }, body: { body: answer.trim() } }
          : { method: "POST" },
      );
      if (request) {
        setLoad({ state: "ready", value: request });
      }
      if (action === "answer") {
        setAnswer("");
        setAnswerKey(randomUUID());
      }
    } catch (error) {
      setProblem({ action, load: failed(error) });
    } finally {
      setBusy(false);
    }
  }

  const request = load.state === "ready" ? load.value : null;
  const failure = (
    <ActionProblem problem={problem?.load ?? null} gone={t("support.gone")} onRetry={() => problem && act(problem.action)} />
  );
  return (
    <Screen
      title={request?.code ?? t("support.title")}
      footer={
        request?.actions.take && (
          <ActionBar
            actions={[
              {
                key: "take",
                label: t("support.take"),
                tone: "primary",
                icon: "hand-back-right-outline",
                disabled: busy,
                testID: "support-take",
                onPress: () => act("take"),
              },
            ]}
          >
            {failure}
          </ActionBar>
        )
      }
    >
      <LoadNotice load={load} gone={t("support.gone")} onRetry={reload} />
      {request && (
        <>
          <Details request={request} />
          {request.actions.answer && (
            <Sheet title={t("support.answer")}>
              <TextInput
                accessibilityLabel={t("support.answer")}
                style={[shared.input, shared.multiline]}
                value={answer}
                onChangeText={setAnswer}
                multiline
              />
              {!request.actions.take && failure}
              <Button
                label={t("support.send")}
                icon="send-outline"
                tone="primary"
                disabled={busy || !answer.trim()}
                testID="support-send"
                onPress={() => act("answer")}
              />
            </Sheet>
          )}
          {!request.actions.take && !request.actions.answer && failure}
        </>
      )}
    </Screen>
  );
}

function Details({ request }: Readonly<{ request: SupportRequestDetail }>) {
  const t = useT();
  const { language } = useSession();
  // The navbar shows the code and the head the customer; the sheet shows the rest.
  const facts: Fact[] = [
    ["support.order", request.order],
    ["support.handledBy", request.handled_by],
    ["support.openedAt", formatMoment(request.opened_at, language)],
  ];
  return (
    <>
      <RecordHead
        title={request.subject}
        status={{ label: t(supportStatusKey(request.status)), tone: supportStatusTone(request.status) }}
      >
        <FactLine icon="account-outline" text={request.customer} />
      </RecordHead>
      <Sheet title={t("task.info")}>
        <Facts facts={facts} />
      </Sheet>
      <Sheet title={t("support.messages")}>
        {request.messages.map((message) => (
          <Message key={message.id} message={message} />
        ))}
      </Sheet>
    </>
  );
}

function Message({ message }: Readonly<{ message: SupportMessage }>) {
  const { language } = useSession();
  return (
    <View style={[styles.message, message.from_customer ? styles.fromCustomer : styles.fromSales]}>
      <Text style={shared.label}>{message.author}</Text>
      <Text style={shared.text}>{message.body}</Text>
      <Text style={shared.detail}>{formatMoment(message.date, language)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  message: { maxWidth: "88%", gap: 2, padding: space.md, borderRadius: radius.lg },
  fromCustomer: {
    alignSelf: "flex-start",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderBottomLeftRadius: radius.sm,
  },
  fromSales: { alignSelf: "flex-end", backgroundColor: colors.primaryLight, borderBottomRightRadius: radius.sm },
});

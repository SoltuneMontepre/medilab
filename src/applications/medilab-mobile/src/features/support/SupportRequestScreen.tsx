import { randomUUID } from "expo-crypto";
import { useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, type SupportMessage, type SupportRequestDetail } from "../../api";
import { useReloadOnReturn } from "../../focus";
import { failed, useLoad, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { Button } from "../shared/Button";
import { Facts, type Fact } from "../shared/Facts";
import { formatMoment } from "../tasks/taskText";
import { supportStatusKey } from "./supportText";

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
  const { load, setLoad, reload } = useLoad(read);
  useReloadOnReturn(reload);

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

  return (
    <SafeAreaView style={shared.page}>
      <LoadNotice load={load} gone={t("support.gone")} onRetry={reload} />
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={shared.pageContent}>
          <Details request={load.value} />
          <ActionProblem
            problem={problem?.load ?? null}
            gone={t("support.gone")}
            onRetry={() => problem && act(problem.action)}
          />
          {load.value.actions.take && <Button label={t("support.take")} disabled={busy} onPress={() => act("take")} />}
          {load.value.actions.answer && (
            <>
              <TextInput
                accessibilityLabel={t("support.answer")}
                style={[shared.input, styles.answer]}
                value={answer}
                onChangeText={setAnswer}
                multiline
              />
              <Button
                label={t("support.send")}
                primary
                disabled={busy || !answer.trim()}
                onPress={() => act("answer")}
              />
            </>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function Details({ request }: Readonly<{ request: SupportRequestDetail }>) {
  const t = useT();
  const { language } = useSession();
  const facts: Fact[] = [
    ["task.statusLabel", t(supportStatusKey(request.status))],
    ["sample.customer", request.customer],
    ["support.order", request.order],
    ["support.handledBy", request.handled_by],
    ["support.openedAt", formatMoment(request.opened_at, language)],
  ];
  return (
    <>
      <Text style={shared.title}>{request.subject}</Text>
      <Text style={shared.detail}>{request.code}</Text>
      <Facts facts={facts} />
      <Text accessibilityRole="header" style={shared.heading}>
        {t("support.messages")}
      </Text>
      {request.messages.map((message) => (
        <Message key={message.id} message={message} />
      ))}
    </>
  );
}

function Message({ message }: Readonly<{ message: SupportMessage }>) {
  const { language } = useSession();
  return (
    <View style={[styles.message, message.from_customer && styles.fromCustomer]}>
      <Text style={shared.label}>{message.author}</Text>
      <Text style={shared.detail}>{formatMoment(message.date, language)}</Text>
      <Text style={shared.text}>{message.body}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  message: { borderLeftWidth: 3, borderLeftColor: colors.primary, paddingLeft: 12, gap: 2 },
  fromCustomer: { borderLeftColor: colors.border },
  answer: { minHeight: 96, textAlignVertical: "top" },
});

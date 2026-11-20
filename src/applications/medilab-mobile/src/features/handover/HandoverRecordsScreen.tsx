import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { HandoverRecordPage, HandoverRecordStatus, HandoverRecordSummary } from "../../api";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { handoverRecordPath } from "../documents/documentPath";
import { Button } from "../shared/Button";
import { chosenTab, ListTabs, type ListTab } from "../shared/ListTabs";
import { formatMoment } from "../tasks/taskText";

const LISTS: ListTab<HandoverRecordStatus>[] = [
  { list: "draft", label: "handover.drafts", empty: "handover.draftsEmpty" },
  { list: "signed", label: "handover.signed", empty: "handover.signedEmpty" },
];

/** The handover records the person may read: those waiting for the customer's signature, and those signed, latest
 * handover first. */
export function HandoverRecordsScreen() {
  const t = useT();
  const { call } = useSession();
  const params = useLocalSearchParams<{ list?: string }>();
  const [list, setList] = useState(() => chosenTab(LISTS, params.list));
  const path = `/handover-records?status=${list}`;
  const { load, setLoad, reload } = useRecord<HandoverRecordPage>(path);
  const { problem, busy, run } = useAction();

  function more(page: HandoverRecordPage) {
    void run(async () => {
      const next = await call<HandoverRecordPage>(`${path}&after=${page.next_after}`);
      if (next) {
        setLoad({ state: "ready", value: { records: [...page.records, ...next.records], next_after: next.next_after } });
      }
    });
  }

  const current = LISTS.find((item) => item.list === list) ?? LISTS[0];
  return (
    <SafeAreaView style={shared.page}>
      <ScrollView contentContainerStyle={shared.pageContent}>
        <Text style={shared.title}>{t("handover.title")}</Text>
        <ListTabs tabs={LISTS} chosen={list} onChoose={setList} />
        <LoadNotice load={load} gone={t(current.empty)} onRetry={reload} />
        {load.state === "ready" && (
          <>
            {!load.value.records.length && <Text style={shared.detail}>{t(current.empty)}</Text>}
            {load.value.records.map((record) => (
              <RecordRow key={record.id} record={record} />
            ))}
            {load.value.next_after !== null && (
              <Button label={t("more")} onPress={() => more(load.value)} disabled={busy} />
            )}
          </>
        )}
        <ActionProblem problem={problem?.load ?? null} gone={t(current.empty)} onRetry={() => problem?.retry()} />
      </ScrollView>
    </SafeAreaView>
  );
}

function RecordRow({ record }: Readonly<{ record: HandoverRecordSummary }>) {
  const { language } = useSession();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[record.code, record.request, record.handed_over_by].join(", ")}
      style={shared.card}
      onPress={() => router.push(handoverRecordPath(record.id))}
    >
      <Text style={shared.label}>{record.code}</Text>
      <Text style={shared.text}>{record.request}</Text>
      <Text style={shared.detail}>
        {`${record.handed_over_by} · ${formatMoment(record.signed_at ?? record.handed_over_at, language)}`}
      </Text>
    </Pressable>
  );
}

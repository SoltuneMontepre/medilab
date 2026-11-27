import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { HandoverRecordPage, HandoverRecordStatus, HandoverRecordSummary } from "../../api";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { handoverRecordPath } from "../documents/documentPath";
import { Badge } from "../shared/Badge";
import { chosenTab, ListTabs, type ListTab } from "../shared/ListTabs";
import { RecordList } from "../shared/RecordList";
import { Screen } from "../shared/Screen";
import { Fact } from "../tasks/TaskRow";
import { formatMoment } from "../tasks/taskText";
import { handoverStatus } from "./handoverText";

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
  const { load, setLoad, reload, refresh } = useRecord<HandoverRecordPage>(path);
  const { problem, run } = useAction();

  function more() {
    if (load.state !== "ready" || load.value.next_after === null) {
      return Promise.resolve();
    }
    const page = load.value;
    return run(async () => {
      const next = await call<HandoverRecordPage>(`${path}&after=${page.next_after}`);
      if (next) {
        setLoad({ state: "ready", value: { records: [...page.records, ...next.records], next_after: next.next_after } });
      }
    });
  }

  const current = LISTS.find((item) => item.list === list) ?? LISTS[0];
  return (
    <Screen title={t("handover.title")} scroll={false}>
      <ListTabs tabs={LISTS} chosen={list} onChoose={setList} />
      <RecordList
        load={load}
        items={load.state === "ready" ? load.value.records : []}
        keyOf={(record) => record.id}
        renderItem={(record) => <RecordRow record={record} />}
        icon="clipboard-text-outline"
        empty={t(current.empty)}
        onRetry={reload}
        onRefresh={refresh}
        hasMore={load.state === "ready" && load.value.next_after !== null}
        onMore={more}
        footer={<ActionProblem problem={problem?.load ?? null} gone={t(current.empty)} onRetry={() => problem?.retry()} />}
      />
    </Screen>
  );
}

function RecordRow({ record }: Readonly<{ record: HandoverRecordSummary }>) {
  const t = useT();
  const { language } = useSession();
  const badge = handoverStatus(record.status);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[record.code, record.request, record.handed_over_by].join(", ")}
      style={({ pressed }) => [shared.card, styles.card, pressed && styles.pressed]}
      onPress={() => router.push(handoverRecordPath(record.id))}
      testID="handover-record"
    >
      <View style={styles.head}>
        <Text style={[shared.label, styles.name]}>{record.code}</Text>
        <Badge label={t(badge.label)} tone={badge.tone} />
      </View>
      <Text style={shared.text}>{record.request}</Text>
      <View style={styles.facts}>
        <Fact icon="account-outline" text={record.handed_over_by} />
        <Fact icon="clock-outline" text={formatMoment(record.signed_at ?? record.handed_over_at, language)} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.sm },
  pressed: { backgroundColor: colors.primaryLight },
  head: { flexDirection: "row", alignItems: "flex-start", gap: space.sm },
  name: { flex: 1 },
  facts: { flexDirection: "row", flexWrap: "wrap", columnGap: space.md, rowGap: space.xs },
});

import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { SupportRequest, SupportRequestList } from "../../api";
import { useReloadOnReturn } from "../../focus";
import { useLoad } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, space } from "../../theme";
import { supportRequestPath } from "../documents/documentPath";
import { Badge } from "../shared/Badge";
import { chosenTab, ListTabs, type ListTab } from "../shared/ListTabs";
import { RecordList } from "../shared/RecordList";
import { Screen } from "../shared/Screen";
import { Fact } from "../tasks/TaskRow";
import { supportStatusKey, supportStatusTone } from "./supportText";

const LISTS: ListTab<SupportRequestList>[] = [
  { list: "mine", label: "support.mine", empty: "support.mineEmpty" },
  { list: "waiting", label: "support.waiting", empty: "support.waitingEmpty" },
];

/** The support requests the person handles, and the requests waiting for a salesperson to take them, as on the web. */
export function SupportRequestsScreen() {
  const t = useT();
  const { call } = useSession();
  const params = useLocalSearchParams<{ list?: string }>();
  const [list, setList] = useState(() => chosenTab(LISTS, params.list));

  const read = useCallback(async () => {
    const answer = await call<{ requests: SupportRequest[] }>(`/support-requests?list=${list}`);
    return answer?.requests ?? [];
  }, [call, list]);
  const { load, reload, refresh } = useLoad(read);
  useReloadOnReturn(refresh);

  const current = LISTS.find((item) => item.list === list) ?? LISTS[0];
  return (
    <Screen title={t("support.title")} scroll={false}>
      <ListTabs tabs={LISTS} chosen={list} onChoose={setList} />
      <RecordList
        load={load}
        items={load.state === "ready" ? load.value : []}
        keyOf={(request) => request.id}
        renderItem={(request) => <SupportRequestRow request={request} />}
        icon="lifebuoy"
        empty={t(current.empty)}
        gone={t("support.unavailable")}
        onRetry={reload}
        onRefresh={refresh}
      />
    </Screen>
  );
}

function SupportRequestRow({ request }: Readonly<{ request: SupportRequest }>) {
  const t = useT();
  const status = t(supportStatusKey(request.status));
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[request.subject, request.code, request.customer, status].join(", ")}
      style={({ pressed }) => [shared.card, styles.card, pressed && styles.pressed]}
      onPress={() => router.push(supportRequestPath(request.id))}
    >
      <View style={styles.head}>
        <Text style={[shared.label, styles.name]} numberOfLines={2}>
          {request.subject}
        </Text>
        <Badge label={status} tone={supportStatusTone(request.status)} />
      </View>
      <View style={styles.facts}>
        <Fact icon="pound" text={request.code} />
        <Fact icon="account-outline" text={request.customer} />
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

import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { SupportRequest, SupportRequestList } from "../../api";
import { useReloadOnReturn } from "../../focus";
import { useLoad } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { LoadNotice } from "../connection/LoadNotice";
import { supportRequestPath } from "../documents/documentPath";
import { chosenTab, ListTabs, type ListTab } from "../lists/ListTabs";
import { supportStatusKey } from "./supportText";

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
  const { load, reload } = useLoad(read);
  useReloadOnReturn(reload);

  const current = LISTS.find((item) => item.list === list) ?? LISTS[0];
  return (
    <SafeAreaView style={styles.screen}>
      <Text style={shared.title}>{t("support.title")}</Text>
      <ListTabs tabs={LISTS} chosen={list} onChoose={setList} />
      <LoadNotice load={load} gone={t("support.unavailable")} onRetry={reload} />
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={styles.list}>
          {load.value.length === 0 && <Text style={shared.detail}>{t(current.empty)}</Text>}
          {load.value.map((request) => (
            <SupportRequestRow key={request.id} request={request} />
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function SupportRequestRow({ request }: Readonly<{ request: SupportRequest }>) {
  const t = useT();
  const status = t(supportStatusKey(request.status));
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[request.subject, request.code, request.customer, status].join(", ")}
      style={styles.item}
      onPress={() => router.push(supportRequestPath(request.id))}
    >
      <Text style={shared.label}>{request.subject}</Text>
      <Text style={shared.detail}>{`${request.code} · ${request.customer}`}</Text>
      <Text style={shared.detail}>{status}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: 24, gap: 16 },
  list: { gap: 8 },
  item: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 12, gap: 4 },
});

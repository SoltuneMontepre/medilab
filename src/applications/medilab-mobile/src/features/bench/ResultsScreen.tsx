import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { ResultPage, ResultSummary } from "../../api";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { resultPath } from "../documents/documentPath";
import { Badge } from "../shared/Badge";
import { RecordList } from "../shared/RecordList";
import { Screen } from "../shared/Screen";
import { Fact } from "../tasks/TaskRow";
import { resultTone } from "./resultText";

const WAITING = "/results?awaiting=me";

/** The results waiting for the person's signature, oldest first: for a head of department, those of their department
 * at their level. */
export function ResultsScreen() {
  const t = useT();
  const { call } = useSession();
  const { load, setLoad, reload, refresh } = useRecord<ResultPage>(WAITING);
  const { problem, run } = useAction();

  function more() {
    if (load.state !== "ready" || load.value.next_after === null) {
      return Promise.resolve();
    }
    const page = load.value;
    return run(async () => {
      const next = await call<ResultPage>(`${WAITING}&after=${page.next_after}`);
      if (next) {
        setLoad({ state: "ready", value: { results: [...page.results, ...next.results], next_after: next.next_after } });
      }
    });
  }

  return (
    <Screen title={t("results.title")} scroll={false}>
      <RecordList
        load={load}
        items={load.state === "ready" ? load.value.results : []}
        keyOf={(result) => result.id}
        renderItem={(result) => <ResultRow result={result} />}
        icon="file-sign"
        empty={t("results.empty")}
        onRetry={reload}
        onRefresh={refresh}
        hasMore={load.state === "ready" && load.value.next_after !== null}
        onMore={more}
        footer={<ActionProblem problem={problem?.load ?? null} gone={t("results.empty")} onRetry={() => problem?.retry()} />}
      />
    </Screen>
  );
}

function ResultRow({ result }: Readonly<{ result: ResultSummary }>) {
  const t = useT();
  const warned = result.warned ? t("results.warned") : "";
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[result.code, result.parameter, result.value_display, warned].filter(Boolean).join(", ")}
      style={({ pressed }) => [shared.card, styles.card, pressed && styles.pressed]}
      onPress={() => router.push(resultPath(result.id))}
    >
      <View style={styles.head}>
        <Text style={[shared.label, styles.name]} numberOfLines={2}>{`${result.code} – ${result.parameter}`}</Text>
        {warned ? <Badge label={warned} tone="warning" /> : <Badge label={t("results.waiting")} tone={resultTone(result.status)} />}
      </View>
      <Text style={styles.value}>{result.value_display}</Text>
      {!!result.entered_by && <Fact icon="account-outline" text={result.entered_by} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.sm },
  pressed: { backgroundColor: colors.primaryLight },
  head: { flexDirection: "row", alignItems: "flex-start", gap: space.sm },
  name: { flex: 1 },
  value: { fontSize: 18, fontWeight: "600", color: colors.text },
});

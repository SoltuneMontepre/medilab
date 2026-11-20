import { randomUUID } from "expo-crypto";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import type { Result, SampleTest } from "../../api";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { resultPath } from "../documents/documentPath";
import { Badge } from "../shared/Badge";
import { LinkRow } from "../shared/LinkRow";
import { RecordHead } from "../shared/RecordHead";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";
import { Fact } from "../tasks/TaskRow";
import { ResultForm, type ResultEntry } from "./ResultForm";
import { resultTone } from "./resultText";
import { TestFacts } from "./TestFacts";

/** A sample test at the bench: its facts, its reported result, and entering the result as the web's Enter Result
 * button lets the person. Sending the result again after a lost answer enters it once. */
export function SampleTestScreen() {
  const t = useT();
  const { call } = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  const path = `/sample-tests/${encodeURIComponent(id)}`;
  const { load, reload } = useRecord<SampleTest>(path);
  const { problem, busy, run } = useAction();
  // One key per result the person enters, so a request sent again enters nothing more.
  const [requestKey] = useState(randomUUID);

  function enter(entry: ResultEntry) {
    void run(async () => {
      const result = await call<Result>(`${path}/results`, {
        method: "POST",
        headers: { "Idempotency-Key": requestKey },
        body: entry,
      });
      if (result) {
        router.replace(resultPath(result.id));
      }
    });
  }

  const test = load.state === "ready" ? load.value : null;
  return (
    <Screen title={test?.code ?? t("test.title")}>
      <LoadNotice load={load} gone={t("test.gone")} onRetry={reload} />
      {test && (
        <>
          <RecordHead title={test.parameter}>
            {!!test.way && <Fact icon="flask-outline" text={test.way} />}
          </RecordHead>
          {test.can_enter_result && (
            <Sheet title={t("test.enterResult")}>
              <ResultForm unit={test.unit} comparisonRequested={test.comparison_requested} busy={busy} onSubmit={enter} />
              <ActionProblem problem={problem?.load ?? null} gone={t("test.gone")} onRetry={() => problem?.retry()} />
            </Sheet>
          )}
          {test.result && <ReportedResult result={test.result} />}
          {!test.can_enter_result && !test.result && <Text style={shared.detail}>{t("test.cannotEnter")}</Text>}
          <Sheet title={t("task.info")}>
            <TestFacts test={test} />
          </Sheet>
        </>
      )}
    </Screen>
  );
}

function ReportedResult({ result }: Readonly<{ result: Result }>) {
  const t = useT();
  return (
    <Sheet title={t("result.result")}>
      <View style={styles.value}>
        <Text style={styles.valueText}>{result.value_display}</Text>
        <Badge label={result.status_label} tone={resultTone(result.status)} />
      </View>
      <LinkRow
        icon="file-document-outline"
        label={t("test.openResult")}
        testID="test-open-result"
        onPress={() => router.push(resultPath(result.id))}
      />
    </Sheet>
  );
}

const styles = StyleSheet.create({
  value: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space.md },
  valueText: { flex: 1, fontSize: 22, fontWeight: "700", color: colors.text },
});

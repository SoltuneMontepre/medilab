import { randomUUID } from "expo-crypto";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { Result, SampleTest } from "../../api";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { resultPath } from "../documents/documentPath";
import { ResultForm, type ResultEntry } from "./ResultForm";
import { Button } from "../shared/Button";
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

  return (
    <SafeAreaView style={shared.page}>
      <LoadNotice load={load} gone={t("test.gone")} onRetry={reload} />
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={shared.pageContent} keyboardShouldPersistTaps="handled">
          <Text style={shared.title}>{load.value.parameter}</Text>
          <TestFacts test={load.value} />
          {load.value.result && <ReportedResult result={load.value.result} />}
          {load.value.can_enter_result && (
            <View style={shared.section}>
              <Text accessibilityRole="header" style={shared.heading}>
                {t("test.enterResult")}
              </Text>
              <ResultForm
                unit={load.value.unit}
                comparisonRequested={load.value.comparison_requested}
                busy={busy}
                onSubmit={enter}
              />
            </View>
          )}
          {!load.value.can_enter_result && !load.value.result && (
            <Text style={shared.detail}>{t("test.cannotEnter")}</Text>
          )}
          <ActionProblem problem={problem?.load ?? null} gone={t("test.gone")} onRetry={() => problem?.retry()} />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function ReportedResult({ result }: Readonly<{ result: Result }>) {
  const t = useT();
  return (
    <View style={shared.section}>
      <Text accessibilityRole="header" style={shared.heading}>
        {t("result.result")}
      </Text>
      <Text style={shared.text}>{result.value_display}</Text>
      <Text style={shared.detail}>{result.status_label}</Text>
      <Button label={t("test.openResult")} onPress={() => router.push(resultPath(result.id))} primary />
    </View>
  );
}

import { router } from "expo-router";
import { Pressable, ScrollView, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { ResultPage, ResultSummary } from "../../api";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { resultPath } from "../documents/documentPath";
import { Button } from "../shared/Button";

const WAITING = "/results?awaiting=me";

/** The results waiting for the person's signature, oldest first: for a head of department, those of their department
 * at their level. */
export function ResultsScreen() {
  const t = useT();
  const { call } = useSession();
  const { load, setLoad, reload } = useRecord<ResultPage>(WAITING);
  const { problem, busy, run } = useAction();

  function more(page: ResultPage) {
    void run(async () => {
      const next = await call<ResultPage>(`${WAITING}&after=${page.next_after}`);
      if (next) {
        setLoad({ state: "ready", value: { results: [...page.results, ...next.results], next_after: next.next_after } });
      }
    });
  }

  return (
    <SafeAreaView style={shared.page}>
      <ScrollView contentContainerStyle={shared.pageContent}>
        <Text style={shared.title}>{t("results.title")}</Text>
        <LoadNotice load={load} gone={t("results.empty")} onRetry={reload} />
        {load.state === "ready" && (
          <>
            {!load.value.results.length && <Text style={shared.detail}>{t("results.empty")}</Text>}
            {load.value.results.map((result) => (
              <ResultRow key={result.id} result={result} />
            ))}
            {load.value.next_after !== null && (
              <Button label={t("more")} onPress={() => more(load.value)} disabled={busy} />
            )}
          </>
        )}
        <ActionProblem problem={problem?.load ?? null} gone={t("results.empty")} onRetry={() => problem?.retry()} />
      </ScrollView>
    </SafeAreaView>
  );
}

function ResultRow({ result }: Readonly<{ result: ResultSummary }>) {
  const t = useT();
  const warned = result.warned ? t("results.warned") : "";
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[result.code, result.parameter, result.value_display, warned].filter(Boolean).join(", ")}
      style={shared.card}
      onPress={() => router.push(resultPath(result.id))}
    >
      <Text style={shared.label}>{`${result.code} – ${result.parameter}`}</Text>
      <Text style={shared.text}>{result.value_display}</Text>
      <Text style={shared.detail}>{[result.entered_by, warned].filter(Boolean).join(" · ")}</Text>
    </Pressable>
  );
}

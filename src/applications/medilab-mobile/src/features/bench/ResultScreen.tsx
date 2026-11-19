import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { Call, Result } from "../../api";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { Facts } from "../shared/Facts";
import { formatMoment } from "../tasks/taskText";
import { Button } from "../shared/Button";
import { ResultForm, type ResultEntry } from "./ResultForm";

type Step = "reading" | "changing" | "signing" | "rejecting";

/** A result with its limit and its warnings, and what the web's form lets the person do with it: change the draft,
 * send it for approval or approve it with a deliberate signature, and reject it with a reason. A result that is
 * approved, or waits for someone else's signature, is only shown. */
export function ResultScreen() {
  const t = useT();
  const { call } = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  const path = `/results/${encodeURIComponent(id)}`;
  const { load, setLoad, reload } = useRecord<Result>(path);
  const { problem, busy, run } = useAction();
  const [step, setStep] = useState<Step>("reading");

  function act(suffix: string, request: Omit<Call, "key">) {
    void run(async () => {
      const result = await call<Result>(path + suffix, request);
      if (result) {
        setLoad({ state: "ready", value: result });
        setStep("reading");
      }
    });
  }

  return (
    <SafeAreaView style={shared.page}>
      <LoadNotice load={load} gone={t("result.gone")} onRetry={reload} />
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={shared.pageContent} keyboardShouldPersistTaps="handled">
          <Details result={load.value} />
          {step === "changing" && (
            <ResultForm
              unit={load.value.unit}
              comparisonRequested={load.value.comparison_requested}
              result={load.value}
              busy={busy}
              onSubmit={(entry: ResultEntry) => act("", { method: "PATCH", body: entry })}
              onCancel={() => setStep("reading")}
            />
          )}
          {step === "signing" && (
            <Signing
              result={load.value}
              busy={busy}
              onSign={(acknowledged) =>
                act("/sign", {
                  method: "POST",
                  body: { confirmed: true, ...(acknowledged ? { warnings_acknowledged: true } : {}) },
                })
              }
              onCancel={() => setStep("reading")}
            />
          )}
          {step === "rejecting" && (
            <Rejecting
              busy={busy}
              onReject={(reason) => act("/reject", { method: "POST", body: { reason } })}
              onCancel={() => setStep("reading")}
            />
          )}
          {step === "reading" && <Actions result={load.value} onStep={setStep} />}
          <ActionProblem problem={problem?.load ?? null} gone={t("result.gone")} onRetry={() => problem?.retry()} />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function Details({ result }: Readonly<{ result: Result }>) {
  const t = useT();
  const { language } = useSession();
  return (
    <>
      <Text style={shared.title}>{`${result.code} – ${result.parameter}`}</Text>
      <Facts
        facts={[
          ["result.result", result.value_display],
          ["result.conclusion", result.conclusion_label],
          ["result.limit", result.limit],
          ["result.status", result.status_label],
          ["result.enteredBy", result.entered_by],
          ["result.enteredAt", result.entered_at ? formatMoment(result.entered_at, language) : ""],
          ["result.rejectionReason", result.rejection_reason],
        ]}
      />
      {result.warnings.length > 0 && (
        <View style={styles.warning} accessibilityRole="alert">
          <Text style={shared.label}>{t("result.warnings")}</Text>
          {result.warnings.map((warning) => (
            <Text key={warning} style={styles.warningText}>
              {warning}
            </Text>
          ))}
        </View>
      )}
    </>
  );
}

function Actions({ result, onStep }: Readonly<{ result: Result; onStep: (step: Step) => void }>) {
  const t = useT();
  const { edit, sign, reject } = result.actions;
  if (!edit && !sign && !reject) {
    return (
      <Text style={shared.detail} testID="result-read-only">
        {t("result.readOnly")}
      </Text>
    );
  }
  return (
    <>
      {sign && (
        <Button label={t(result.status === "none" ? "result.send" : "result.approve")} onPress={() => onStep("signing")} primary testID="result-send" />
      )}
      {edit && (
        <Button label={t("result.change")} onPress={() => onStep("changing")} />
      )}
      {reject && (
        <Button label={t("result.reject")} onPress={() => onStep("rejecting")} />
      )}
    </>
  );
}

/** The confirmation step of a signature: what signing does, and the person's acknowledgement of the warnings of a
 * draft they send. */
function Signing({
  result,
  busy,
  onSign,
  onCancel,
}: Readonly<{ result: Result; busy: boolean; onSign: (acknowledged: boolean) => void; onCancel: () => void }>) {
  const t = useT();
  const sending = result.status === "none";
  const warned = sending && result.warnings.length > 0;
  const [acknowledged, setAcknowledged] = useState(false);
  const ready = !busy && (!warned || acknowledged);
  return (
    <View style={shared.section}>
      <Text style={shared.text}>
        {t(sending ? "result.confirmSend" : "result.confirmApprove", { code: result.code, parameter: result.parameter })}
      </Text>
      {warned && (
        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: acknowledged }}
          style={[styles.acknowledgement, acknowledged && styles.acknowledged]}
          testID="result-acknowledge"
          onPress={() => setAcknowledged(!acknowledged)}
        >
          <Text style={shared.label}>{t("result.acknowledge")}</Text>
        </Pressable>
      )}
      <Button label={t("result.sign")} onPress={() => onSign(warned)} primary disabled={!ready} testID="result-sign" />
      <Button label={t("result.cancel")} onPress={onCancel} />
    </View>
  );
}

function Rejecting({
  busy,
  onReject,
  onCancel,
}: Readonly<{ busy: boolean; onReject: (reason: string) => void; onCancel: () => void }>) {
  const t = useT();
  const [reason, setReason] = useState("");
  return (
    <View style={shared.section}>
      <Text style={shared.label}>{t("result.reason")}</Text>
      <TextInput
        accessibilityLabel={t("result.reason")}
        style={[shared.input, styles.reason]}
        value={reason}
        onChangeText={setReason}
        multiline
      />
      <Button label={t("result.confirmReject")} onPress={() => onReject(reason)} primary disabled={busy} />
      <Button label={t("result.cancel")} onPress={onCancel} />
    </View>
  );
}

const styles = StyleSheet.create({
  warning: { gap: 4, padding: 12, borderRadius: 8, backgroundColor: "#fff4e5" },
  warningText: { fontSize: 14, color: "#663c00" },
  acknowledgement: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 12 },
  acknowledged: { borderColor: colors.primary, borderWidth: 2 },
  reason: { minHeight: 80, textAlignVertical: "top" },
});

import { useLocalSearchParams } from "expo-router";
import { useState, type ReactNode } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { Call, Result } from "../../api";
import type { Translate } from "../../i18n";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, layout, radius, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { ActionBar, type BarAction } from "../shared/ActionBar";
import { BottomSheet } from "../shared/BottomSheet";
import { Button } from "../shared/Button";
import { Facts } from "../shared/Facts";
import { Icon } from "../shared/Icon";
import { RecordHead } from "../shared/RecordHead";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";
import { Fact } from "../tasks/TaskRow";
import { formatMoment } from "../tasks/taskText";
import { ResultForm, type ResultEntry } from "./ResultForm";
import { resultTone } from "./resultText";

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

  const result = load.state === "ready" ? load.value : null;
  const failure = (
    <ActionProblem problem={problem?.load ?? null} gone={t("result.gone")} onRetry={() => problem?.retry()} />
  );
  return (
    <Screen
      title={result?.code ?? t("result.result")}
      footer={result && step === "reading" && <ActionBar actions={actions(result, setStep, t)}>{failure}</ActionBar>}
    >
      <LoadNotice load={load} gone={t("result.gone")} onRetry={reload} />
      {result && (
        <>
          <Details result={result} />
          {step === "changing" && (
            <Sheet title={t("result.change")}>
              <ResultForm
                unit={result.unit}
                comparisonRequested={result.comparison_requested}
                result={result}
                busy={busy}
                onSubmit={(entry: ResultEntry) => act("", { method: "PATCH", body: entry })}
                onCancel={() => setStep("reading")}
              />
              {failure}
            </Sheet>
          )}
          {step === "reading" && !result.actions.edit && !result.actions.sign && !result.actions.reject && (
            <View style={styles.readOnly}>
              <Icon name="lock-outline" size={18} />
              <Text style={[shared.detail, styles.readOnlyText]} testID="result-read-only">
                {t("result.readOnly")}
              </Text>
            </View>
          )}
          <Signing
            visible={step === "signing"}
            result={result}
            busy={busy}
            failure={failure}
            onSign={(acknowledged) =>
              act("/sign", {
                method: "POST",
                body: { confirmed: true, ...(acknowledged ? { warnings_acknowledged: true } : {}) },
              })
            }
            onCancel={() => setStep("reading")}
          />
          <Rejecting
            visible={step === "rejecting"}
            busy={busy}
            failure={failure}
            onReject={(reason) => act("/reject", { method: "POST", body: { reason } })}
            onCancel={() => setStep("reading")}
          />
        </>
      )}
    </Screen>
  );
}

/** The actions on the result: sending a draft moves it forward, approving accepts it, rejecting refuses it. */
function actions(result: Result, onStep: (step: Step) => void, t: Translate): BarAction[] {
  const { edit, sign, reject } = result.actions;
  const sending = result.status === "none";
  const listed: BarAction[] = [];
  if (sign) {
    listed.push({
      key: "sign",
      label: t(sending ? "result.send" : "result.approve"),
      tone: sending ? "primary" : "success",
      icon: sending ? "send-outline" : "check-decagram-outline",
      testID: "result-send",
      onPress: () => onStep("signing"),
    });
  }
  if (edit) {
    listed.push({ key: "edit", label: t("result.change"), icon: "pencil-outline", onPress: () => onStep("changing") });
  }
  if (reject) {
    listed.push({
      key: "reject",
      label: t("result.reject"),
      tone: "danger",
      icon: "close-circle-outline",
      testID: "result-reject",
      onPress: () => onStep("rejecting"),
    });
  }
  return listed;
}

function Details({ result }: Readonly<{ result: Result }>) {
  const t = useT();
  const { language } = useSession();
  return (
    <>
      <RecordHead
        title={`${result.code} – ${result.parameter}`}
        status={{ label: result.status_label, tone: resultTone(result.status) }}
      >
        {!!result.entered_by && <Fact icon="account-outline" text={result.entered_by} />}
      </RecordHead>
      {result.warnings.length > 0 && (
        <View style={styles.warning} accessibilityRole="alert">
          <View style={styles.warningHead}>
            <Icon name="alert-outline" color={colors.warning} />
            <Text style={shared.label}>{t("result.warnings")}</Text>
          </View>
          {result.warnings.map((warning) => (
            <Text key={warning} style={shared.text}>
              {warning}
            </Text>
          ))}
        </View>
      )}
      <Sheet title={t("result.result")}>
        <Text style={styles.value}>{result.value_display}</Text>
        <Facts
          facts={[
            ["result.conclusion", result.conclusion_label],
            ["result.limit", result.limit],
            ["result.enteredBy", result.entered_by],
            ["result.enteredAt", result.entered_at ? formatMoment(result.entered_at, language) : ""],
            ["result.rejectionReason", result.rejection_reason],
          ]}
        />
      </Sheet>
    </>
  );
}

/** The confirmation step of a signature: what signing does, and the person's acknowledgement of the warnings of a
 * draft they send. */
function Signing({
  visible,
  result,
  busy,
  failure,
  onSign,
  onCancel,
}: Readonly<{
  visible: boolean;
  result: Result;
  busy: boolean;
  failure: ReactNode;
  onSign: (acknowledged: boolean) => void;
  onCancel: () => void;
}>) {
  const t = useT();
  const sending = result.status === "none";
  const warned = sending && result.warnings.length > 0;
  const [acknowledged, setAcknowledged] = useState(false);
  const ready = !busy && (!warned || acknowledged);
  return (
    <BottomSheet visible={visible} title={t(sending ? "result.send" : "result.approve")} onClose={onCancel}>
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
          <Icon
            name={acknowledged ? "checkbox-marked" : "checkbox-blank-outline"}
            size={24}
            color={acknowledged ? colors.primary : colors.borderControl}
          />
          <Text style={[shared.label, styles.acknowledgementText]}>{t("result.acknowledge")}</Text>
        </Pressable>
      )}
      {failure}
      <Button label={t("result.sign")} icon="draw-pen" onPress={() => onSign(warned)} tone="success" disabled={!ready} testID="result-sign" />
      <Button label={t("result.cancel")} onPress={onCancel} />
    </BottomSheet>
  );
}

function Rejecting({
  visible,
  busy,
  failure,
  onReject,
  onCancel,
}: Readonly<{
  visible: boolean;
  busy: boolean;
  failure: ReactNode;
  onReject: (reason: string) => void;
  onCancel: () => void;
}>) {
  const t = useT();
  const [reason, setReason] = useState("");
  return (
    <BottomSheet visible={visible} title={t("result.confirmReject")} onClose={onCancel}>
      <View style={styles.field}>
        <Text style={shared.label}>{t("result.reason")}</Text>
        <TextInput
          accessibilityLabel={t("result.reason")}
          style={[shared.input, shared.multiline]}
          value={reason}
          onChangeText={setReason}
          multiline
        />
      </View>
      {failure}
      <Button
        label={t("result.confirmReject")}
        icon="close-circle-outline"
        onPress={() => onReject(reason)}
        tone="danger"
        disabled={busy}
        testID="result-confirm-reject"
      />
      <Button label={t("result.cancel")} onPress={onCancel} />
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  readOnly: { flexDirection: "row", gap: space.sm, alignItems: "center" },
  readOnlyText: { flex: 1 },
  warning: {
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.warning,
    backgroundColor: colors.warningSoft,
  },
  warningHead: { flexDirection: "row", alignItems: "center", gap: space.sm },
  value: { fontSize: 26, fontWeight: "700", color: colors.text },
  field: { gap: 6 },
  acknowledgement: {
    minHeight: layout.touch,
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: space.md,
  },
  acknowledged: { borderColor: colors.primary, backgroundColor: colors.primaryLight },
  acknowledgementText: { flex: 1 },
});

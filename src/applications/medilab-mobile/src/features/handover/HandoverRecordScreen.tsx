import { useLocalSearchParams } from "expo-router";
import { memo, useCallback, useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import type { HandoverRecord } from "../../api";
import { useReloadOnReturn } from "../../focus";
import { useLoad } from "../../load";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, radius, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { ActionBar } from "../shared/ActionBar";
import { BottomSheet } from "../shared/BottomSheet";
import { Button } from "../shared/Button";
import { Facts } from "../shared/Facts";
import { Icon } from "../shared/Icon";
import { RecordHead } from "../shared/RecordHead";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";
import { UnsentCard } from "../shared/UnsentCard";
import { formatMoment } from "../tasks/taskText";
import { handoverStatus } from "./handoverText";
import { discardSignature, keepSignature, sendSignature, unsentSignature } from "./signatureQueue";
import { SignaturePad } from "./SignaturePad";
import { signaturePng, type Stroke } from "./signaturePng";

type Step = "reading" | "signing" | "confirming";

/** A handover record the customer reads and signs by hand on the phone. The signature is kept on the phone, then sent
 * from the confirmation step; one MediLab did not get stays on the phone to send again or discard. A signed record is
 * only shown. */
export function HandoverRecordScreen() {
  const t = useT();
  const { call } = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  const recordId = Number(id);
  const { load, setLoad, reload } = useRecord<HandoverRecord>(`/handover-records/${encodeURIComponent(id)}`);
  const { load: kept, reload: reloadKept } = useLoad(useCallback(() => unsentSignature(recordId), [recordId]));
  useReloadOnReturn(reloadKept);
  const { problem, busy, run } = useAction();
  const [step, setStep] = useState<Step>("reading");
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [pad, setPad] = useState({ width: 0, height: 0 });
  const signed = load.state === "ready" && load.value.status === "signed";

  // A signature kept for a record that is signed now, on this phone or another, has nothing left to do.
  useEffect(() => {
    if (signed && kept.state === "ready" && kept.value) {
      discardSignature(recordId);
      void reloadKept();
    }
  }, [signed, kept, reloadKept, recordId]);

  function settle(action: () => Promise<HandoverRecord | null | void>) {
    return run(async () => {
      try {
        const record = await action();
        if (record) {
          setLoad({ state: "ready", value: record });
        }
      } finally {
        await reloadKept();
      }
    });
  }

  async function confirm() {
    const signature = await keepSignature(recordId, signaturePng(strokes, pad.width, pad.height));
    setStrokes([]);
    setStep("reading");
    await settle(() => sendSignature(signature, call));
  }

  const record = load.state === "ready" ? load.value : null;
  const waiting = kept.state === "ready" && !signed ? kept.value : null;
  const offersSigning = step === "reading" && !!record?.can_sign && !waiting;
  return (
    <Screen
      title={record?.code ?? t("handover.title")}
      scrollEnabled={step !== "signing"}
      footer={
        record && (
          <ActionBar
            actions={
              offersSigning
                ? [
                    {
                      key: "sign",
                      label: t("handover.sign"),
                      tone: "primary",
                      icon: "draw-pen",
                      testID: "handover-sign",
                      onPress: () => setStep("signing"),
                    },
                  ]
                : []
            }
          >
            <ActionProblem problem={problem?.load ?? null} gone={t("handover.gone")} onRetry={() => problem?.retry()} />
          </ActionBar>
        )
      }
    >
      <LoadNotice load={load} gone={t("handover.gone")} onRetry={reload} />
      {record && (
        <>
          {/* The signature box replaces the record, so that it and its buttons fit the screen that stops scrolling. */}
          {step !== "signing" && <Details record={record} />}
          {step === "reading" && signed && (
            <View style={styles.readOnly}>
              <Icon name="lock-outline" size={18} />
              <Text style={[shared.detail, styles.readOnlyText]} testID="handover-read-only">
                {t("handover.readOnly")}
              </Text>
            </View>
          )}
          {waiting && (
            <UnsentCard
              label={t("handover.unsent")}
              send={t("handover.send")}
              discard={t("handover.discard")}
              busy={busy}
              onSend={() => settle(() => sendSignature(waiting, call))}
              onDiscard={() => settle(async () => discardSignature(recordId))}
              testID="unsent-signature"
            />
          )}
          {step === "signing" && (
            <Sheet title={t("handover.pad")}>
              <Text style={shared.text}>{t("handover.padHint")}</Text>
              <SignaturePad label={t("handover.pad")} strokes={strokes} onDraw={setStrokes} onLayout={setPad} />
              <Button
                label={t("handover.next")}
                icon="arrow-right"
                onPress={() => setStep("confirming")}
                tone="primary"
                disabled={!strokes.length}
                testID="handover-next"
              />
              <View style={styles.row}>
                <View style={styles.slot}>
                  <Button label={t("handover.clear")} icon="eraser" onPress={() => setStrokes([])} disabled={!strokes.length} />
                </View>
                <View style={styles.slot}>
                  <Button label={t("handover.cancel")} onPress={() => setStep("reading")} />
                </View>
              </View>
            </Sheet>
          )}
          <BottomSheet visible={step === "confirming"} title={t("handover.confirmSign")} onClose={() => setStep("signing")}>
            <SignaturePad label={t("handover.pad")} strokes={strokes} />
            <Text style={shared.text}>{t("handover.confirm", { name: record.handed_over_by, code: record.code })}</Text>
            <Button
              label={t("handover.confirmSign")}
              icon="check"
              onPress={confirm}
              tone="success"
              disabled={busy}
              testID="handover-confirm"
            />
            <Button label={t("handover.clear")} icon="eraser" onPress={() => setStep("signing")} />
          </BottomSheet>
        </>
      )}
    </Screen>
  );
}

const Details = memo(function Details({ record }: Readonly<{ record: HandoverRecord }>) {
  const t = useT();
  const { language } = useSession();
  const status = handoverStatus(record.status);
  return (
    <>
      <RecordHead title={record.code} status={{ label: t(status.label), tone: status.tone }} />
      <Sheet title={t("task.info")}>
        <Facts
          facts={[
            ["handover.request", record.request],
            ["handover.handedOverBy", record.handed_over_by],
            ["handover.handedOverAt", formatMoment(record.handed_over_at, language)],
            ["handover.receivedBy", record.received_by],
            ["handover.signedAt", record.signed_at ? formatMoment(record.signed_at, language) : ""],
            ["handover.signedDevice", record.signed_device],
          ]}
        />
      </Sheet>
      <Sheet title={t("handover.samples")}>
        {record.samples.map((sample, index) => (
          <View key={sample.code} style={[styles.sample, index > 0 && styles.divided]}>
            <Text style={shared.label}>{[sample.code, sample.customer_sample_name].filter(Boolean).join(" – ")}</Text>
            <Text style={shared.text}>
              {[sample.sample_type, sample.quantity, sample.condition].filter(Boolean).join(" · ")}
            </Text>
            <Text style={shared.detail}>
              {t("handover.counts", { actual: sample.actual_count, expected: sample.expected_count || sample.actual_count })}
            </Text>
            {!!sample.excess_material && (
              <Text style={shared.detail}>{t("handover.excess", { excess: sample.excess_material })}</Text>
            )}
            {!!sample.condition_note && <Text style={shared.detail}>{sample.condition_note}</Text>}
          </View>
        ))}
      </Sheet>
    </>
  );
});

const styles = StyleSheet.create({
  readOnly: { flexDirection: "row", gap: space.sm, alignItems: "center" },
  readOnlyText: { flex: 1 },
  row: { flexDirection: "row", gap: space.sm },
  slot: { flex: 1 },
  sample: { gap: 2, paddingVertical: space.xs },
  divided: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    paddingTop: space.md,
    borderRadius: radius.sm,
  },
});

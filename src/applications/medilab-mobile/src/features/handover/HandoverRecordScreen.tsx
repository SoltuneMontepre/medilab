import { useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { HandoverRecord } from "../../api";
import { useReloadOnReturn } from "../../focus";
import { useLoad } from "../../load";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { Button } from "../shared/Button";
import { Facts } from "../shared/Facts";
import { formatMoment } from "../tasks/taskText";
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
  const unsent = useLoad(useCallback(() => unsentSignature(recordId), [recordId]));
  useReloadOnReturn(unsent.reload);
  const { problem, busy, run } = useAction();
  const [step, setStep] = useState<Step>("reading");
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [pad, setPad] = useState({ width: 0, height: 0 });
  const signed = load.state === "ready" && load.value.status === "signed";

  // A signature kept for a record that is signed now, on this phone or another, has nothing left to do.
  const { load: kept, reload: reloadKept } = unsent;
  useEffect(() => {
    if (signed && kept.state === "ready" && kept.value) {
      discardSignature(recordId);
      void reloadKept();
    }
  }, [signed, kept, reloadKept, recordId]);

  function send(kept: Parameters<typeof sendSignature>[0]) {
    return run(async () => {
      try {
        const record = await sendSignature(kept, call);
        if (record) {
          setLoad({ state: "ready", value: record });
          setStep("reading");
        }
      } finally {
        await unsent.reload();
      }
    });
  }

  async function confirm() {
    const kept = await keepSignature(recordId, signaturePng(strokes, pad.width, pad.height));
    setStrokes([]);
    setStep("reading");
    await send(kept);
  }

  const waiting = unsent.load.state === "ready" && !signed ? unsent.load.value : null;
  return (
    <SafeAreaView style={shared.page}>
      <LoadNotice load={load} gone={t("handover.gone")} onRetry={reload} />
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={shared.pageContent} scrollEnabled={step !== "signing"}>
          <Details record={load.value} />
          {step === "reading" && signed && (
            <Text style={shared.detail} testID="handover-read-only">
              {t("handover.readOnly")}
            </Text>
          )}
          {waiting && (
            <View style={shared.card} testID="unsent-signature">
              <Text style={shared.label}>{t("handover.unsent")}</Text>
              <Button label={t("handover.send")} onPress={() => send(waiting)} primary disabled={busy} />
              <Button
                label={t("handover.discard")}
                onPress={() => run(async () => {
                  discardSignature(recordId);
                  await unsent.reload();
                })}
                disabled={busy}
              />
            </View>
          )}
          {step === "reading" && load.value.can_sign && !waiting && (
            <Button label={t("handover.sign")} onPress={() => setStep("signing")} primary testID="handover-sign" />
          )}
          {step === "signing" && (
            <View style={shared.section}>
              <Text style={shared.text}>{t("handover.padHint")}</Text>
              <SignaturePad label={t("handover.pad")} strokes={strokes} onDraw={setStrokes} onLayout={setPad} />
              <Button label={t("handover.next")} onPress={() => setStep("confirming")} primary disabled={!strokes.length} />
              <Button label={t("handover.clear")} onPress={() => setStrokes([])} disabled={!strokes.length} />
              <Button label={t("handover.cancel")} onPress={() => setStep("reading")} />
            </View>
          )}
          {step === "confirming" && (
            <View style={shared.section}>
              <SignaturePad label={t("handover.pad")} strokes={strokes} />
              <Text style={shared.text}>
                {t("handover.confirm", { name: load.value.handed_over_by, code: load.value.code })}
              </Text>
              <Button label={t("handover.confirmSign")} onPress={confirm} primary disabled={busy} testID="handover-confirm" />
              <Button label={t("handover.clear")} onPress={() => setStep("signing")} />
            </View>
          )}
          <ActionProblem problem={problem?.load ?? null} gone={t("handover.gone")} onRetry={() => problem?.retry()} />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function Details({ record }: Readonly<{ record: HandoverRecord }>) {
  const t = useT();
  const { language } = useSession();
  return (
    <>
      <Text style={shared.title}>{record.code}</Text>
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
      <Text accessibilityRole="header" style={shared.heading}>
        {t("handover.samples")}
      </Text>
      {record.samples.map((sample) => (
        <View key={sample.code} style={shared.card}>
          <Text style={shared.label}>
            {[sample.code, sample.customer_sample_name].filter(Boolean).join(" – ")}
          </Text>
          <Text style={shared.text}>{[sample.sample_type, sample.quantity, sample.condition].filter(Boolean).join(" · ")}</Text>
          <Text style={shared.detail}>
            {t("handover.counts", { actual: sample.actual_count, expected: sample.expected_count || sample.actual_count })}
          </Text>
          {!!sample.excess_material && (
            <Text style={shared.detail}>{t("handover.excess", { excess: sample.excess_material })}</Text>
          )}
          {!!sample.condition_note && <Text style={shared.detail}>{sample.condition_note}</Text>}
        </View>
      ))}
    </>
  );
}

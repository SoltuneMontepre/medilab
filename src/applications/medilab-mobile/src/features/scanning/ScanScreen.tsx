import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useRef, useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import type { Sample } from "../../api";
import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, radius, space } from "../../theme";
import { Unreachable } from "../connection/Unreachable";
import { samplePath } from "../documents/documentPath";
import { Button } from "../shared/Button";
import { CameraPermission } from "../shared/CameraPermission";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";

/** Reads a sample's label with the camera, or takes its lab code typed when the label cannot be read, and opens the
 * sample as the person may see it. */
export function ScanScreen() {
  const t = useT();
  const { call } = useSession();
  const [permission, requestPermission] = useCameraPermissions();
  const [focused, setFocused] = useState(false);
  const [typed, setTyped] = useState("");
  const [problem, setProblem] = useState<{ code: string; load: Load<never> } | null>(null);
  const [missing, setMissing] = useState(false);
  const looking = useRef(false);
  // A label stays in front of the camera after it is read: the camera opens it once, until the screen shows again.
  const scanned = useRef<string | null>(null);

  // The camera runs only while the tab is shown, so it neither scans nor holds the camera behind the sample.
  useFocusEffect(
    useCallback(() => {
      scanned.current = null;
      setFocused(true);
      return () => setFocused(false);
    }, []),
  );

  const open = useCallback(
    async (code: string) => {
      const label = code.trim();
      setMissing(!label);
      if (!label || looking.current) {
        return;
      }
      looking.current = true;
      setProblem(null);
      try {
        const sample = await call<Sample>(`/samples/lookup?code=${encodeURIComponent(label)}`);
        if (sample) {
          router.push(samplePath(sample.id));
        }
      } catch (error) {
        setProblem({ code: label, load: failed(error) });
      } finally {
        looking.current = false;
      }
    },
    [call],
  );

  function scan({ data }: BarcodeScanningResult) {
    if (data !== scanned.current) {
      scanned.current = data;
      void open(data);
    }
  }

  return (
    <Screen title={t("scan.title")} tab>
      {permission?.granted && (
        <View style={styles.camera}>
          {focused && (
            <CameraView
              style={StyleSheet.absoluteFill}
              facing="back"
              barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
              onBarcodeScanned={scan}
            />
          )}
          <View pointerEvents="none" style={styles.frame} />
        </View>
      )}
      {permission?.granted && <Text style={[shared.detail, styles.hint]}>{t("scan.hint")}</Text>}
      <CameraPermission permission={permission} needed={t("scan.cameraNeeded")} onAllow={requestPermission} />
      <Sheet title={t("scan.code")}>
        <TextInput
          accessibilityLabel={t("scan.code")}
          testID="scan-code"
          placeholder={t("scan.code")}
          placeholderTextColor={colors.textMuted}
          autoCapitalize="characters"
          autoCorrect={false}
          returnKeyType="go"
          style={shared.input}
          value={typed}
          onChangeText={setTyped}
          onSubmitEditing={() => open(typed)}
        />
        {missing && <Text style={shared.error}>{t("scan.missing")}</Text>}
        <Button label={t("scan.open")} icon="magnify" tone="primary" testID="scan-open" onPress={() => open(typed)} />
      </Sheet>
      {problem?.load.state === "unreachable" && <Unreachable onRetry={() => open(problem.code)} />}
      {problem?.load.state === "gone" && (
        <Text accessibilityRole="alert" style={shared.error}>
          {t("scan.notFound", { code: problem.code })}
        </Text>
      )}
      {problem?.load.state === "refused" && (
        <Text accessibilityRole="alert" style={shared.error}>
          {problem.load.message}
        </Text>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  camera: {
    aspectRatio: 1,
    borderRadius: radius.lg,
    overflow: "hidden",
    backgroundColor: colors.secondary,
    alignItems: "center",
    justifyContent: "center",
  },
  frame: {
    width: "62%",
    aspectRatio: 1,
    borderRadius: radius.lg,
    borderWidth: 3,
    borderColor: colors.textOnPrimary,
    opacity: 0.85,
  },
  hint: { textAlign: "center", marginTop: -space.xs },
});

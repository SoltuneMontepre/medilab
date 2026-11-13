import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { Sample } from "../../api";
import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { Unreachable } from "../connection/Unreachable";
import { samplePath } from "../documents/documentPath";

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

  // The camera runs only while the screen is shown, so it neither scans nor holds the camera behind the sample.
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
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={shared.title}>{t("scan.title")}</Text>
        {permission?.granted && focused && (
          <View style={styles.camera}>
            <CameraView
              style={StyleSheet.absoluteFill}
              facing="back"
              barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
              onBarcodeScanned={scan}
            />
          </View>
        )}
        {permission?.granted && <Text style={shared.detail}>{t("scan.hint")}</Text>}
        {permission && !permission.granted && (
          <>
            <Text style={shared.detail}>{t("scan.cameraNeeded")}</Text>
            {permission.canAskAgain && (
              <Pressable accessibilityRole="button" style={shared.secondaryButton} onPress={requestPermission}>
                <Text style={shared.secondaryButtonText}>{t("scan.allowCamera")}</Text>
              </Pressable>
            )}
          </>
        )}
        <TextInput
          accessibilityLabel={t("scan.code")}
          placeholder={t("scan.code")}
          autoCapitalize="characters"
          autoCorrect={false}
          returnKeyType="go"
          style={shared.input}
          value={typed}
          onChangeText={setTyped}
          onSubmitEditing={() => open(typed)}
        />
        {missing && <Text style={shared.error}>{t("scan.missing")}</Text>}
        <Pressable accessibilityRole="button" style={shared.primaryButton} onPress={() => open(typed)}>
          <Text style={shared.primaryButtonText}>{t("scan.open")}</Text>
        </Pressable>
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
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 24, gap: 16 },
  camera: { aspectRatio: 1, borderRadius: 8, overflow: "hidden" },
});

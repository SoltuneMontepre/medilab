import { CameraView, useCameraPermissions } from "expo-camera";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useRef, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { Button } from "../shared/Button";
import { CameraPermission } from "../shared/CameraPermission";
import { keepPhoto, sendPhoto } from "./photoQueue";

// A photo of a sample is for people, not a print: a smaller file sends faster from the field.
const PHOTO_QUALITY = 0.7;

/** Photographs a sample when it is collected or received. The photo is kept on the phone first, then sent; one MediLab
 * did not get stays on the phone, and the sample's screen sends it again or discards it. */
export function PhotoScreen() {
  const t = useT();
  const { call } = useSession();
  const { id, code } = useLocalSearchParams<{ id: string; code: string }>();
  const [permission, requestPermission] = useCameraPermissions();
  const [focused, setFocused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Load<never> | null>(null);
  const camera = useRef<CameraView>(null);

  // The camera runs only while the screen is shown.
  useFocusEffect(
    useCallback(() => {
      setFocused(true);
      return () => setFocused(false);
    }, []),
  );

  async function shoot() {
    const picture = await camera.current?.takePictureAsync({ quality: PHOTO_QUALITY });
    if (!picture) {
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const photo = await keepPhoto(Number(id), code, picture.uri);
      await sendPhoto(photo, call);
      router.back();
    } catch (error) {
      setProblem(failed(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={shared.page}>
      <ScrollView contentContainerStyle={shared.pageContent}>
        <Text style={shared.title}>{t("photo.title", { code })}</Text>
        {permission?.granted && focused && !problem && (
          <View style={styles.camera}>
            <CameraView ref={camera} style={StyleSheet.absoluteFill} facing="back" />
          </View>
        )}
        <CameraPermission permission={permission} needed={t("photo.cameraNeeded")} onAllow={requestPermission} />
        {permission?.granted && !problem && (
          <Button label={t("photo.shutter")} onPress={shoot} primary disabled={busy} testID="photo-shutter" />
        )}
        {problem && (
          <>
            <Text style={shared.label}>{t("photo.kept")}</Text>
            {problem.state !== "unreachable" && <Refusal problem={problem} />}
            <Button label={t("photo.back")} onPress={() => router.back()} testID="photo-back" />
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

/** Why MediLab did not take the photo: its refusal, or the sample gone. Without a connection the photo simply waits. */
function Refusal({ problem }: Readonly<{ problem: Load<never> }>) {
  const t = useT();
  return (
    <Text accessibilityRole="alert" style={shared.error}>
      {problem.state === "refused" ? problem.message : t("sample.gone")}
    </Text>
  );
}

const styles = StyleSheet.create({
  camera: { aspectRatio: 3 / 4, borderRadius: 8, overflow: "hidden" },
});

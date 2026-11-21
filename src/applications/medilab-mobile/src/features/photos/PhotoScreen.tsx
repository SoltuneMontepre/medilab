import { CameraView, useCameraPermissions } from "expo-camera";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, radius, space } from "../../theme";
import { Button } from "../shared/Button";
import { CameraPermission } from "../shared/CameraPermission";
import { Screen } from "../shared/Screen";
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
    <Screen title={t("photo.title", { code })} bell={false}>
      {permission?.granted && focused && !problem && (
        <View style={styles.camera}>
          <CameraView ref={camera} style={StyleSheet.absoluteFill} facing="back" />
        </View>
      )}
      <CameraPermission permission={permission} needed={t("photo.cameraNeeded")} onAllow={requestPermission} />
      {permission?.granted && !problem && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("photo.shutter")}
          accessibilityState={{ disabled: busy }}
          disabled={busy}
          testID="photo-shutter"
          style={({ pressed }) => [styles.shutter, (pressed || busy) && styles.pressed]}
          onPress={shoot}
        >
          <View style={styles.shutterInner} />
        </Pressable>
      )}
      {problem && (
        <View style={styles.kept}>
          <Text style={shared.label}>{t("photo.kept")}</Text>
          {problem.state !== "unreachable" && <Refusal problem={problem} />}
          <Button label={t("photo.back")} icon="arrow-left" onPress={() => router.back()} testID="photo-back" />
        </View>
      )}
    </Screen>
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
  camera: { aspectRatio: 3 / 4, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.secondary },
  shutter: {
    alignSelf: "center",
    width: 76,
    height: 76,
    borderRadius: radius.pill,
    borderWidth: 4,
    borderColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  shutterInner: { width: 58, height: 58, borderRadius: radius.pill, backgroundColor: colors.primary },
  pressed: { opacity: 0.6 },
  kept: { gap: space.md },
});

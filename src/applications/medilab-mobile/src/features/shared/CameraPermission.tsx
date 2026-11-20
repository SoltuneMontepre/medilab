import type { PermissionResponse } from "expo-camera";
import { StyleSheet, Text, View } from "react-native";

import { useT } from "../../locale";
import { styles as shared } from "../../styles";
import { colors, space } from "../../theme";
import { Button } from "./Button";
import { Icon } from "./Icon";

/** Why the screen needs the camera the person has not allowed, and the way to allow it while the phone still asks. */
export function CameraPermission({
  permission,
  needed,
  onAllow,
}: Readonly<{ permission: PermissionResponse | null; needed: string; onAllow: () => void }>) {
  const t = useT();
  if (!permission || permission.granted) {
    return null;
  }
  return (
    <View style={styles.box}>
      <Icon name="camera-off-outline" size={36} color={colors.textMuted} />
      <Text style={[shared.text, styles.text]}>{needed}</Text>
      {permission.canAskAgain && (
        <Button label={t("scan.allowCamera")} icon="camera" tone="primary" onPress={onAllow} testID="allow-camera" />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { alignItems: "center", gap: space.md, paddingVertical: space.lg },
  text: { textAlign: "center", color: colors.textSecondary },
});

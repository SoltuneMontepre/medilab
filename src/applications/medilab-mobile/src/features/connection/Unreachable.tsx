import { Pressable, StyleSheet, Text, View } from "react-native";

import { useT } from "../../locale";
import { styles as shared } from "../../styles";

/** The state every screen shows when MediLab cannot be reached: nothing was changed, and the person tries again. */
export function Unreachable({ onRetry }: Readonly<{ onRetry: () => void }>) {
  const t = useT();
  return (
    <View style={styles.box} accessibilityRole="alert">
      <Text style={styles.message}>{t("unreachable.message")}</Text>
      <Pressable accessibilityRole="button" style={shared.secondaryButton} onPress={onRetry}>
        <Text style={shared.secondaryButtonText}>{t("unreachable.retry")}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { gap: 12, padding: 16, borderRadius: 8, backgroundColor: "#fff4e5" },
  message: { fontSize: 15, color: "#663c00" },
});

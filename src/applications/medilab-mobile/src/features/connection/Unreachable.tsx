import { StyleSheet, Text, View } from "react-native";

import { useT } from "../../locale";
import { colors, radius, space } from "../../theme";
import { styles as shared } from "../../styles";
import { Button } from "../shared/Button";
import { Icon } from "../shared/Icon";

/** The state every screen shows when MediLab cannot be reached: nothing was changed, and the person tries again. */
export function Unreachable({ onRetry }: Readonly<{ onRetry: () => void }>) {
  const t = useT();
  return (
    <View style={styles.box} accessibilityRole="alert">
      <View style={styles.head}>
        <Icon name="wifi-off" color={colors.warning} />
        <Text style={[shared.text, styles.message]}>{t("unreachable.message")}</Text>
      </View>
      <Button label={t("unreachable.retry")} icon="refresh" compact onPress={onRetry} />
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    gap: space.md,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.warning,
    backgroundColor: colors.warningSoft,
  },
  head: { flexDirection: "row", gap: space.sm },
  message: { flex: 1 },
});

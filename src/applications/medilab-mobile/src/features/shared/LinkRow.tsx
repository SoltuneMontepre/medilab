import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, layout, space } from "../../theme";
import { styles as shared } from "../../styles";
import { Icon, type IconName } from "./Icon";

/** A row that opens another screen or page: its icon, its label, what it holds now, and a chevron. */
export function LinkRow({
  icon,
  label,
  detail,
  onPress,
  testID,
}: Readonly<{ icon: IconName; label: string; detail?: string; onPress: () => void; testID?: string }>) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      testID={testID}
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
      onPress={onPress}
    >
      <Icon name={icon} size={22} color={colors.primary} />
      <View style={styles.text}>
        <Text style={shared.label}>{label}</Text>
        {!!detail && (
          <Text style={shared.detail} numberOfLines={1}>
            {detail}
          </Text>
        )}
      </View>
      <Icon name="chevron-right" size={22} color={colors.textMuted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { minHeight: layout.touch, flexDirection: "row", alignItems: "center", gap: space.md, paddingVertical: space.xs },
  pressed: { opacity: 0.6 },
  text: { flex: 1, gap: 2 },
});

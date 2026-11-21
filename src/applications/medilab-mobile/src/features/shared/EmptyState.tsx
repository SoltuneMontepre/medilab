import { StyleSheet, Text, View } from "react-native";

import { colors, space } from "../../theme";
import { styles as shared } from "../../styles";
import { Icon, type IconName } from "./Icon";

/** What an empty list says, under the icon of what it lists. */
export function EmptyState({ icon, text }: Readonly<{ icon: IconName; text: string }>) {
  return (
    <View style={styles.empty}>
      <Icon name={icon} size={44} color={colors.borderStrong} />
      <Text style={[shared.text, styles.text]}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  empty: { alignItems: "center", gap: space.md, paddingVertical: 40, paddingHorizontal: space.xl },
  text: { color: colors.textMuted, textAlign: "center" },
});

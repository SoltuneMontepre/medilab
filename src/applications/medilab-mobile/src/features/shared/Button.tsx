import { Pressable, StyleSheet, Text } from "react-native";

import { colors, fontSize, layout, radius, space } from "../../theme";
import { Icon, type IconName } from "./Icon";

/** What a button does, which gives its colour: moves the work forward, accepts or finishes, destroys or refuses, or
 * anything else. */
export type Tone = "primary" | "success" | "danger" | "secondary";

/** A button of the screen, coloured by what it does. A compact one sits on a row of a list. */
export function Button({
  label,
  onPress,
  tone = "secondary",
  icon,
  compact = false,
  disabled = false,
  testID,
}: Readonly<{
  label: string;
  onPress: () => void;
  tone?: Tone;
  icon?: IconName;
  compact?: boolean;
  disabled?: boolean;
  testID?: string;
}>) {
  const filled = tone !== "secondary";
  const ink = filled ? colors.textOnPrimary : colors.text;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      testID={testID}
      hitSlop={compact ? 6 : 0}
      style={({ pressed }) => [
        styles.button,
        compact && styles.compact,
        styles[tone],
        pressed && styles.pressed,
        disabled && styles.disabled,
      ]}
      onPress={onPress}
    >
      {icon && <Icon name={icon} size={compact ? 18 : 20} color={ink} />}
      <Text numberOfLines={1} style={[styles.label, compact && styles.compactLabel, { color: ink }]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: layout.touch,
    borderRadius: radius.md,
    borderWidth: 1,
    paddingHorizontal: space.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space.sm,
  },
  compact: { minHeight: 36, paddingHorizontal: space.md, borderRadius: radius.sm },
  primary: { backgroundColor: colors.primary, borderColor: colors.primary },
  success: { backgroundColor: colors.success, borderColor: colors.success },
  danger: { backgroundColor: colors.danger, borderColor: colors.danger },
  secondary: { backgroundColor: colors.surface, borderColor: colors.borderControl },
  pressed: { opacity: 0.85 },
  disabled: { opacity: 0.5 },
  label: { fontSize: fontSize.md, fontWeight: "600" },
  compactLabel: { fontSize: fontSize.base },
});

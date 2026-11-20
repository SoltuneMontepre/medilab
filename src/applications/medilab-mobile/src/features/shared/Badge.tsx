import { StyleSheet, Text, View } from "react-native";

import { colors, fontSize, radius, space } from "../../theme";

/** What a status means, which gives its colour: in progress, done, waiting for someone, refused or stopped, or
 * anything else. */
export type BadgeTone = "info" | "success" | "warning" | "danger" | "muted";

export const TONES: Record<BadgeTone, { background: string; dot: string; text: string }> = {
  info: { background: colors.accentSoft, dot: colors.accent, text: colors.primary },
  success: { background: colors.successSoft, dot: colors.success, text: colors.success },
  warning: { background: colors.warningSoft, dot: colors.warning, text: colors.text },
  danger: { background: colors.dangerSoft, dot: colors.danger, text: colors.danger },
  muted: { background: colors.secondaryLight, dot: colors.textMuted, text: colors.textSecondary },
};

/** A status beside the name of what it is about; its text says what the colour means. */
export function Badge({ label, tone }: Readonly<{ label: string; tone: BadgeTone }>) {
  const look = TONES[tone];
  return (
    <View style={[styles.badge, { backgroundColor: look.background }]}>
      <View style={[styles.dot, { backgroundColor: look.dot }]} />
      <Text numberOfLines={1} style={[styles.text, { color: look.text }]}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: 6,
    borderRadius: radius.pill,
    paddingHorizontal: 10,
    paddingVertical: space.xs,
  },
  dot: { width: 7, height: 7, borderRadius: 4 },
  text: { fontSize: fontSize.xs, fontWeight: "600" },
});

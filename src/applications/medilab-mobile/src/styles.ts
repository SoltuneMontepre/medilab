import { StyleSheet } from "react-native";

import { colors, fontSize, layout, letterSpacing, radius, space } from "./theme";

// Text and controls the screens share, from the theme's tokens.
export const styles = StyleSheet.create({
  title: { fontSize: fontSize.xl, fontWeight: "700", color: colors.text, letterSpacing: letterSpacing.heading },
  heading: { fontSize: fontSize.md, fontWeight: "600", color: colors.text, letterSpacing: letterSpacing.heading },
  label: { fontSize: 15, fontWeight: "500", color: colors.text },
  text: { fontSize: 15, lineHeight: 22, color: colors.text },
  detail: { fontSize: fontSize.sm, lineHeight: 18, color: colors.textMuted },
  error: { fontSize: fontSize.base, color: colors.danger },
  input: {
    minHeight: layout.touch,
    borderWidth: 1,
    borderColor: colors.borderControl,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    paddingHorizontal: space.md,
    paddingVertical: 10,
    fontSize: fontSize.md,
    color: colors.text,
  },
  multiline: { minHeight: 96, textAlignVertical: "top" },
  disabled: { opacity: 0.5 },
  // A record in a list, which opens it.
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: space.md,
    gap: space.xs,
  },
});

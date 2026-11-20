import { StyleSheet, Text, View } from "react-native";

import { colors, fontSize, radius, tints } from "../../theme";

// The initials of a name: its first and last words.
function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? [words[0], words.at(-1) ?? ""] : words;
  return letters.map((word) => word[0]?.toUpperCase() ?? "").join("") || "?";
}

// The same name always takes the same tint.
function tint(name: string): string {
  let sum = 0;
  for (const letter of name) {
    sum += letter.codePointAt(0) ?? 0;
  }
  return tints[sum % tints.length];
}

/** A person or a conversation as its initials on a round tint, the same size wherever it appears in a list. */
export function Avatar({ name, size = 40 }: Readonly<{ name: string; size?: number }>) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.avatar, { width: size, height: size, backgroundColor: tint(name) }]}
    >
      <Text style={[styles.text, { fontSize: size < 36 ? fontSize.xs : fontSize.base }]}>{initials(name)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  avatar: { borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  text: { fontWeight: "700", color: colors.primary },
});

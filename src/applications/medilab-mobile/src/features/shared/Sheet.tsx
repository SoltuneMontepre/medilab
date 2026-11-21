import type { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, space } from "../../theme";
import { styles as shared } from "../../styles";
import { Icon } from "./Icon";

/** A block of a screen on a white sheet, as the web's form sheet: its heading, which opens more when it can, an action
 * beside the heading, and its content. */
export function Sheet({
  title,
  onOpen,
  openTestID,
  right,
  testID,
  children,
}: Readonly<{
  title?: string;
  onOpen?: () => void;
  openTestID?: string;
  right?: ReactNode;
  testID?: string;
  children: ReactNode;
}>) {
  return (
    <View style={styles.sheet} testID={testID}>
      {(title || right) && (
        <View style={styles.head}>
          {title && onOpen ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={title}
              testID={openTestID}
              style={styles.link}
              hitSlop={8}
              onPress={onOpen}
            >
              <Text accessibilityRole="header" style={shared.heading}>
                {title}
              </Text>
              <Icon name="chevron-right" size={22} color={colors.primary} />
            </Pressable>
          ) : (
            title && (
              <Text accessibilityRole="header" style={[shared.heading, styles.title]}>
                {title}
              </Text>
            )
          )}
          {right}
        </View>
      )}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: space.lg,
    gap: space.md,
    ...shadow.sm,
  },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space.sm },
  link: { flexDirection: "row", alignItems: "center", gap: 2, flexShrink: 1 },
  title: { flexShrink: 1 },
});

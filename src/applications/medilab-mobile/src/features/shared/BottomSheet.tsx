import type { ReactNode } from "react";
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useT } from "../../locale";
import { styles as shared } from "../../styles";
import { colors, layout, radius, space } from "../../theme";

/** A sheet that rises from the bottom over the screen, for a confirmation or a few more actions. Tapping outside it
 * closes it, as its cancel does. */
export function BottomSheet({
  visible,
  title,
  onClose,
  testID,
  children,
}: Readonly<{ visible: boolean; title: string; onClose: () => void; testID?: string; children: ReactNode }>) {
  const t = useT();
  return (
    <Modal visible={visible} transparent animationType="slide" statusBarTranslucent onRequestClose={onClose}>
      <KeyboardAvoidingView style={styles.backdrop} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <Pressable accessibilityRole="button" accessibilityLabel={t("sheet.close")} style={styles.outside} onPress={onClose} />
        <SafeAreaView edges={["bottom", "left", "right"]} style={styles.sheet} testID={testID}>
          <View style={styles.handle} />
          <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
            <Text accessibilityRole="header" style={shared.heading}>
              {title}
            </Text>
            {children}
          </ScrollView>
        </SafeAreaView>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(19, 41, 75, 0.4)" },
  outside: { flex: 1 },
  sheet: {
    width: "100%",
    maxWidth: layout.contentWidth,
    maxHeight: "85%",
    alignSelf: "center",
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
  },
  handle: {
    alignSelf: "center",
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.borderStrong,
    marginTop: space.sm,
  },
  content: { padding: space.lg, gap: space.md },
});

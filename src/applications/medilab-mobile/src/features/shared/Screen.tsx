import type { ReactNode } from "react";
import { KeyboardAvoidingView, Platform, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, layout, space } from "../../theme";
import { Navbar } from "./Navbar";

/** A screen of the app: the navbar, the content on the app's background, centred and no wider than a phone's on a
 * tablet, and a footer that stays at the bottom, such as the record's actions. A tab's own screen has no way back and
 * sits above the tab bar; any other screen keeps clear of the phone's own bottom bar. Content that is not a list scrolls,
 * and pulling it down reads it again when the screen can. */
export function Screen({
  title,
  tab = false,
  bell = true,
  actions,
  footer,
  scroll = true,
  scrollEnabled = true,
  refreshing = false,
  onRefresh,
  testID,
  children,
}: Readonly<{
  title: string;
  tab?: boolean;
  bell?: boolean;
  actions?: ReactNode;
  footer?: ReactNode;
  scroll?: boolean;
  scrollEnabled?: boolean;
  refreshing?: boolean;
  onRefresh?: () => void;
  testID?: string;
  children: ReactNode;
}>) {
  const body = scroll ? (
    <ScrollView
      style={styles.body}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
      scrollEnabled={scrollEnabled}
      refreshControl={
        onRefresh ? (
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[colors.primary]} tintColor={colors.primary} />
        ) : undefined
      }
    >
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.body, styles.list]}>{children}</View>
  );
  return (
    <View style={styles.screen} testID={testID}>
      <Navbar title={title} back={!tab} bell={bell} actions={actions} />
      <KeyboardAvoidingView style={styles.body} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        {tab || footer ? body : <SafeAreaView edges={["bottom", "left", "right"]} style={styles.body}>{body}</SafeAreaView>}
        {footer}
      </KeyboardAvoidingView>
    </View>
  );
}

/** The content of a screen, centred and no wider than a phone's on a tablet, for lists that scroll themselves. */
export const content = {
  width: "100%",
  maxWidth: layout.contentWidth,
  alignSelf: "center",
  padding: space.lg,
  gap: space.md,
} as const;

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  body: { flex: 1 },
  list: { width: "100%", maxWidth: layout.contentWidth, alignSelf: "center" },
  content: { ...content, paddingBottom: space.xl },
});

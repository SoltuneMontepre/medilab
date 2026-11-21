import { router } from "expo-router";
import type { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useBadges } from "../../badges";
import { useT } from "../../locale";
import { colors, fontSize, layout, letterSpacing, radius, shadow, space } from "../../theme";
import { Icon, type IconName } from "./Icon";

/** The bar on top of every screen, as the web's navbar: the way back on a screen opened from another, the screen's
 * title, its own actions and the notifications, marked while one is unread. */
export function Navbar({
  title,
  back,
  bell = true,
  actions,
}: Readonly<{ title: string; back: boolean; bell?: boolean; actions?: ReactNode }>) {
  const t = useT();
  const { notifications } = useBadges();
  return (
    <SafeAreaView edges={["top", "left", "right"]} style={styles.bar}>
      <View style={styles.row}>
        {back && <NavButton icon="arrow-left" label={t("back")} onPress={goBack} testID="navbar-back" />}
        <Text accessibilityRole="header" numberOfLines={1} style={[styles.title, !back && styles.rootTitle]}>
          {title}
        </Text>
        {actions}
        {bell && (
          <NavButton
            icon={notifications ? "bell-badge-outline" : "bell-outline"}
            label={t(notifications ? "navbar.notificationsUnread" : "navbar.notifications")}
            dot={notifications}
            onPress={() => router.push("/notifications")}
            testID="navbar-notifications"
          />
        )}
      </View>
    </SafeAreaView>
  );
}

// A screen opened from a push has the person's tasks under it; one opened by a link with nothing under it returns there.
function goBack() {
  if (router.canGoBack()) {
    router.back();
  } else {
    router.replace("/");
  }
}

/** An action of the navbar shown as its icon alone, named for assistive technology by its label. */
export function NavButton({
  icon,
  label,
  onPress,
  dot = false,
  testID,
}: Readonly<{ icon: IconName; label: string; onPress: () => void; dot?: boolean; testID?: string }>) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      testID={testID}
      hitSlop={4}
      style={({ pressed }) => [styles.button, pressed && styles.pressed]}
      onPress={onPress}
    >
      <Icon name={icon} size={24} color={colors.textOnPrimary} />
      {dot && <View style={styles.dot} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bar: { backgroundColor: colors.primary, borderBottomWidth: 1, borderBottomColor: colors.primaryDark, ...shadow.sm },
  row: {
    height: layout.navbarHeight,
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
    paddingHorizontal: space.xs,
  },
  title: {
    flex: 1,
    fontSize: fontSize.lg,
    fontWeight: "600",
    letterSpacing: letterSpacing.heading,
    color: colors.textOnPrimary,
    paddingHorizontal: space.xs,
  },
  rootTitle: { paddingHorizontal: space.md },
  button: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  pressed: { backgroundColor: "rgba(255, 255, 255, 0.12)" },
  dot: {
    position: "absolute",
    top: 10,
    right: 10,
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: colors.favorite,
    borderWidth: 1.5,
    borderColor: colors.primary,
  },
});

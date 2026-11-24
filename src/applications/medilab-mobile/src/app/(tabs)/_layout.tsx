import { Tabs } from "expo-router";
import type { ColorValue } from "react-native";

import { useBadges } from "../../badges";
import { Icon, type IconName } from "../../features/shared/Icon";
import { useT } from "../../locale";
import { usePersonRead } from "../../person";
import { colors, fontSize } from "../../theme";

// The most unread messages the tab counts; more show as this number and a plus.
const MOST_COUNTED = 99;

function tabIcon(outline: IconName, filled: IconName) {
  return function TabIcon({ color, focused }: Readonly<{ color: ColorValue; focused: boolean }>) {
    return <Icon name={focused ? filled : outline} size={24} color={typeof color === "string" ? color : undefined} />;
  };
}

/** The app's tabs: the person's tasks, scanning sample labels for those who receive or hand samples over, their
 * conversations with the unread messages, and the menu of the other apps and their account. */
export default function TabsLayout() {
  const t = useT();
  const person = usePersonRead();
  const { conversations } = useBadges();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
        tabBarLabelStyle: { fontSize: fontSize.xs, fontWeight: "600" },
        tabBarBadgeStyle: { backgroundColor: colors.danger, color: colors.textOnPrimary, fontSize: fontSize.xs },
        sceneStyle: { backgroundColor: colors.bg },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: t("tabs.tasks"),
          tabBarButtonTestID: "tab-tasks",
          tabBarIcon: tabIcon("clipboard-check-outline", "clipboard-check"),
        }}
      />
      <Tabs.Screen
        name="scan"
        options={{
          title: t("tabs.scan"),
          tabBarButtonTestID: "tab-scan",
          tabBarIcon: tabIcon("qrcode-scan", "qrcode-scan"),
          href: person?.me.can.scan_samples ? undefined : null,
        }}
      />
      <Tabs.Screen
        name="conversations"
        options={{
          title: t("tabs.conversations"),
          tabBarButtonTestID: "tab-conversations",
          tabBarIcon: tabIcon("message-text-outline", "message-text"),
          tabBarBadge: conversations ? (conversations > MOST_COUNTED ? `${MOST_COUNTED}+` : conversations) : undefined,
        }}
      />
      <Tabs.Screen
        name="menu"
        options={{ title: t("tabs.menu"), tabBarButtonTestID: "tab-menu", tabBarIcon: tabIcon("apps", "apps") }}
      />
    </Tabs>
  );
}

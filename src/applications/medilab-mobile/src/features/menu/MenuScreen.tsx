import { router, type Href } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { ApiError, UnreachableError } from "../../api";
import { LOCALES, type Translate } from "../../i18n";
import { useT } from "../../locale";
import { COMMERCE_MODULE, usePerson, type Person } from "../../person";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, fontSize, radius, space, tints } from "../../theme";
import { LoadNotice } from "../connection/LoadNotice";
import { Unreachable } from "../connection/Unreachable";
import { Avatar } from "../shared/Avatar";
import { Button } from "../shared/Button";
import { Icon, type IconName } from "../shared/Icon";
import { LinkRow } from "../shared/LinkRow";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";

interface App {
  label: string;
  icon: IconName;
  path: Href;
  testID: string;
}

/** The apps the person may use besides the tabs, as the web's app drawer lists them: the results waiting for their
 * signature, the handover records and, with E-commerce installed, the support requests. */
function apps(person: Person, t: Translate): App[] {
  const { can } = person.me;
  const listed: App[] = [];
  if (can.sign_results) {
    listed.push({ label: t("menu.results"), icon: "file-sign", path: "/results", testID: "menu-results" });
  }
  if (can.read_handover_records) {
    listed.push({
      label: t("menu.handoverRecords"),
      icon: "clipboard-text-outline",
      path: "/handover-records",
      testID: "home-handover-records",
    });
  }
  if (person.modules.includes(COMMERCE_MODULE) && can.take_support_requests) {
    listed.push({ label: t("support.title"), icon: "lifebuoy", path: "/support", testID: "menu-support" });
  }
  return listed;
}

/** The menu: the person's other apps and their account, with the server, the notification settings, the language and
 * signing out. */
export function MenuScreen() {
  const t = useT();
  const { load, reload } = usePerson();
  return (
    <Screen title={t("tabs.menu")} tab>
      <LoadNotice load={load} gone="" onRetry={reload} />
      {load.state === "ready" && <Apps apps={apps(load.value, t)} />}
      <Account person={load.state === "ready" ? load.value : null} />
    </Screen>
  );
}

function Apps({ apps: listed }: Readonly<{ apps: App[] }>) {
  const t = useT();
  if (!listed.length) {
    return null;
  }
  return (
    <Sheet title={t("menu.apps")}>
      <View style={styles.grid}>
        {listed.map((app, index) => (
          <Pressable
            key={app.testID}
            accessibilityRole="button"
            accessibilityLabel={app.label}
            testID={app.testID}
            style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
            onPress={() => router.push(app.path)}
          >
            <View style={[styles.tileIcon, { backgroundColor: tints[index % tints.length] }]}>
              <Icon name={app.icon} size={28} color={colors.primary} />
            </View>
            <Text style={styles.tileName} numberOfLines={2}>
              {app.label}
            </Text>
          </Pressable>
        ))}
      </View>
    </Sheet>
  );
}

function Account({ person }: Readonly<{ person: Person | null }>) {
  const t = useT();
  const session = useSession();
  const [refusal, setRefusal] = useState<string | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  async function signOut() {
    setRefusal(null);
    setUnreachable(false);
    try {
      await session.signOut();
    } catch (error) {
      if (error instanceof UnreachableError) {
        setUnreachable(true);
      } else if (error instanceof ApiError) {
        setRefusal(error.message);
      } else {
        throw error;
      }
    }
  }

  return (
    <Sheet title={t("menu.account")}>
      {person && (
        <View style={styles.person}>
          <Avatar name={person.me.name} size={48} />
          <View style={styles.personText}>
            <Text style={shared.heading}>{person.me.name}</Text>
            <Text style={shared.detail}>{[person.me.department, person.me.login].filter(Boolean).join(" · ")}</Text>
          </View>
        </View>
      )}
      <View style={styles.divided}>
        <Text style={shared.detail}>{t("menu.server")}</Text>
        <Text style={shared.label}>{session.serverUrl}</Text>
      </View>
      <View style={styles.divided}>
        <LinkRow
          icon="bell-cog-outline"
          label={t("menu.notificationSettings")}
          testID="menu-notification-settings"
          onPress={() => router.push("/notification-settings")}
        />
      </View>
      <View style={[styles.divided, styles.language]}>
        <Text style={shared.label}>{t("menu.language")}</Text>
        <View style={styles.languages} accessibilityRole="radiogroup">
          {LOCALES.map((locale) => {
            const chosen = session.language === locale;
            return (
              <Pressable
                key={locale}
                accessibilityRole="radio"
                accessibilityState={{ checked: chosen }}
                testID={`menu-language-${locale}`}
                hitSlop={6}
                style={[styles.pill, chosen && styles.pillChosen]}
                onPress={() => session.setLanguage(locale)}
              >
                <Text style={[styles.pillText, chosen && styles.pillTextChosen]}>{t(`language.${locale}`)}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>
      {unreachable && <Unreachable onRetry={signOut} />}
      {refusal && (
        <Text accessibilityRole="alert" style={shared.error}>
          {refusal}
        </Text>
      )}
      <Button label={t("signOut.submit")} icon="logout" onPress={signOut} testID="sign-out" />
    </Sheet>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", flexWrap: "wrap", rowGap: space.lg },
  tile: { width: "33.33%", alignItems: "center", gap: space.sm, paddingHorizontal: space.xs },
  pressed: { opacity: 0.6 },
  tileIcon: { width: 56, height: 56, borderRadius: radius.lg, alignItems: "center", justifyContent: "center" },
  tileName: { fontSize: fontSize.sm, fontWeight: "500", color: colors.text, textAlign: "center" },
  person: { flexDirection: "row", alignItems: "center", gap: space.md },
  personText: { flex: 1, gap: 2 },
  divided: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingTop: space.md, gap: 2 },
  language: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space.md },
  languages: { flexDirection: "row", gap: space.sm },
  pill: {
    minHeight: 36,
    justifyContent: "center",
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    paddingHorizontal: space.md,
  },
  pillChosen: { backgroundColor: colors.primary, borderColor: colors.primary },
  pillText: { fontSize: fontSize.base, color: colors.textSecondary },
  pillTextChosen: { color: colors.textOnPrimary, fontWeight: "600" },
});

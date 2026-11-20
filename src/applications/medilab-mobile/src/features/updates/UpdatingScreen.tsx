import { ActivityIndicator, Image, StatusBar, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useT } from "../../locale";
import { styles as shared } from "../../styles";
import { colors, radius, shadow, space } from "../../theme";
import { Button } from "../shared/Button";
import type { Release } from "./release";

const LOGO = require("../../../assets/logo.png");

/** The only screen of a phone with an update waiting. It has no way into the app: only the update, or trying it again,
 * leaves it. */
export function UpdatingScreen({
  release,
  failed,
  onRetry,
}: Readonly<{ release: Release; failed: boolean; onRetry: () => void }>) {
  const t = useT();
  const version = release.action === "unavailable" ? "" : release.version;
  return (
    <SafeAreaView style={styles.screen} testID="updating-screen">
      <StatusBar barStyle="dark-content" />
      <View style={styles.card}>
        <Image source={LOGO} style={styles.logo} accessibilityIgnoresInvertColors />
        <Text accessibilityRole="header" style={shared.title}>
          {t("update.title")}
        </Text>
        <Text style={[shared.text, styles.center]}>{t(`update.${release.action}`, { version })}</Text>
        {failed ? (
          <Text accessibilityRole="alert" style={[shared.error, styles.center]}>
            {t("update.failed")}
          </Text>
        ) : null}
        {!failed && release.action === "code" ? (
          <ActivityIndicator size="large" color={colors.primary} accessibilityLabel={t("update.downloading")} />
        ) : null}
        {failed || release.action !== "code" ? (
          <View style={styles.action}>
            <Button
              tone="primary"
              icon={release.action === "install" && !failed ? "download" : "refresh"}
              testID="update-retry"
              label={t(release.action === "install" && !failed ? "update.openInstaller" : "update.retry")}
              onPress={onRetry}
            />
          </View>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg, justifyContent: "center", padding: space.lg },
  card: {
    width: "100%",
    maxWidth: 480,
    alignSelf: "center",
    alignItems: "center",
    gap: space.lg,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: space.xl,
    ...shadow.md,
  },
  logo: { width: 64, height: 64, borderRadius: radius.lg },
  center: { textAlign: "center" },
  action: { alignSelf: "stretch" },
});

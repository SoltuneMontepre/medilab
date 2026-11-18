import { ActivityIndicator, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useT } from "../../locale";
import { styles } from "../../styles";
import { Button } from "../shared/Button";
import type { Release } from "./release";

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
      <Text accessibilityRole="header" style={styles.title}>
        {t("update.title")}
      </Text>
      <Text style={styles.detail}>{t(`update.${release.action}`, { version })}</Text>
      {failed ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {t("update.failed")}
        </Text>
      ) : null}
      {!failed && release.action === "code" ? <ActivityIndicator accessibilityLabel={t("update.downloading")} /> : null}
      {failed || release.action !== "code" ? (
        <Button
          primary
          testID="update-retry"
          label={t(release.action === "install" && !failed ? "update.openInstaller" : "update.retry")}
          onPress={onRetry}
        />
      ) : null}
    </SafeAreaView>
  );
}

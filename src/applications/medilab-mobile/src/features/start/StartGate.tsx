import type { ReactNode } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors } from "../../theme";
import { SignInScreen } from "../sign-in/SignInScreen";

/** Opens on sign-in until the phone has a device key, then on the app. */
export function StartGate({ children }: Readonly<{ children: ReactNode }>) {
  const t = useT();
  const { status } = useSession();
  if (status === "loading") {
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color={colors.primary} accessibilityLabel={t("loading")} />
      </View>
    );
  }
  return status === "signedIn" ? children : <SignInScreen />;
}

const styles = StyleSheet.create({
  loading: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg },
});

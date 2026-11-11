import { ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles } from "../../styles";
import { HomeScreen } from "../home/HomeScreen";
import { SignInScreen } from "../sign-in/SignInScreen";

/** Opens on sign-in until the phone has a device key, then on the person's start. */
export function StartScreen() {
  const t = useT();
  const { status } = useSession();
  if (status === "loading") {
    return (
      <SafeAreaView style={styles.screen}>
        <ActivityIndicator accessibilityLabel={t("loading")} />
      </SafeAreaView>
    );
  }
  return status === "signedIn" ? <HomeScreen /> : <SignInScreen />;
}

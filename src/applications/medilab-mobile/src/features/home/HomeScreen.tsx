import { StyleSheet, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { serverUrl } from "../../config";
import { useT } from "../../locale";

export function HomeScreen() {
  const t = useT();
  return (
    <SafeAreaView style={styles.screen}>
      <Text style={styles.title}>MediLab</Text>
      <Text style={styles.detail}>{t("home.server", { url: serverUrl })}</Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: "center", justifyContent: "center", gap: 8, padding: 24 },
  title: { fontSize: 28, fontWeight: "600" },
  detail: { fontSize: 14, color: "#60646c" },
});

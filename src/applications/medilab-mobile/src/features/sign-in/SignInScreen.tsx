import { useState } from "react";
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, UnreachableError } from "../../api";
import { LOCALES, type MessageKey } from "../../i18n";
import { useT } from "../../locale";
import { serverUrlError } from "../../server";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, fontSize, layout, radius, shadow, space } from "../../theme";
import { Unreachable } from "../connection/Unreachable";
import { Button } from "../shared/Button";

type Problem = { kind: "message"; key: MessageKey } | { kind: "refused"; text: string } | { kind: "unreachable" };

const LOGO = require("../../../assets/logo.png");

/** Signs the person in with their MediLab login, in the language they choose, as the web's sign-in page does. The
 * server is the build's own until the person changes it. */
export function SignInScreen() {
  const t = useT();
  const session = useSession();
  const [server, setServer] = useState(session.serverUrl);
  const [changingServer, setChangingServer] = useState(false);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function submit() {
    const invalid = serverUrlError(server);
    if (invalid) {
      setChangingServer(true);
      setProblem({ kind: "message", key: invalid });
      return;
    }
    if (!login.trim() || !password) {
      setProblem({ kind: "message", key: "signIn.missing" });
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await session.signIn(server, login.trim(), password);
    } catch (error) {
      if (error instanceof ApiError) {
        setPassword("");
        setProblem({ kind: "refused", text: error.message });
      } else if (error instanceof UnreachableError) {
        setProblem({ kind: "unreachable" });
      } else {
        throw error;
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.screen}>
      <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <SafeAreaView edges={["top"]} style={styles.brand}>
            <Image source={LOGO} style={styles.logo} accessibilityIgnoresInvertColors />
            <Text style={styles.name}>MediLab</Text>
          </SafeAreaView>
          <View style={styles.cardSpace}>
            <View style={styles.card}>
              <View style={styles.cardHead}>
                <Text accessibilityRole="header" style={shared.heading}>
                  {t("signIn.title")}
                </Text>
                <View style={styles.languages} accessibilityRole="radiogroup">
                  {LOCALES.map((locale) => {
                    const chosen = session.language === locale;
                    return (
                      <Pressable
                        key={locale}
                        accessibilityRole="radio"
                        accessibilityState={{ checked: chosen }}
                        testID={`language-${locale}`}
                        hitSlop={6}
                        style={[styles.language, chosen && styles.chosen]}
                        onPress={() => session.setLanguage(locale)}
                      >
                        <Text style={chosen ? styles.chosenText : styles.languageText}>{t(`language.${locale}`)}</Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>
              <View style={styles.field}>
                <Text style={shared.label}>{t("signIn.login")}</Text>
                <TextInput
                  accessibilityLabel={t("signIn.login")}
                  testID="sign-in-login"
                  style={shared.input}
                  value={login}
                  onChangeText={setLogin}
                  autoCapitalize="none"
                  autoCorrect={false}
                  textContentType="username"
                />
              </View>
              <View style={styles.field}>
                <Text style={shared.label}>{t("signIn.password")}</Text>
                <TextInput
                  accessibilityLabel={t("signIn.password")}
                  testID="sign-in-password"
                  style={shared.input}
                  value={password}
                  onChangeText={setPassword}
                  secureTextEntry
                  textContentType="password"
                  onSubmitEditing={submit}
                />
              </View>
              {changingServer ? (
                <View style={styles.field}>
                  <Text style={shared.label}>{t("signIn.server")}</Text>
                  <TextInput
                    accessibilityLabel={t("signIn.server")}
                    style={shared.input}
                    value={server}
                    onChangeText={setServer}
                    autoCapitalize="none"
                    autoCorrect={false}
                    keyboardType="url"
                  />
                </View>
              ) : (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={t("signIn.changeServer")}
                  testID="sign-in-change-server"
                  hitSlop={8}
                  style={styles.server}
                  onPress={() => setChangingServer(true)}
                >
                  <Text style={shared.detail} numberOfLines={1}>
                    {t("signIn.serverIs", { url: server })}
                  </Text>
                  <Text style={styles.change}>{t("signIn.changeServer")}</Text>
                </Pressable>
              )}
              {problem?.kind === "message" && (
                <Text accessibilityRole="alert" style={shared.error}>
                  {t(problem.key)}
                </Text>
              )}
              {problem?.kind === "refused" && (
                <Text accessibilityRole="alert" style={shared.error}>
                  {problem.text}
                </Text>
              )}
              {problem?.kind === "unreachable" && <Unreachable onRetry={submit} />}
              <Button
                label={t("signIn.submit")}
                icon="login"
                tone="primary"
                disabled={busy}
                testID="sign-in-submit"
                onPress={submit}
              />
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  scroll: { flexGrow: 1, paddingBottom: space.xl },
  brand: {
    backgroundColor: colors.primary,
    alignItems: "center",
    gap: space.sm,
    paddingTop: space.xl,
    paddingBottom: 72,
  },
  logo: { width: 72, height: 72, borderRadius: radius.lg },
  name: { fontSize: 26, fontWeight: "700", color: colors.textOnPrimary, letterSpacing: -0.3 },
  cardSpace: { marginTop: -48, paddingHorizontal: space.lg },
  // The sign-in card: white, rounded and lifted over the brand band.
  card: {
    width: "100%",
    maxWidth: 480,
    alignSelf: "center",
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: space.xl,
    gap: space.lg,
    ...shadow.md,
  },
  cardHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: space.sm,
    flexWrap: "wrap",
  },
  languages: { flexDirection: "row", gap: space.sm },
  language: {
    minHeight: 32,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
  },
  chosen: { borderColor: colors.primary, backgroundColor: colors.primary },
  languageText: { fontSize: fontSize.sm, color: colors.textSecondary },
  chosenText: { fontSize: fontSize.sm, color: colors.textOnPrimary, fontWeight: "600" },
  field: { gap: 6 },
  server: { minHeight: layout.touch - 12, flexDirection: "row", alignItems: "center", gap: space.sm },
  change: { fontSize: fontSize.sm, fontWeight: "600", color: colors.accentDark },
});

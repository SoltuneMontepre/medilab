import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, UnreachableError } from "../../api";
import { LOCALES, type MessageKey } from "../../i18n";
import { useT } from "../../locale";
import { serverUrlError } from "../../server";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { Unreachable } from "../connection/Unreachable";

type Problem = { kind: "message"; key: MessageKey } | { kind: "refused"; text: string } | { kind: "unreachable" };

/** Signs the person in with their MediLab login, on the server address and in the language they choose. */
export function SignInScreen() {
  const t = useT();
  const session = useSession();
  const [server, setServer] = useState(session.serverUrl);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function submit() {
    const invalid = serverUrlError(server);
    if (invalid) {
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
    <SafeAreaView style={shared.screen}>
      <Text style={shared.title}>{t("signIn.title")}</Text>
      <View style={styles.languages} accessibilityRole="radiogroup">
        {LOCALES.map((locale) => (
          <Pressable
            key={locale}
            accessibilityRole="radio"
            accessibilityState={{ checked: session.language === locale }}
            style={[styles.language, session.language === locale && styles.chosen]}
            onPress={() => session.setLanguage(locale)}
          >
            <Text style={session.language === locale ? styles.chosenText : styles.languageText}>
              {t(`language.${locale}`)}
            </Text>
          </Pressable>
        ))}
      </View>
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
      <View style={styles.field}>
        <Text style={shared.label}>{t("signIn.login")}</Text>
        <TextInput
          accessibilityLabel={t("signIn.login")}
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
          style={shared.input}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          textContentType="password"
        />
      </View>
      {problem?.kind === "message" && <Text style={shared.error}>{t(problem.key)}</Text>}
      {problem?.kind === "refused" && <Text style={shared.error}>{problem.text}</Text>}
      {problem?.kind === "unreachable" && <Unreachable onRetry={submit} />}
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: busy }}
        disabled={busy}
        style={[shared.primaryButton, busy && styles.busy]}
        onPress={submit}
      >
        <Text style={shared.primaryButtonText}>{t("signIn.submit")}</Text>
      </Pressable>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  languages: { flexDirection: "row", gap: 8 },
  language: { borderWidth: 1, borderColor: colors.border, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 6 },
  chosen: { borderColor: colors.primary, backgroundColor: colors.primary },
  languageText: { color: colors.text },
  chosenText: { color: "#ffffff", fontWeight: "600" },
  field: { gap: 6 },
  busy: { opacity: 0.6 },
});

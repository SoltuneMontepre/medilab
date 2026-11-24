import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { Conclusion, Result } from "../../api";
import type { MessageKey } from "../../i18n";
import { useT } from "../../locale";
import { styles as shared } from "../../styles";
import { colors, fontSize, radius, space } from "../../theme";
import { Button } from "../shared/Button";
import { parseNumber, typedNumber } from "./resultNumber";

/** What the tester enters or changes: a number with the decimals typed, or a text, and the conclusion. */
export interface ResultEntry {
  value?: number;
  decimals?: number;
  value_text?: string | null;
  conclusion?: Conclusion | null;
}

type Kind = "number" | "text";

const KINDS: { value: Kind; label: MessageKey }[] = [
  { value: "number", label: "result.number" },
  { value: "text", label: "result.text" },
];

const CONCLUSIONS: { value: Conclusion; label: MessageKey }[] = [
  { value: "pass", label: "result.conclusion.pass" },
  { value: "fail", label: "result.conclusion.fail" },
  { value: "insufficient", label: "result.conclusion.insufficient" },
];

/** The result as a number in the unit of the way of testing or as a text, with its conclusion when the sample's
 * regulation is compared, as the web's result form takes it. */
export function ResultForm({
  unit,
  comparisonRequested,
  result,
  busy,
  onSubmit,
  onCancel,
}: Readonly<{
  unit: string;
  comparisonRequested: boolean;
  result?: Result;
  busy: boolean;
  onSubmit: (entry: ResultEntry) => void;
  onCancel?: () => void;
}>) {
  const t = useT();
  const [kind, setKind] = useState<Kind>(result?.value_text ? "text" : "number");
  const [number, setNumber] = useState(
    result?.value === null || result?.value === undefined ? "" : typedNumber(result.value, result.decimals),
  );
  const [text, setText] = useState(result?.value_text ?? "");
  const [conclusion, setConclusion] = useState<Conclusion | null>(result?.conclusion ?? null);
  const [invalid, setInvalid] = useState<string | null>(null);

  function entry(): ResultEntry | string {
    let entered: ResultEntry;
    if (kind === "number") {
      const parsed = parseNumber(number);
      if (!parsed) {
        return t("result.invalidNumber");
      }
      entered = { value: parsed.value, decimals: parsed.decimals, value_text: null };
    } else {
      if (!text.trim()) {
        return t("result.missingText");
      }
      entered = { value_text: text.trim() };
    }
    if (!comparisonRequested) {
      return entered;
    }
    return conclusion ? { ...entered, conclusion } : t("result.missingConclusion");
  }

  function submit() {
    const entered = entry();
    if (typeof entered === "string") {
      setInvalid(entered);
      return;
    }
    setInvalid(null);
    onSubmit(entered);
  }

  return (
    <View style={styles.form}>
      <Choices options={KINDS} chosen={kind} onChoose={setKind} />
      {kind === "number" ? (
        <View style={styles.field}>
          <Text style={shared.label}>{t("result.value", { unit })}</Text>
          <TextInput
            accessibilityLabel={t("result.value", { unit })}
            testID="result-value"
            placeholder="0,000"
            placeholderTextColor={colors.textMuted}
            keyboardType="decimal-pad"
            style={[shared.input, styles.number]}
            value={number}
            onChangeText={setNumber}
          />
        </View>
      ) : (
        <View style={styles.field}>
          <Text style={shared.label}>{t("result.textValue")}</Text>
          <TextInput
            accessibilityLabel={t("result.textValue")}
            placeholder={t("result.textHint")}
            placeholderTextColor={colors.textMuted}
            style={shared.input}
            value={text}
            onChangeText={setText}
          />
        </View>
      )}
      {comparisonRequested && (
        <View style={styles.field}>
          <Text style={shared.label}>{t("result.conclusion")}</Text>
          {result?.limit_missing && <Text style={shared.detail}>{t("result.limitMissing")}</Text>}
          <Choices options={CONCLUSIONS} chosen={conclusion} onChoose={setConclusion} />
        </View>
      )}
      {invalid && (
        <Text accessibilityRole="alert" style={shared.error}>
          {invalid}
        </Text>
      )}
      <Button label={t("result.save")} icon="content-save-outline" onPress={submit} tone="primary" disabled={busy} testID="result-save" />
      {onCancel && <Button label={t("result.cancel")} onPress={onCancel} />}
    </View>
  );
}

function Choices<T extends string>({
  options,
  chosen,
  onChoose,
}: Readonly<{ options: { value: T; label: MessageKey }[]; chosen: T | null; onChoose: (value: T) => void }>) {
  const t = useT();
  return (
    <View style={styles.choices} accessibilityRole="radiogroup">
      {options.map(({ value, label }) => {
        const selected = chosen === value;
        return (
          <Pressable
            key={value}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            testID={`choice-${value}`}
            style={[styles.choice, selected && styles.chosen]}
            onPress={() => onChoose(value)}
          >
            <Text style={[styles.choiceText, selected && styles.chosenText]}>{t(label)}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: space.lg },
  field: { gap: 6 },
  number: { fontSize: 22, fontWeight: "600" },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  choice: {
    minHeight: 40,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.pill,
    paddingHorizontal: space.lg,
    backgroundColor: colors.surface,
  },
  chosen: { borderColor: colors.primary, backgroundColor: colors.primary },
  choiceText: { fontSize: fontSize.base, fontWeight: "500", color: colors.textSecondary },
  chosenText: { color: colors.textOnPrimary, fontWeight: "600" },
});

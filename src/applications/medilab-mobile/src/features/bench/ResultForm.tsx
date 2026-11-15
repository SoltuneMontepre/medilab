import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { Conclusion, Result } from "../../api";
import type { MessageKey } from "../../i18n";
import { useT } from "../../locale";
import { colors, styles as shared } from "../../styles";
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
    <View style={shared.section}>
      <Choices options={KINDS} chosen={kind} onChoose={setKind} />
      {kind === "number" ? (
        <TextInput
          accessibilityLabel={t("result.value", { unit })}
          testID="result-value"
          placeholder={t("result.value", { unit })}
          keyboardType="decimal-pad"
          style={shared.input}
          value={number}
          onChangeText={setNumber}
        />
      ) : (
        <TextInput
          accessibilityLabel={t("result.textValue")}
          placeholder={t("result.textHint")}
          style={shared.input}
          value={text}
          onChangeText={setText}
        />
      )}
      {comparisonRequested && (
        <>
          <Text style={shared.label}>{t("result.conclusion")}</Text>
          {result?.limit_missing && <Text style={shared.detail}>{t("result.limitMissing")}</Text>}
          <Choices options={CONCLUSIONS} chosen={conclusion} onChoose={setConclusion} />
        </>
      )}
      {invalid && (
        <Text accessibilityRole="alert" style={shared.error}>
          {invalid}
        </Text>
      )}
      <Button label={t("result.save")} onPress={submit} primary disabled={busy} testID="result-save" />
      {onCancel && (
        <Button label={t("result.cancel")} onPress={onCancel} />
      )}
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
      {options.map(({ value, label }) => (
        <Pressable
          key={value}
          accessibilityRole="radio"
          accessibilityState={{ checked: chosen === value }}
          style={[styles.choice, chosen === value && styles.chosen]}
          testID={`choice-${value}`}
          onPress={() => onChoose(value)}
        >
          <Text style={shared.label}>{t(label)}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8 },
  chosen: { borderColor: colors.primary, borderWidth: 2 },
});

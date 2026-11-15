import { StyleSheet, Text, View } from "react-native";

import type { MessageKey } from "../../i18n";
import { useT } from "../../locale";
import { styles as shared } from "../../styles";

export type Fact = [MessageKey, string | null];

/** A record's facts, each under its label; a fact without a value is left out. */
export function Facts({ facts }: Readonly<{ facts: Fact[] }>) {
  const t = useT();
  return (
    <>
      {facts
        .filter(([, value]) => value)
        .map(([label, value]) => (
          <View key={label} style={styles.fact}>
            <Text style={shared.detail}>{t(label)}</Text>
            <Text style={shared.label}>{value}</Text>
          </View>
        ))}
    </>
  );
}

const styles = StyleSheet.create({
  fact: { gap: 2 },
});

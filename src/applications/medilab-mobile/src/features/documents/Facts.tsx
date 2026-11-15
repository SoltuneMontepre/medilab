import { StyleSheet, Text, View } from "react-native";

import type { MessageKey } from "../../i18n";
import { useT } from "../../locale";
import { styles as shared } from "../../styles";

/** A record's facts as labels and values, leaving out those without a value. */
export function Facts({ facts }: Readonly<{ facts: [MessageKey, string | null][] }>) {
  const t = useT();
  return facts
    .filter(([, value]) => value)
    .map(([label, value]) => (
      <View key={label} style={styles.fact}>
        <Text style={shared.detail}>{t(label)}</Text>
        <Text style={shared.label}>{value}</Text>
      </View>
    ));
}

const styles = StyleSheet.create({
  fact: { gap: 2 },
});

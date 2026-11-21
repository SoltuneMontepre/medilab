import { StyleSheet, Text, View } from "react-native";

import type { MessageKey } from "../../i18n";
import { useT } from "../../locale";
import { styles as shared } from "../../styles";
import { colors, space } from "../../theme";

export type Fact = [MessageKey, string | null];

/** A record's facts as label and value rows of its sheet, between soft dividers; a fact without a value is left out. */
export function Facts({ facts }: Readonly<{ facts: Fact[] }>) {
  const t = useT();
  return (
    <View>
      {facts
        .filter(([, value]) => value)
        .map(([label, value], index) => (
          <View key={label} style={[styles.fact, index > 0 && styles.divided]}>
            <Text style={shared.detail}>{t(label)}</Text>
            <Text style={shared.label}>{value}</Text>
          </View>
        ))}
    </View>
  );
}

const styles = StyleSheet.create({
  fact: { gap: 2, paddingVertical: space.sm },
  divided: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
});

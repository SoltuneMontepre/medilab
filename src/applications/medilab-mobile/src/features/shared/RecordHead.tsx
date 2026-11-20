import type { ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { styles as shared } from "../../styles";
import { space } from "../../theme";
import { Badge, type BadgeTone } from "./Badge";

/** The head of a record's screen, as the web's form header: its name, its status, and the facts that say whether to
 * act, such as its code, deadline and person. */
export function RecordHead({
  title,
  status,
  children,
}: Readonly<{ title: string; status?: { label: string; tone: BadgeTone }; children?: ReactNode }>) {
  return (
    <View style={styles.head}>
      <Text style={shared.title}>{title}</Text>
      {status && <Badge label={status.label} tone={status.tone} />}
      {children && <View style={styles.facts}>{children}</View>}
    </View>
  );
}

const styles = StyleSheet.create({
  head: { gap: space.sm, paddingVertical: space.xs },
  facts: { flexDirection: "row", flexWrap: "wrap", columnGap: space.lg, rowGap: space.xs },
});

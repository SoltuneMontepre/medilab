import { StyleSheet, Text, View } from "react-native";

import { styles as shared } from "../../styles";
import { colors, radius, space } from "../../theme";
import { Button } from "./Button";
import { Icon } from "./Icon";

/** Something kept on the phone that MediLab did not get, such as a photo or a signature, to send again or discard. */
export function UnsentCard({
  label,
  send,
  discard,
  busy,
  onSend,
  onDiscard,
  testID,
}: Readonly<{
  label: string;
  send: string;
  discard: string;
  busy: boolean;
  onSend: () => void;
  onDiscard: () => void;
  testID: string;
}>) {
  return (
    <View style={styles.card} testID={testID}>
      <View style={styles.head}>
        <Icon name="cloud-upload-outline" color={colors.warning} />
        <Text style={[shared.label, styles.label]}>{label}</Text>
      </View>
      <View style={styles.actions}>
        <View style={styles.slot}>
          <Button label={send} onPress={onSend} tone="primary" compact disabled={busy} testID={`${testID}-send`} />
        </View>
        <View style={styles.slot}>
          <Button label={discard} onPress={onDiscard} tone="danger" compact disabled={busy} testID={`${testID}-discard`} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.warningSoft,
    borderWidth: 1,
    borderColor: colors.warning,
    borderRadius: radius.md,
    padding: space.md,
    gap: space.md,
  },
  head: { flexDirection: "row", gap: space.sm, alignItems: "center" },
  label: { flex: 1 },
  actions: { flexDirection: "row", gap: space.sm },
  slot: { flex: 1 },
});

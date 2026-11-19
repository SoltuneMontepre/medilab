import { Text, View } from "react-native";

import { styles as shared } from "../../styles";
import { Button } from "./Button";

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
    <View style={shared.card} testID={testID}>
      <Text style={shared.label}>{label}</Text>
      <Button label={send} onPress={onSend} primary disabled={busy} testID={`${testID}-send`} />
      <Button label={discard} onPress={onDiscard} disabled={busy} testID={`${testID}-discard`} />
    </View>
  );
}

import { Pressable, Text } from "react-native";

import { styles as shared } from "../../styles";

/** A button of the screen: the primary one for the action the screen is for, a secondary one otherwise. */
export function Button({
  label,
  onPress,
  primary = false,
  disabled = false,
  testID,
}: Readonly<{ label: string; onPress: () => void; primary?: boolean; disabled?: boolean; testID?: string }>) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      style={[primary ? shared.primaryButton : shared.secondaryButton, disabled && shared.disabled]}
      onPress={onPress}
    >
      <Text style={primary ? shared.primaryButtonText : shared.secondaryButtonText}>{label}</Text>
    </Pressable>
  );
}

import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import type { ComponentProps } from "react";

import { colors } from "../../theme";

// Material Design Icons, the set the web names `mdi:<name>`.
export type IconName = ComponentProps<typeof MaterialCommunityIcons>["name"];

/** An icon beside a label or alone in a button; the label, not the icon, is what assistive technology reads. */
export function Icon({
  name,
  size = 22,
  color = colors.textMuted,
}: Readonly<{ name: IconName; size?: number; color?: string }>) {
  return (
    <MaterialCommunityIcons
      name={name}
      size={size}
      color={color}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    />
  );
}

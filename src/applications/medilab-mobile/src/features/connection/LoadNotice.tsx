import { ActivityIndicator, Text } from "react-native";

import type { Load } from "../../load";
import { useT } from "../../locale";
import { styles as shared } from "../../styles";
import { Unreachable } from "./Unreachable";

/** What a screen shows until what it reads is ready: loading, MediLab not reached, the record gone with the screen's
 * own words for it, or MediLab's refusal. */
export function LoadNotice({ load, gone, onRetry }: Readonly<{ load: Load<unknown>; gone: string; onRetry: () => void }>) {
  const t = useT();
  switch (load.state) {
    case "loading":
      return <ActivityIndicator accessibilityLabel={t("loading")} />;
    case "unreachable":
      return <Unreachable onRetry={onRetry} />;
    case "gone":
      return (
        <Text accessibilityRole="alert" style={shared.error}>
          {gone}
        </Text>
      );
    case "refused":
      return <Text style={shared.error}>{load.message}</Text>;
    default:
      return null;
  }
}

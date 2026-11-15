import { Text } from "react-native";

import type { Load } from "../../load";
import { styles as shared } from "../../styles";
import { Unreachable } from "./Unreachable";

/** Why an action of the screen did not happen: MediLab not reached, with a retry, the record gone, with the screen's
 * own words for it, or MediLab's refusal. */
export function ActionProblem({
  problem,
  gone,
  onRetry,
}: Readonly<{ problem: Load<never> | null; gone: string; onRetry: () => void }>) {
  if (problem?.state === "unreachable") {
    return <Unreachable onRetry={onRetry} />;
  }
  if (problem?.state === "refused" || problem?.state === "gone") {
    return (
      <Text accessibilityRole="alert" style={shared.error}>
        {problem.state === "refused" ? problem.message : gone}
      </Text>
    );
  }
  return null;
}

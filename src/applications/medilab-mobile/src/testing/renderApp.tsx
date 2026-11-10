import { render } from "@testing-library/react-native";

import { StartScreen } from "../features/start/StartScreen";
import { SessionProvider } from "../session";

/** The app as it starts, with what the secure storage holds. */
export function renderApp() {
  return render(
    <SessionProvider>
      <StartScreen />
    </SessionProvider>,
  );
}

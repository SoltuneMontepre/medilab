import { render } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { HomeScreen } from "../features/home/HomeScreen";
import { StartGate } from "../features/start/StartGate";
import { SessionProvider } from "../session";

/** The app as it starts, with what the secure storage holds: sign-in, or once signed in the screen given, the person's
 * day unless another is named. */
export function renderApp(signedIn: ReactNode = <HomeScreen />) {
  return render(
    <SessionProvider>
      <StartGate>{signedIn}</StartGate>
    </SessionProvider>,
  );
}

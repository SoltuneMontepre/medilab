import { render } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { SessionProvider, useSession } from "../session";
import { kept } from "./fakeMediLab";

function OnceSignedIn({ children }: Readonly<{ children: ReactNode }>) {
  return useSession().status === "signedIn" ? children : null;
}

/** A screen of a phone signed in with the kept device key, as the app opens it once the key is read. */
export function renderSignedIn(screen: ReactNode) {
  kept().set("medilab.device_key", "device-key");
  return render(
    <SessionProvider>
      <OnceSignedIn>{screen}</OnceSignedIn>
    </SessionProvider>,
  );
}

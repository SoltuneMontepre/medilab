import { Stack } from "expo-router";

import { PushOpener } from "../features/documents/PushOpener";
import { UpdateGate } from "../features/updates/UpdateGate";
import { SessionProvider } from "../session";

export default function RootLayout() {
  return (
    <SessionProvider>
      <UpdateGate>
        <PushOpener />
        <Stack screenOptions={{ headerShown: false }} />
      </UpdateGate>
    </SessionProvider>
  );
}

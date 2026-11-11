import { Stack } from "expo-router";

import { PushOpener } from "../features/documents/PushOpener";
import { SessionProvider } from "../session";

export default function RootLayout() {
  return (
    <SessionProvider>
      <PushOpener />
      <Stack screenOptions={{ headerShown: false }} />
    </SessionProvider>
  );
}

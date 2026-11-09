import { Stack } from "expo-router";

import { SessionProvider } from "../session";

export default function RootLayout() {
  return (
    <SessionProvider>
      <Stack screenOptions={{ headerShown: false }} />
    </SessionProvider>
  );
}

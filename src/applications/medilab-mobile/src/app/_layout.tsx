import { Stack } from "expo-router";
import { StatusBar } from "react-native";

import { BadgeProvider } from "../badges";
import { PushOpener } from "../features/documents/PushOpener";
import { StartGate } from "../features/start/StartGate";
import { UpdateGate } from "../features/updates/UpdateGate";
import { PersonProvider } from "../person";
import { SessionProvider } from "../session";
import { colors } from "../theme";

export default function RootLayout() {
  return (
    <SessionProvider>
      <StatusBar barStyle="light-content" />
      <UpdateGate>
        <StartGate>
          <PersonProvider>
            <BadgeProvider>
              <PushOpener />
              <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }} />
            </BadgeProvider>
          </PersonProvider>
        </StartGate>
      </UpdateGate>
    </SessionProvider>
  );
}

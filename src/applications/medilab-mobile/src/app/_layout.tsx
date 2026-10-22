import { Stack } from "expo-router";

import { LocaleProvider } from "../locale";

export default function RootLayout() {
  return (
    <LocaleProvider locale="vi">
      <Stack screenOptions={{ headerShown: false }} />
    </LocaleProvider>
  );
}

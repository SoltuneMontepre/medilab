import type { PermissionResponse } from "expo-camera";
import { Text } from "react-native";

import { useT } from "../../locale";
import { styles as shared } from "../../styles";
import { Button } from "./Button";

/** Why the screen needs the camera the person has not allowed, and the way to allow it while the phone still asks. */
export function CameraPermission({
  permission,
  needed,
  onAllow,
}: Readonly<{ permission: PermissionResponse | null; needed: string; onAllow: () => void }>) {
  const t = useT();
  if (!permission || permission.granted) {
    return null;
  }
  return (
    <>
      <Text style={shared.detail}>{needed}</Text>
      {permission.canAskAgain && <Button label={t("scan.allowCamera")} onPress={onAllow} testID="allow-camera" />}
    </>
  );
}

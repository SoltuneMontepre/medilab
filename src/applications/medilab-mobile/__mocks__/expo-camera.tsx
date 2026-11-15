import type { ComponentProps } from "react";
import { View } from "react-native";

// The camera, granted unless a test says otherwise; a test reads a label by firing barcodeScanned on the camera view.
export const requestPermission = jest.fn();

export const useCameraPermissions = jest.fn(() => [
  { granted: true, canAskAgain: true, status: "granted", expires: "never" },
  requestPermission,
  jest.fn(),
]);

export function CameraView(props: ComponentProps<typeof View> & { onBarcodeScanned?: unknown }) {
  return <View testID="camera" {...props} />;
}

import type { ComponentProps, Ref } from "react";
import { useImperativeHandle } from "react";
import { View } from "react-native";

import { memoryFiles } from "../src/testing/memoryFiles";

// The camera, granted unless a test says otherwise; a test reads a label by firing barcodeScanned on the camera view.
export const requestPermission = jest.fn();

export const useCameraPermissions = jest.fn(() => [
  { granted: true, canAskAgain: true, status: "granted", expires: "never" },
  requestPermission,
  jest.fn(),
]);

// Taking a picture leaves it in the camera's cache, as the camera does.
export const takePictureAsync = jest.fn(async () => {
  const uri = `file:///cache/Camera/${memoryFiles.size}.jpg`;
  memoryFiles.set(uri, "photo of the sample");
  return { uri, width: 4, height: 3, format: "jpg" };
});

export function CameraView({
  ref,
  ...props
}: ComponentProps<typeof View> & { onBarcodeScanned?: unknown; ref?: Ref<unknown> }) {
  useImperativeHandle(ref, () => ({ takePictureAsync }));
  return <View testID="camera" {...props} />;
}

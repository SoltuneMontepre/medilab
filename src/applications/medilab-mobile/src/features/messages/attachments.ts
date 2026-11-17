import { getDocumentAsync } from "expo-document-picker";
import { File } from "expo-file-system";
import {
  launchCameraAsync,
  launchImageLibraryAsync,
  requestCameraPermissionsAsync,
  type ImagePickerResult,
} from "expo-image-picker";

import type { NewFile } from "../../api";

// The quality photos are sent at, which keeps a phone's photo well under MediLab's 10 MiB limit.
const PHOTO_QUALITY = 0.7;

export type PhotoSource = "camera" | "gallery";

/** A photo the person takes with the camera or picks from the gallery, or null when they cancel or refuse the camera. */
export async function pickPhoto(from: PhotoSource): Promise<NewFile | null> {
  let picked: ImagePickerResult;
  if (from === "camera") {
    const permission = await requestCameraPermissionsAsync();
    if (!permission.granted) {
      return null;
    }
    picked = await launchCameraAsync({ mediaTypes: ["images"], base64: true, quality: PHOTO_QUALITY });
  } else {
    picked = await launchImageLibraryAsync({ mediaTypes: ["images"], base64: true, quality: PHOTO_QUALITY });
  }
  const photo = picked.canceled ? null : picked.assets[0];
  if (!photo?.base64) {
    return null;
  }
  return {
    name: photo.fileName ?? `photo-${Date.now()}.jpg`,
    mimetype: photo.mimeType ?? "image/jpeg",
    data: photo.base64,
  };
}

/** A file the person picks on the phone, or null when they cancel. */
export async function pickFile(): Promise<NewFile | null> {
  const picked = await getDocumentAsync({ copyToCacheDirectory: true });
  const file = picked.canceled ? null : picked.assets[0];
  if (!file) {
    return null;
  }
  return {
    name: file.name,
    mimetype: file.mimeType ?? "application/octet-stream",
    data: await new File(file.uri).base64(),
  };
}

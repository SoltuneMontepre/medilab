import {
  getInitialNotification,
  getMessaging,
  getToken,
  onNotificationOpenedApp,
  onTokenRefresh,
  type RemoteMessage,
} from "@react-native-firebase/messaging";
import { PermissionsAndroid, Platform } from "react-native";

// The first Android version that asks the person before showing notifications.
const ANDROID_NOTIFICATION_PERMISSION_API = 33;

/** The document a push is about, from its data: the model and id the app opens. */
export interface PushedDocument {
  model: string;
  id: number;
}

/** The document a push names, or null for a push without one. */
export function pushedDocument(message: RemoteMessage | null): PushedDocument | null {
  const model = message?.data?.model;
  const id = Number(message?.data?.id);
  if (typeof model !== "string" || !model || !Number.isInteger(id) || id <= 0) {
    return null;
  }
  return { model, id };
}

/** The Firebase token pushes reach this phone with, once the person allows notifications; null when the build has no
 * Firebase project, such as a local build without its google-services.json, or Firebase cannot give one. */
export async function pushToken(): Promise<string | null> {
  try {
    if (Platform.OS === "android" && Number(Platform.Version) >= ANDROID_NOTIFICATION_PERMISSION_API) {
      await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS);
    }
    return await getToken(getMessaging());
  } catch {
    return null;
  }
}

/** Calls back with each new token Firebase gives the phone; returns the unsubscribing function. */
export function watchPushToken(onToken: (token: string) => void): () => void {
  try {
    return onTokenRefresh(getMessaging(), onToken);
  } catch {
    return () => undefined;
  }
}

/** Calls back with the document of each push the person taps, including the one that started the app. */
export function watchOpenedPushes(onOpened: (document: PushedDocument) => void): () => void {
  try {
    const messaging = getMessaging();
    getInitialNotification(messaging)
      .then((message) => {
        const document = pushedDocument(message);
        if (document) {
          onOpened(document);
        }
      })
      .catch(() => undefined);
    return onNotificationOpenedApp(messaging, (message) => {
      const document = pushedDocument(message);
      if (document) {
        onOpened(document);
      }
    });
  } catch {
    return () => undefined;
  }
}

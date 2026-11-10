import {
  getInitialNotification,
  getMessaging,
  onNotificationOpenedApp,
  onRegistered,
  register,
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

/** Calls back with the id pushes reach this phone with, its Firebase Installation ID, once the person allows
 * notifications, and again whenever Firebase changes it; returns the unsubscribing function. A build without a Firebase
 * project, such as a local build without its google-services.json, never calls back. */
export function watchPushToken(onToken: (token: string) => void): () => void {
  let unsubscribe: () => void = () => undefined;
  let stopped = false;
  allowNotifications()
    .then(() => {
      if (stopped) {
        return;
      }
      const messaging = getMessaging();
      unsubscribe = onRegistered(messaging, onToken);
      return register(messaging);
    })
    .catch(() => undefined);
  return () => {
    stopped = true;
    unsubscribe();
  };
}

// Android 13 and later show notifications only once the person allows them.
async function allowNotifications(): Promise<void> {
  if (Platform.OS === "android" && Number(Platform.Version) >= ANDROID_NOTIFICATION_PERMISSION_API) {
    await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS);
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

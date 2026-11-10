// Firebase Cloud Messaging as the tests drive it: the token Firebase gives, and the pushes the person taps.
type Message = { data?: Record<string, string> } | null;

const state = {
  token: null as string | null,
  initial: null as Message,
  onOpened: [] as ((message: Message) => void)[],
  onToken: [] as ((token: string) => void)[],
};

/** The token Firebase gives the phone; null stands for a build without a Firebase project. */
export function givePushToken(token: string | null) {
  state.token = token;
}

/** The push the app was started from. */
export function startFromPush(message: Message) {
  state.initial = message;
}

/** The person taps a push while the app runs in the background. */
export function tapPush(message: Message) {
  state.onOpened.forEach((listener) => listener(message));
}

/** Firebase gives the phone a new token. */
export function refreshPushToken(token: string) {
  state.token = token;
  state.onToken.forEach((listener) => listener(token));
}

export function resetMessaging() {
  state.token = null;
  state.initial = null;
  state.onOpened = [];
  state.onToken = [];
}

export const getMessaging = jest.fn(() => ({}));

export const getToken = jest.fn(async () => {
  if (state.token === null) {
    throw new Error("No Firebase App '[DEFAULT]' has been created.");
  }
  return state.token;
});

export const getInitialNotification = jest.fn(async () => {
  const message = state.initial;
  state.initial = null;
  return message;
});

export const onNotificationOpenedApp = jest.fn((_messaging: unknown, listener: (message: Message) => void) => {
  state.onOpened.push(listener);
  return () => {
    state.onOpened = state.onOpened.filter((kept) => kept !== listener);
  };
});

export const onTokenRefresh = jest.fn((_messaging: unknown, listener: (token: string) => void) => {
  state.onToken.push(listener);
  return () => {
    state.onToken = state.onToken.filter((kept) => kept !== listener);
  };
});

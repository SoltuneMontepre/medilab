import type { Locale } from "./i18n";

// The path of MediLab's API under the server address.
const API_PATH = "/medilab/api/v1";
// Seconds a call waits for MediLab before it counts as unreachable.
const TIMEOUT_SECONDS = 20;

/** MediLab refused the call: the app acts on the code and shows the message, which is in the person's language. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** MediLab could not be reached, so the call changed nothing. */
export class UnreachableError extends Error {}

export interface Call {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  key?: string | null;
}

/** Calls MediLab's API at the path and answers its JSON, or null for an answer without content. */
export async function callApi<T>(serverUrl: string, language: Locale, path: string, call: Call = {}): Promise<T | null> {
  const headers: Record<string, string> = { Accept: "application/json", "Accept-Language": language };
  if (call.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (call.key) {
    headers.Authorization = `Bearer ${call.key}`;
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_SECONDS * 1000);
  let response: Response;
  try {
    response = await fetch(serverUrl + API_PATH + path, {
      method: call.method ?? "GET",
      headers,
      body: call.body === undefined ? undefined : JSON.stringify(call.body),
      signal: controller.signal,
    });
  } catch {
    throw new UnreachableError();
  } finally {
    clearTimeout(timeout);
  }
  if (response.status === 204) {
    return null;
  }
  const answer = await response.json().catch(() => null);
  if (response.ok && answer !== null) {
    return answer as T;
  }
  if (answer?.error?.code) {
    throw new ApiError(answer.error.code, answer.error.message, response.status);
  }
  // Something other than MediLab answered, such as a proxy while MediLab is down.
  throw new UnreachableError();
}

export interface Device {
  id: number;
  name: string;
  platform: string;
  status: string;
}

export interface SignedIn {
  key: string;
  device: Device;
}

/** The document a notification or a push is about. */
export interface DocumentReference {
  model: string;
  id: number;
  code: string;
}

export interface Notification {
  id: number;
  event: string | null;
  title: string;
  date: string;
  read: boolean;
  document: DocumentReference | null;
}

export interface NotificationPage {
  notifications: Notification[];
  next_after: number | null;
}

/** An event and whether it is pushed to the person's phones. */
export interface PushPreference {
  event: string;
  name: string;
  mandatory: boolean;
  push: boolean;
}

/** A document as the person may read it, with the app's screen for it and its address on the web. */
export interface MediLabDocument extends DocumentReference {
  title: string;
  screen: string;
  url: string;
}

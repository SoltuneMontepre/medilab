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
  headers?: Record<string, string>;
}

/** Calls MediLab's API at the path and answers its JSON, or null for an answer without content. */
export async function callApi<T>(serverUrl: string, language: Locale, path: string, call: Call = {}): Promise<T | null> {
  const headers: Record<string, string> = {
    ...call.headers,
    Accept: "application/json",
    "Accept-Language": language,
  };
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

/** The person signed in and what they may do, as the web's buttons show it. */
export interface Me {
  name: string;
  login: string;
  department: string;
  roles: string[];
  can: { create_tasks: boolean; assign_tasks: boolean };
}

export type TaskStatus = "open" | "assigned" | "in_progress" | "done" | "cancelled";

/** The document a task opens, with the app's screen for it. */
export interface TaskDocument extends DocumentReference {
  screen: string;
}

export interface Task {
  id: number;
  name: string;
  type: string;
  status: TaskStatus;
  action: string;
  deadline: string | null;
  planned_start: string | null;
  planned_end: string | null;
  done_at: string | null;
  department: string;
  assignee: string;
  location: string;
  closed_by_system: boolean;
  document: TaskDocument | null;
}

export interface TaskStep {
  minutes: number;
  instruction: string;
  note: string;
  location: string;
}

/** A task with its note, its method's steps and the actions the person may take on it. */
export interface TaskDetail extends Task {
  note: string;
  reassign_reason: string;
  assigned_by: string;
  steps: TaskStep[];
  actions: { claim: boolean; start: boolean; done: boolean; assign: boolean };
}

/** The person's day, as the Tasks app opens on it. */
export interface TaskDay {
  person: string;
  open_count: number;
  overdue_count: number;
  due_today_count: number;
  finished_count: number;
  claimable_count: number;
  next_up: Task[];
  planned_today: Task[];
  claimable: Task[];
}

export type TaskList = "open" | "finished" | "queue";

export interface TaskPage {
  tasks: Task[];
  next_after: number | null;
}

/** The people and the departments a task may go to. */
export interface Assignees {
  people: { id: number; name: string; department: string }[];
  departments: { id: number; name: string }[];
}

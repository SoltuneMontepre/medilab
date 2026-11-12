import { memoryStore } from "./memoryStore";

export interface Sent {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

type Answer = { status: number; body?: unknown } | "unreachable";

/** Stands in for MediLab: each call gets the next answer, and every request sent is kept. */
export function fakeMediLab(...answers: Answer[]) {
  const sent: Sent[] = [];
  const queue = [...answers];
  globalThis.fetch = jest.fn((url: string, init: RequestInit) => {
    sent.push({
      url,
      method: init.method ?? "GET",
      headers: init.headers as Record<string, string>,
      body: init.body ? JSON.parse(init.body as string) : undefined,
    });
    const answer = queue.shift();
    if (answer === undefined) {
      return Promise.reject(new Error(`No answer is planned for ${url}.`));
    }
    if (answer === "unreachable") {
      return Promise.reject(new TypeError("Network request failed"));
    }
    return Promise.resolve({
      status: answer.status,
      ok: answer.status >= 200 && answer.status < 300,
      json: () => (answer.body === undefined ? Promise.reject(new SyntaxError("No body")) : Promise.resolve(answer.body)),
    } as Response);
  }) as typeof fetch;
  return { sent, plan: (...more: Answer[]) => queue.push(...more) };
}

export function refusal(status: number, code: string, message: string) {
  return { status, body: { error: { code, message } } };
}

/** Everything the app kept in the phone's secure storage. */
export function kept(): Map<string, string> {
  return memoryStore;
}

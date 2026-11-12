import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, UnreachableError } from "./api";

/** What a screen read from MediLab: still loading, read, gone (not found or no longer readable), refused with
 * MediLab's message, or not reached. */
export type Load<T> =
  | { state: "loading" }
  | { state: "ready"; value: T }
  | { state: "gone" }
  | { state: "unreachable" }
  | { state: "refused"; message: string };

const LOADING = { state: "loading" } as const;

/** What a call that failed means for the screen. A refused key has already returned the person to sign-in. */
export function failed(error: unknown): Load<never> {
  if (error instanceof UnreachableError) {
    return { state: "unreachable" };
  }
  if (error instanceof ApiError) {
    return error.code === "not_found" ? { state: "gone" } : { state: "refused", message: error.message };
  }
  throw error;
}

/** Reads what the screen shows once it opens, and again on retry, after an action changed it or when what it reads
 * changes, such as another list. Only the latest reading is shown, and nothing of a former reading meanwhile. */
export function useLoad<T>(read: () => Promise<T>) {
  const [shown, setShown] = useState<{ read: () => Promise<T>; load: Load<T> }>({ read, load: LOADING });
  const latest = useRef(0);

  const attempt = useCallback(async () => {
    latest.current += 1;
    const reading = latest.current;
    let load: Load<T>;
    try {
      load = { state: "ready", value: await read() };
    } catch (error) {
      try {
        load = failed(error);
      } catch {
        load = { state: "unreachable" };
      }
    }
    if (reading === latest.current) {
      setShown({ read, load });
    }
  }, [read]);

  useEffect(() => {
    void attempt();
    return () => {
      // A reading still under way when the screen closes or reads something else is not shown.
      latest.current += 1;
    };
  }, [attempt]);

  const reload = useCallback(async () => {
    setShown({ read, load: LOADING });
    await attempt();
  }, [read, attempt]);

  const setLoad = useCallback((load: Load<T>) => setShown({ read, load }), [read]);
  const load: Load<T> = shown.read === read ? shown.load : LOADING;
  return { load, setLoad, reload };
}

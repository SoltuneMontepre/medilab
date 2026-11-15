import { useCallback, useState } from "react";

import { ApiError } from "./api";
import { useReloadOnReturn } from "./focus";
import { failed, useLoad, type Load } from "./load";
import { useSession } from "./session";

/** Reads the record at the path of MediLab's API once the screen opens and again when the person returns to it. An
 * answer without content is a record gone. */
export function useRecord<T>(path: string) {
  const { call } = useSession();
  const read = useCallback(async () => {
    const record = await call<T>(path);
    if (!record) {
      throw new ApiError("not_found", "", 404);
    }
    return record;
  }, [call, path]);
  const loaded = useLoad(read);
  useReloadOnReturn(loaded.reload);
  return loaded;
}

/** Runs the screen's actions one at a time, and keeps why the last one did not happen with the way to try it again. */
export function useAction() {
  const [problem, setProblem] = useState<{ load: Load<never>; retry: () => void } | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async function attempt(action: () => Promise<void>) {
    setProblem(null);
    setBusy(true);
    try {
      await action();
    } catch (error) {
      setProblem({ load: failed(error), retry: () => void attempt(action) });
    } finally {
      setBusy(false);
    }
  }, []);

  return { problem, busy, run };
}

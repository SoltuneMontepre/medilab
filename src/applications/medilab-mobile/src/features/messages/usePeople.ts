import { useCallback } from "react";

import type { PersonName } from "../../api";
import { useSession } from "../../session";

/** Finds the active people of the laboratory by name, for new conversations and mentions. */
export function usePeople() {
  const { call } = useSession();
  return useCallback(
    async (query: string): Promise<PersonName[]> =>
      (await call<{ people: PersonName[] }>(`/people?q=${encodeURIComponent(query)}`))?.people ?? [],
    [call],
  );
}

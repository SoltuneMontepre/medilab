import { createContext, useCallback, useContext, useEffect, type ReactNode } from "react";
import { AppState } from "react-native";

import { UnreachableError, type Me, type ModuleList } from "./api";
import { useLoad, type Load } from "./load";
import { useSession } from "./session";

// The module whose screens are the support requests.
export const COMMERCE_MODULE = "sol_commerce";

/** The signed-in person, what they may do, and the MediLab modules installed. */
export interface Person {
  me: Me;
  modules: string[];
}

const PersonContext = createContext<{ load: Load<Person>; reload: () => Promise<void> }>({
  load: { state: "loading" },
  reload: async () => undefined,
});

/** Reads the person and the installed modules once the phone is signed in, for the navigation and the screens that
 * offer only what the person may use. A person not read, such as without a connection at start, is read again when
 * the app comes back to the foreground or a screen tries again. */
export function PersonProvider({ children }: Readonly<{ children: ReactNode }>) {
  const { call } = useSession();
  const read = useCallback(async (): Promise<Person> => {
    const [me, installed] = await Promise.all([call<Me>("/me"), call<ModuleList>("/modules")]);
    if (!me || !installed) {
      throw new UnreachableError();
    }
    return { me, modules: installed.modules };
  }, [call]);
  const { load, reload, refresh } = useLoad(read);
  const unread = load.state !== "ready";

  useEffect(() => {
    const foreground = AppState.addEventListener("change", (state) => state === "active" && unread && void refresh());
    return () => foreground.remove();
  }, [unread, refresh]);

  return <PersonContext.Provider value={{ load, reload }}>{children}</PersonContext.Provider>;
}

/** Reads the person again when they were not read, such as when a screen tries again after MediLab was not reached. */
export function useRetryPerson(): () => void {
  const { load, reload } = useContext(PersonContext);
  return useCallback(() => {
    if (load.state !== "ready") {
      void reload();
    }
  }, [load.state, reload]);
}

export function usePerson() {
  return useContext(PersonContext);
}

/** The person once read, or null while they are not. */
export function usePersonRead(): Person | null {
  const { load } = usePerson();
  return load.state === "ready" ? load.value : null;
}

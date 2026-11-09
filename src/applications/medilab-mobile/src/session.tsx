import * as Device from "expo-device";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Platform } from "react-native";

import { ApiError, callApi, UnreachableError, type Call, type SignedIn } from "./api";
import { serverUrl as builtInServerUrl } from "./config";
import { isLocale, type Locale } from "./i18n";
import { LocaleProvider } from "./locale";
import { normalizeServerUrl } from "./server";
import { installationId, read, remove, write } from "./storage";

export type SessionStatus = "loading" | "signedOut" | "signedIn";

export interface Session {
  status: SessionStatus;
  serverUrl: string;
  language: Locale;
  setLanguage(language: Locale): Promise<void>;
  /** Signs the phone in on the server and keeps the server and the phone's device key; the password is only sent. */
  signIn(server: string, login: string, password: string): Promise<void>;
  /** Signs the phone out on MediLab, which turns its push token off, then removes its key. */
  signOut(): Promise<void>;
  /** Calls MediLab with the phone's key. A refused key is removed and the person returns to sign-in. */
  call<T>(path: string, call?: Omit<Call, "key">): Promise<T | null>;
}

const SessionContext = createContext<Session | null>(null);

// The name a phone signs in with is one name, never a path.
function phoneName(): string {
  return (Device.modelName ?? "").replace(/[/\\:]/g, " ").trim() || "Phone";
}

/** Keeps the phone's session: its server, its language and its device key, all in secure storage. */
export function SessionProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [serverUrl, setServerUrl] = useState(builtInServerUrl);
  const [language, setLanguage] = useState<Locale>("vi");
  const [key, setKey] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.all([read("serverUrl"), read("language"), read("deviceKey")])
      .then(([url, lang, kept]) => {
        if (!mounted) {
          return;
        }
        if (url) {
          setServerUrl(url);
        }
        if (isLocale(lang)) {
          setLanguage(lang);
        }
        setKey(kept);
        setStatus(kept ? "signedIn" : "signedOut");
      })
      // Secure storage the app cannot read leaves the phone signed out.
      .catch(() => mounted && setStatus("signedOut"));
    return () => {
      mounted = false;
    };
  }, []);

  const forgetKey = useCallback(async () => {
    await remove("deviceKey");
    setKey(null);
    setStatus("signedOut");
  }, []);

  const keepLanguage = useCallback(async (chosen: Locale) => {
    await write("language", chosen);
    setLanguage(chosen);
  }, []);

  const signIn = useCallback(
    async (server: string, login: string, password: string) => {
      const url = normalizeServerUrl(server);
      const signedIn = await callApi<SignedIn>(url, language, "/sign-in", {
        method: "POST",
        body: {
          login,
          password,
          client_uid: await installationId(),
          name: phoneName(),
          platform: Platform.OS === "ios" ? "ios" : "android",
        },
      });
      if (!signedIn) {
        throw new UnreachableError();
      }
      await write("serverUrl", url);
      await write("deviceKey", signedIn.key);
      setServerUrl(url);
      setKey(signedIn.key);
      setStatus("signedIn");
    },
    [language],
  );

  const call = useCallback(
    async <T,>(path: string, request: Omit<Call, "key"> = {}): Promise<T | null> => {
      try {
        return await callApi<T>(serverUrl, language, path, { ...request, key });
      } catch (error) {
        if (error instanceof ApiError && error.code === "invalid_key") {
          await forgetKey();
        }
        throw error;
      }
    },
    [serverUrl, language, key, forgetKey],
  );

  const signOut = useCallback(async () => {
    try {
      await call("/sign-out", { method: "POST" });
    } catch (error) {
      // A key MediLab no longer takes is already signed out, and call() has removed it.
      if (!(error instanceof ApiError && error.code === "invalid_key")) {
        throw error;
      }
      return;
    }
    await forgetKey();
  }, [call, forgetKey]);

  const session = useMemo<Session>(
    () => ({ status, serverUrl, language, setLanguage: keepLanguage, signIn, signOut, call }),
    [status, serverUrl, language, keepLanguage, signIn, signOut, call],
  );
  return (
    <SessionContext.Provider value={session}>
      <LocaleProvider locale={language}>{children}</LocaleProvider>
    </SessionContext.Provider>
  );
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) {
    throw new Error("useSession is used outside SessionProvider.");
  }
  return session;
}

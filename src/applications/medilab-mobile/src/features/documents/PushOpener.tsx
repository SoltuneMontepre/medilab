import { router } from "expo-router";
import { useEffect } from "react";

import { watchOpenedPushes } from "../../push";
import { useSession } from "../../session";
import { documentPath } from "./documentPath";

/** Opens the document of a push the person taps, once the phone is signed in. */
export function PushOpener() {
  const { status } = useSession();
  useEffect(() => {
    if (status !== "signedIn") {
      return;
    }
    return watchOpenedPushes((document) => router.push(documentPath(document)));
  }, [status]);
  return null;
}

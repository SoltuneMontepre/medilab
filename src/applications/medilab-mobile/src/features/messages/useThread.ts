import { useCallback, useEffect, useRef, useState } from "react";

import type { Message, MessagePage } from "../../api";
import { failed, type Load } from "../../load";
import { useSession } from "../../session";

// How many messages MediLab gives in a page when the app names no limit.
const PAGE_SIZE = 30;

// The messages oldest first, each once.
function merged(kept: Message[], read: Message[]): Message[] {
  const byId = new Map(kept.map((message) => [message.id, message]));
  read.forEach((message) => byId.set(message.id, message));
  return [...byId.values()].sort((first, second) => first.id - second.id);
}

function loadOf(error: unknown): Load<never> {
  try {
    return failed(error);
  } catch {
    return { state: "unreachable" };
  }
}

/** The messages of a conversation or of a document's chatter at the path, oldest first: read when the screen opens,
 * older pages when the person asks, newer messages when the screen asks, such as on a push or while a conversation is
 * open, and a message the person posted. */
export function useThread(path: string) {
  const { call } = useSession();
  const [load, setLoad] = useState<Load<Message[]>>({ state: "loading" });
  const [hasOlder, setHasOlder] = useState(false);
  const shown = useRef<Message[]>([]);

  const show = useCallback((messages: Message[]) => {
    shown.current = messages;
    setLoad({ state: "ready", value: messages });
  }, []);

  const page = useCallback(
    async (query: string) => (await call<MessagePage>(path + query))?.messages ?? [],
    [call, path],
  );

  const showFirst = useCallback(
    (messages: Message[]) => {
      setHasOlder(messages.length >= PAGE_SIZE);
      show(merged([], messages));
    },
    [show],
  );

  useEffect(() => {
    let current = true;
    page("")
      .then((messages) => current && showFirst(messages))
      .catch((error: unknown) => current && setLoad(loadOf(error)));
    return () => {
      current = false;
    };
  }, [page, showFirst]);

  const read = useCallback(async () => {
    setLoad({ state: "loading" });
    try {
      showFirst(await page(""));
    } catch (error) {
      setLoad(loadOf(error));
    }
  }, [page, showFirst]);

  // A newer message the screen could not read now is read at the next push or the next poll.
  const newer = useCallback(async () => {
    const newest = shown.current.at(-1);
    try {
      show(merged(shown.current, await page(newest ? `?after=${newest.id}` : "")));
    } catch {
      // Read again at the next push or poll.
    }
  }, [page, show]);

  const older = useCallback(async () => {
    const oldest = shown.current[0];
    if (!oldest) {
      return;
    }
    try {
      const messages = await page(`?before=${oldest.id}`);
      setHasOlder(messages.length >= PAGE_SIZE);
      show(merged(shown.current, messages));
    } catch (error) {
      setLoad(loadOf(error));
    }
  }, [page, show]);

  const add = useCallback((message: Message) => show(merged(shown.current, [message])), [show]);

  return { load, hasOlder, read, newer, older, add };
}

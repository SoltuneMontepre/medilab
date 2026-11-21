import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { AppState } from "react-native";

import type { Conversation, NotificationPage } from "./api";
import { watchPushes } from "./push";
import { useSession } from "./session";

/** The unread marks of the navigation: how many conversation messages the person has not read, and whether a
 * notification is unread. */
export interface Badges {
  conversations: number;
  notifications: boolean;
  /** Reads the marks again, such as after the person read a notification or a conversation. */
  refresh(): void;
  /** Takes the unread messages of the conversations a screen has just read. */
  showConversations(conversations: Conversation[]): void;
}

const BadgeContext = createContext<Badges>({
  conversations: 0,
  notifications: false,
  refresh: () => undefined,
  showConversations: () => undefined,
});

function unreadMessages(conversations: Conversation[]): number {
  return conversations.reduce((total, conversation) => total + conversation.unread, 0);
}

/** Keeps the unread marks, read when the app opens, comes back to the foreground or gets a push. The notifications come
 * unread first, so the first one says whether any is unread. */
export function BadgeProvider({ children }: Readonly<{ children: ReactNode }>) {
  const { call } = useSession();
  const [conversations, setConversations] = useState(0);
  const [notifications, setNotifications] = useState(false);

  const refresh = useCallback(() => {
    call<{ conversations: Conversation[] }>("/conversations")
      .then((answer) => setConversations(unreadMessages(answer?.conversations ?? [])))
      .catch(() => undefined);
    call<NotificationPage>("/notifications?limit=1")
      .then((answer) => setNotifications(!!answer?.notifications.some((notification) => !notification.read)))
      .catch(() => undefined);
  }, [call]);

  useEffect(() => {
    refresh();
    const foreground = AppState.addEventListener("change", (state) => state === "active" && refresh());
    const pushed = watchPushes(refresh);
    return () => {
      foreground.remove();
      pushed();
    };
  }, [refresh]);

  const badges = useMemo<Badges>(
    () => ({
      conversations,
      notifications,
      refresh,
      showConversations: (list) => setConversations(unreadMessages(list)),
    }),
    [conversations, notifications, refresh],
  );
  return <BadgeContext.Provider value={badges}>{children}</BadgeContext.Provider>;
}

export function useBadges(): Badges {
  return useContext(BadgeContext);
}

import type { Conversation, Message } from "../api";

// The conversations of demo.tester: the morning shift of Chemistry and its people.
export const HEAD = { id: 21, name: "Hoang Van Minh" };
export const CHEMIST = { id: 22, name: "Ly Van Hung" };

export function message(values: Partial<Message> = {}): Message {
  return {
    id: 101,
    author: HEAD.name,
    mine: false,
    date: "2026-11-16T01:30:00+00:00",
    text: "Sáng nay ưu tiên các mẫu nước uống đóng chai.",
    note: false,
    attachments: [],
    ...values,
  };
}

export function conversation(values: Partial<Conversation> = {}): Conversation {
  return {
    id: 5,
    type: "group",
    name: "Hóa – ca sáng",
    unread: 2,
    muted: false,
    members: [HEAD, CHEMIST],
    last_message: message(),
    ...values,
  };
}

export function page(...messages: Message[]) {
  return { status: 200, body: { messages } };
}

export function conversations(...listed: Conversation[]) {
  return { status: 200, body: { conversations: listed } };
}

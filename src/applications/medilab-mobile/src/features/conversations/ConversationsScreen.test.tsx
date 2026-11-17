import { act, fireEvent, screen } from "@testing-library/react-native";
import { router } from "expo-router";

import { conversation, conversations, message } from "../../testing/conversations";
import { fakeMediLab, kept } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { ConversationsScreen } from "./ConversationsScreen";

// The test-only controls of the mocked Firebase Cloud Messaging.
const messaging = jest.requireMock("@react-native-firebase/messaging");

jest.mock("@react-native-firebase/messaging");
jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ router: { push: jest.fn() }, useFocusEffect: jest.fn() }));

const MUTED = conversation({
  id: 6,
  type: "chat",
  name: "Hoang Van Minh",
  unread: 0,
  muted: true,
  last_message: message({ id: 99, mine: true, text: "Dạ em chạy lại ngay." }),
});

describe("ConversationsScreen", () => {
  beforeEach(() => {
    kept().clear();
    messaging.resetMessaging();
    jest.mocked(router.push).mockClear();
  });

  it("lists the conversations with their unread messages and whether they are muted", async () => {
    fakeMediLab(conversations(conversation(), MUTED));
    await renderSignedIn(<ConversationsScreen />);

    expect(await screen.findByRole("button", { name: "Hóa – ca sáng, 2 tin chưa đọc" })).toBeOnTheScreen();
    expect(screen.getByRole("button", { name: "Hoang Van Minh, Đã tắt thông báo" })).toBeOnTheScreen();
    expect(screen.getByText("Bạn: Dạ em chạy lại ngay.")).toBeOnTheScreen();
  });

  it("opens a conversation and starts a new one", async () => {
    fakeMediLab(conversations(conversation()));
    await renderSignedIn(<ConversationsScreen />);

    await fireEvent.press(await screen.findByTestId("conversation-5"));
    await fireEvent.press(screen.getByTestId("conversations-new"));

    expect(router.push).toHaveBeenCalledWith({ pathname: "/conversations/[id]", params: { id: "5" } });
    expect(router.push).toHaveBeenCalledWith("/conversations/new");
  });

  it("reads the list again when a message is pushed", async () => {
    const mediLab = fakeMediLab(conversations(conversation({ unread: 0 })));
    await renderSignedIn(<ConversationsScreen />);
    expect(await screen.findByRole("button", { name: "Hóa – ca sáng" })).toBeOnTheScreen();

    mediLab.plan(conversations(conversation({ unread: 1 })));
    await act(() => messaging.receivePush({ data: { event: "message", model: "discuss.channel", id: "5" } }));

    expect(await screen.findByRole("button", { name: "Hóa – ca sáng, 1 tin chưa đọc" })).toBeOnTheScreen();
    expect(mediLab.sent).toHaveLength(2);
  });

  it("says when the person has none", async () => {
    fakeMediLab(conversations());
    await renderSignedIn(<ConversationsScreen />);

    expect(await screen.findByText("Bạn chưa có cuộc trò chuyện nào.")).toBeOnTheScreen();
  });
});

import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { useLocalSearchParams } from "expo-router";

import { CHEMIST, conversation, conversations, message, page } from "../../testing/conversations";
import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { scrollingParent } from "../../testing/scrolling";
import { ConversationScreen, POLL_MILLISECONDS } from "./ConversationScreen";

// The test-only controls of the mocked Firebase Cloud Messaging, camera and gallery, and phone's files.
const messaging = jest.requireMock("@react-native-firebase/messaging");
const picker = jest.requireMock("expo-image-picker");
const documents = jest.requireMock("expo-document-picker");

jest.mock("@react-native-firebase/messaging");
jest.mock("expo-image-picker");
jest.mock("expo-document-picker");
jest.mock("expo-file-system");
jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const URL = "https://lab.example/medilab/api/v1/conversations/5";
const FIRST = message({ id: 101 });
const SECOND = message({ id: 102, author: CHEMIST.name, text: "Chai acetonitrile mới đã mở." });
const SEEN = { status: 204 };

async function open(...answers: Parameters<typeof fakeMediLab>) {
  const mediLab = fakeMediLab(page(SECOND, FIRST), conversations(conversation()), SEEN, ...answers);
  await renderSignedIn(<ConversationScreen />);
  expect(await screen.findByText("Chai acetonitrile mới đã mở.")).toBeOnTheScreen();
  return mediLab;
}

describe("ConversationScreen", () => {
  beforeEach(() => {
    kept().clear();
    messaging.resetMessaging();
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "5" });
  });

  it("shows the messages oldest first and marks them read up to the newest", async () => {
    const mediLab = await open();

    expect(screen.getAllByTestId(/^message-\d+$/).map((item) => item.props.testID)).toEqual([
      "message-101",
      "message-102",
    ]);
    expect(await screen.findByText("Hóa – ca sáng")).toBeOnTheScreen();
    await waitFor(() => expect(mediLab.sent).toHaveLength(3));
    expect(mediLab.sent[2]).toMatchObject({ method: "POST", url: `${URL}/seen`, body: { message_id: 102 } });
  });

  it("reads the new messages when one is pushed", async () => {
    const mediLab = await open(page(message({ id: 103, text: "Máy HPLC số 2 đã xong." })), SEEN);

    await act(() => messaging.receivePush({ data: { event: "message", model: "discuss.channel", id: "5" } }));

    expect(await screen.findByText("Máy HPLC số 2 đã xong.")).toBeOnTheScreen();
    expect(mediLab.sent[3].url).toBe(`${URL}/messages?after=102`);
  });

  it("asks for new messages about every 10 seconds while it is open", async () => {
    jest.useFakeTimers();
    try {
      const mediLab = await open(page());
      await act(() => jest.advanceTimersByTime(POLL_MILLISECONDS));
      await waitFor(() => expect(mediLab.sent.at(-1)?.url).toBe(`${URL}/messages?after=102`));
    } finally {
      jest.useRealTimers();
    }
  });

  it("sends a message that mentions a member, with a photo and a file, once per key", async () => {
    picker.nextPhoto({ base64: "cGhvdG8=", fileName: "spinach.jpg", mimeType: "image/jpeg" });
    documents.nextDocument({ name: "worksheet.pdf", mimeType: "application/pdf", content: "PDF" });
    const posted = message({ id: 104, mine: true, text: "@Ly Van Hung xem ảnh" });
    const mediLab = await open(refusal(413, "too_large", "worksheet.pdf lớn hơn 10 MiB."), {
      status: 200,
      body: posted,
    });

    await fireEvent.changeText(screen.getByTestId("message-text"), "@Ly");
    await fireEvent.press(await screen.findByTestId(`mention-${CHEMIST.id}`));
    await fireEvent.changeText(screen.getByTestId("message-text"), "@Ly Van Hung xem ảnh");
    await fireEvent.press(screen.getByTestId("attach-camera"));
    await fireEvent.press(screen.getByTestId("attach-file"));
    await fireEvent.press(await screen.findByTestId("attached-1"));
    documents.nextDocument({ name: "worksheet.pdf", mimeType: "application/pdf", content: "PDF" });
    await fireEvent.press(screen.getByTestId("attach-file"));
    await screen.findByTestId("attached-1");
    await fireEvent.press(screen.getByTestId("message-send"));
    expect(await screen.findByText("worksheet.pdf lớn hơn 10 MiB.")).toBeOnTheScreen();
    await fireEvent.press(screen.getByTestId("message-send"));

    expect(await screen.findByText("@Ly Van Hung xem ảnh")).toBeOnTheScreen();
    const [refused, sent] = mediLab.sent.slice(3);
    expect(sent).toMatchObject({
      method: "POST",
      url: `${URL}/messages`,
      body: {
        text: "@Ly Van Hung xem ảnh",
        mentions: [CHEMIST.id],
        files: [
          { name: "spinach.jpg", mimetype: "image/jpeg", data: "cGhvdG8=" },
          { name: "worksheet.pdf", mimetype: "application/pdf", data: btoa("PDF") },
        ],
      },
    });
    expect(sent.headers["Idempotency-Key"]).toBe(refused.headers["Idempotency-Key"]);
    expect(screen.getByTestId("message-text").props.value).toBe("");
  });

  it("chooses a suggested member with the tap that closes the keyboard", async () => {
    await open();

    await fireEvent.changeText(screen.getByTestId("message-text"), "@Ly");
    const suggestion = await screen.findByTestId(`mention-${CHEMIST.id}`);

    expect(scrollingParent(suggestion)).toHaveProp("keyboardShouldPersistTaps", "handled");
  });

  it("mutes and unmutes the conversation", async () => {
    const mediLab = await open({ status: 200, body: conversation({ muted: true }) });

    await fireEvent.press(await screen.findByTestId("conversation-mute"));

    expect(mediLab.sent[3]).toMatchObject({ method: "PUT", url: `${URL}/mute`, body: { muted: true } });
    expect(await screen.findByRole("button", { name: "Bật lại thông báo" })).toBeOnTheScreen();
  });

  it("says when the person is no longer in the conversation", async () => {
    fakeMediLab(refusal(404, "not_found", "Không tìm thấy."), conversations());
    await renderSignedIn(<ConversationScreen />);

    expect(await screen.findByText("Bạn không còn ở trong cuộc trò chuyện này.")).toBeOnTheScreen();
  });
});

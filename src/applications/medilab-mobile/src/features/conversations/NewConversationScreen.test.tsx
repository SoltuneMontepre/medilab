import { fireEvent, screen } from "@testing-library/react-native";
import { router } from "expo-router";

import { CHEMIST, conversation, HEAD } from "../../testing/conversations";
import { fakeMediLab, kept } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { scrollingParent } from "../../testing/scrolling";
import { NewConversationScreen } from "./NewConversationScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ router: { push: jest.fn(), replace: jest.fn() } }));

const API = "https://lab.example/medilab/api/v1";
const PEOPLE = { status: 200, body: { people: [HEAD, CHEMIST] } };

describe("NewConversationScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(router.replace).mockClear();
  });

  it("opens the direct conversation with one person", async () => {
    const mediLab = fakeMediLab(PEOPLE, { status: 200, body: conversation({ id: 6, type: "chat", name: HEAD.name }) });
    await renderSignedIn(<NewConversationScreen />);

    await fireEvent.press(await screen.findByTestId(`person-${HEAD.id}`));
    await fireEvent.press(screen.getByRole("button", { name: "Nhắn riêng" }));

    expect(mediLab.sent[0].url).toBe(`${API}/people?q=`);
    expect(mediLab.sent[1]).toMatchObject({
      method: "POST",
      url: `${API}/conversations`,
      body: { person_id: HEAD.id },
    });
    expect(router.replace).toHaveBeenCalledWith({ pathname: "/conversations/[id]", params: { id: "6" } });
  });

  it("creates a group of several people with its name, once per key", async () => {
    const mediLab = fakeMediLab(PEOPLE, { status: 200, body: conversation() });
    await renderSignedIn(<NewConversationScreen />);

    await fireEvent.press(await screen.findByTestId(`person-${HEAD.id}`));
    await fireEvent.press(screen.getByTestId(`person-${CHEMIST.id}`));
    await fireEvent.changeText(screen.getByTestId("group-name"), "Hóa – ca sáng");
    await fireEvent.press(screen.getByTestId("conversation-start"));

    expect(mediLab.sent[1]).toMatchObject({
      method: "POST",
      url: `${API}/conversations`,
      body: { name: "Hóa – ca sáng", member_ids: [HEAD.id, CHEMIST.id] },
    });
    expect(mediLab.sent[1].headers["Idempotency-Key"]).toBeTruthy();
    expect(router.replace).toHaveBeenCalledWith({ pathname: "/conversations/[id]", params: { id: "5" } });
  });

  it("finds people by name and starts nothing until someone is chosen", async () => {
    const mediLab = fakeMediLab(PEOPLE, { status: 200, body: { people: [CHEMIST] } });
    await renderSignedIn(<NewConversationScreen />);

    await fireEvent.changeText(await screen.findByTestId("people-search"), "Ly");

    const found = await screen.findByTestId(`person-${CHEMIST.id}`);
    expect(found).toBeOnTheScreen();
    // The tap that closes the keyboard also chooses the person.
    expect(scrollingParent(found)).toHaveProp("keyboardShouldPersistTaps", "handled");
    expect(screen.queryByTestId(`person-${HEAD.id}`)).toBeNull();
    expect(mediLab.sent[1].url).toBe(`${API}/people?q=Ly`);
    expect(screen.getByTestId("conversation-start")).toBeDisabled();
  });
});

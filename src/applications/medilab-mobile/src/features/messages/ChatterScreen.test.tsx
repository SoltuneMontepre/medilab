import { fireEvent, screen } from "@testing-library/react-native";
import { useLocalSearchParams } from "expo-router";

import { HEAD, message, page } from "../../testing/conversations";
import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { ChatterScreen } from "./ChatterScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ useLocalSearchParams: jest.fn() }));

const URL = "https://lab.example/medilab/api/v1/documents/medilab.sample/12";
const NOTE = message({ id: 201, note: true, text: "@Dang Thi Lan Mẫu này cần đồng nhất lại." });

describe("ChatterScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ model: "medilab.sample", id: "12", code: "MS-2026-0042" });
  });

  it("shows the sample's chatter with its notes", async () => {
    const mediLab = fakeMediLab(page(NOTE));
    await renderSignedIn(<ChatterScreen />);

    expect(await screen.findByText("Trao đổi về MS-2026-0042")).toBeOnTheScreen();
    expect(screen.getByText(`${HEAD.name} · Ghi chú nội bộ`)).toBeOnTheScreen();
    expect(mediLab.sent[0].url).toBe(`${URL}/messages`);
    expect(screen.queryByTestId("attach-camera")).toBeNull();
  });

  it("posts a note that mentions a person found by name", async () => {
    const posted = message({ id: 202, mine: true, note: true, text: "@Hoang Van Minh đã đồng nhất" });
    const mediLab = fakeMediLab(page(), { status: 200, body: { people: [HEAD] } }, { status: 200, body: posted });
    await renderSignedIn(<ChatterScreen />);

    await fireEvent.changeText(await screen.findByTestId("message-text"), "@Hoa");
    await fireEvent.press(await screen.findByTestId(`mention-${HEAD.id}`));
    await fireEvent.changeText(screen.getByTestId("message-text"), "@Hoang Van Minh đã đồng nhất");
    await fireEvent.press(screen.getByTestId("message-send"));

    expect(await screen.findByText("@Hoang Van Minh đã đồng nhất")).toBeOnTheScreen();
    expect(mediLab.sent[1].url).toBe("https://lab.example/medilab/api/v1/people?q=Hoa");
    expect(mediLab.sent[2]).toMatchObject({
      method: "POST",
      url: `${URL}/notes`,
      body: { text: "@Hoang Van Minh đã đồng nhất", mentions: [HEAD.id] },
    });
  });

  it("says when the person can no longer see the document", async () => {
    fakeMediLab(refusal(404, "not_found", "Không tìm thấy."));
    await renderSignedIn(<ChatterScreen />);

    expect(await screen.findByText("Bạn không còn xem được tài liệu này, hoặc tài liệu đã bị xoá.")).toBeOnTheScreen();
  });
});

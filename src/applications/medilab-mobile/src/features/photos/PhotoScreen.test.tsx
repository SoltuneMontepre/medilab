import { fireEvent, screen } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { memoryFiles } from "../../testing/memoryFiles";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { PhotoScreen } from "./PhotoScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { back: jest.fn() },
  // The screen is shown as soon as it renders, so its camera runs.
  useFocusEffect: (effect: () => void) => jest.requireActual<typeof import("react")>("react").useEffect(effect, [effect]),
  useLocalSearchParams: jest.fn(),
}));

const API = "https://lab.example/medilab/api/v1";
const SENT = {
  id: 7,
  name: "PTN.2026.0042.jpg",
  mimetype: "image/jpeg",
  created_at: "2026-11-16T03:00:00Z",
  created_by: "Lê Thị Lan",
};

function unsentFiles(): string[] {
  return [...memoryFiles.keys()].filter((uri) => uri.includes("/unsent-photos/"));
}

describe("PhotoScreen", () => {
  beforeEach(() => {
    kept().clear();
    memoryFiles.clear();
    jest.mocked(router.back).mockClear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "42", code: "PTN.2026.0042" });
  });

  it("sends the photo to the sample with its own Idempotency-Key and leaves nothing on the phone", async () => {
    const mediLab = fakeMediLab({ status: 200, body: SENT });
    await renderSignedIn(<PhotoScreen />);

    await fireEvent.press(await screen.findByTestId("photo-shutter"));

    expect(mediLab.sent[0]).toMatchObject({
      method: "POST",
      url: `${API}/samples/42/photos`,
      body: { mimetype: "image/jpeg", data: btoa("photo of the sample") },
    });
    expect(mediLab.sent[0].body).toMatchObject({ name: expect.stringMatching(/^PTN\.2026\.0042-[\dTZ-]+\.jpg$/) });
    expect(mediLab.sent[0].headers["Idempotency-Key"]).toMatch(/^[\w-]+$/);
    expect(router.back).toHaveBeenCalled();
    expect(unsentFiles()).toEqual([]);
  });

  it("keeps a photo on the phone when MediLab cannot be reached", async () => {
    fakeMediLab("unreachable");
    await renderSignedIn(<PhotoScreen />);

    await fireEvent.press(await screen.findByTestId("photo-shutter"));

    expect(
      await screen.findByText(
        "Ảnh chưa gửi được nên vẫn lưu trên điện thoại. Gửi lại hoặc bỏ ảnh ở màn hình mẫu.",
      ),
    ).toBeOnTheScreen();
    expect(unsentFiles()).toHaveLength(2);
    expect(router.back).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByTestId("photo-back"));
    expect(router.back).toHaveBeenCalled();
  });

  it("shows why MediLab refused the photo, which stays on the phone", async () => {
    fakeMediLab(refusal(413, "too_large", "Ảnh tối đa 10 MiB."));
    await renderSignedIn(<PhotoScreen />);

    await fireEvent.press(await screen.findByTestId("photo-shutter"));

    expect(await screen.findByText("Ảnh tối đa 10 MiB.")).toBeOnTheScreen();
    expect(unsentFiles()).toHaveLength(2);
  });
});

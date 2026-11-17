import { fireEvent, screen } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";

import { fakeMediLab, kept } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { supportRequest } from "../../testing/support";
import { SupportRequestsScreen } from "./SupportRequestsScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const API = "https://lab.example/medilab/api/v1";

describe("SupportRequestsScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(router.push).mockClear();
    jest.mocked(useLocalSearchParams).mockReturnValue({});
  });

  it("lists the requests the person handles, then those waiting to be taken", async () => {
    const mediLab = fakeMediLab(
      { status: 200, body: { requests: [] } },
      { status: 200, body: { requests: [supportRequest()] } },
    );
    await renderSignedIn(<SupportRequestsScreen />);

    expect(await screen.findByText("Bạn không xử lý yêu cầu nào đang mở.")).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("tab", { name: "Chờ nhận xử lý" }));

    const row = await screen.findByRole("button", {
      name: "Khi nào có kết quả mẫu nước đóng chai?, HT.0005, Công ty Nước Sạch, Mở",
    });
    expect(mediLab.sent.map((sent) => sent.url)).toEqual([
      `${API}/support-requests?list=mine`,
      `${API}/support-requests?list=waiting`,
    ]);
    await fireEvent.press(row);
    expect(router.push).toHaveBeenCalledWith({ pathname: "/support/[id]", params: { id: "5" } });
  });

  it("says when the person may not see support requests", async () => {
    fakeMediLab({ status: 404, body: { error: { code: "not_found", message: "" } } });
    await renderSignedIn(<SupportRequestsScreen />);

    expect(await screen.findByText("Bạn không xem được yêu cầu hỗ trợ.")).toBeOnTheScreen();
  });
});

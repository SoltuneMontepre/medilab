import { fireEvent, screen } from "@testing-library/react-native";
import { router } from "expo-router";

import { sent } from "../../testing/bench";
import { fakeMediLab, kept } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { ResultsScreen } from "./ResultsScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useFocusEffect: jest.fn(),
}));

const API = "https://lab.example/medilab/api/v1";
const WARNED = sent({ id: 32, code: "PTN.2026.0043", value_display: "0,0095 mg/L", warned: true });

describe("ResultsScreen", () => {
  beforeEach(() => {
    kept().clear();
  });

  it("lists the results waiting for the head, page by page, and opens one", async () => {
    const mediLab = fakeMediLab(
      { status: 200, body: { results: [sent()], next_after: 1 } },
      { status: 200, body: { results: [WARNED], next_after: null } },
    );
    await renderSignedIn(<ResultsScreen />);

    expect(await screen.findByText("PTN.2026.0042 – Chì (Pb)")).toBeOnTheScreen();
    await fireEvent(screen.getByTestId("record-list"), "endReached");
    const warned = await screen.findByRole("button", { name: /PTN.2026.0043, Chì \(Pb\), 0,0095 mg\/L, Có cảnh báo/ });

    expect(mediLab.sent.map(({ url }) => url)).toEqual([
      `${API}/results?awaiting=me`,
      `${API}/results?awaiting=me&after=1`,
    ]);
    const asked = mediLab.sent.length;
    await fireEvent(screen.getByTestId("record-list"), "endReached");
    expect(mediLab.sent).toHaveLength(asked);
    await fireEvent.press(warned);
    expect(router.push).toHaveBeenCalledWith({ pathname: "/results/[id]", params: { id: "32" } });
  });

  it("says when no result waits for the person", async () => {
    fakeMediLab({ status: 200, body: { results: [], next_after: null } });
    await renderSignedIn(<ResultsScreen />);

    expect(await screen.findByText("Không có kết quả nào chờ bạn ký.")).toBeOnTheScreen();
  });
});

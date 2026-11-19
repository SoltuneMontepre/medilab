import { fireEvent, screen } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";

import { fakeMediLab, kept } from "../../testing/fakeMediLab";
import { draftRecord, signedRecord } from "../../testing/handover";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { HandoverRecordsScreen } from "./HandoverRecordsScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const API = "https://lab.example/medilab/api/v1";

describe("HandoverRecordsScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(useLocalSearchParams).mockReturnValue({});
  });

  it("lists the records waiting for the customer's signature and the signed ones, and opens one", async () => {
    const mediLab = fakeMediLab(
      { status: 200, body: { records: [draftRecord()], next_after: null } },
      { status: 200, body: { records: [signedRecord({ id: 13, code: "BBGN.2026.0001" })], next_after: null } },
    );
    await renderSignedIn(<HandoverRecordsScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "BBGN.2026.0004, YC.2026.0007, Trần Văn Bình" }));
    expect(router.push).toHaveBeenCalledWith({ pathname: "/handover-records/[id]", params: { id: "12" } });
    await fireEvent.press(screen.getByRole("tab", { name: "Đã ký" }));

    expect(await screen.findByText("BBGN.2026.0001")).toBeOnTheScreen();
    expect(mediLab.sent.map((sent) => sent.url)).toEqual([
      `${API}/handover-records?status=draft`,
      `${API}/handover-records?status=signed`,
    ]);
  });
});

import { fireEvent, screen } from "@testing-library/react-native";
import { useLocalSearchParams } from "expo-router";
import { Linking } from "react-native";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { DocumentScreen } from "./DocumentScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ useLocalSearchParams: jest.fn() }));

const SAMPLE = {
  model: "medilab.sample",
  id: 12,
  code: "MS-2026-0042",
  title: "MS-2026-0042",
  screen: "sample",
  url: "https://lab.example/odoo/medilab.sample/12",
};

describe("DocumentScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ model: "medilab.sample", id: "12" });
  });

  it("opens the document a push names, read with the person's key", async () => {
    const mediLab = fakeMediLab({ status: 200, body: SAMPLE });
    const openURL = jest.spyOn(Linking, "openURL").mockResolvedValue(undefined);
    await renderSignedIn(<DocumentScreen />);

    expect(await screen.findByText("MS-2026-0042")).toBeOnTheScreen();
    expect(mediLab.sent[0]).toMatchObject({
      url: "https://lab.example/medilab/api/v1/documents/medilab.sample/12",
      headers: { Authorization: "Bearer device-key" },
    });
    await fireEvent.press(screen.getByRole("button", { name: "Mở trên web" }));
    expect(openURL).toHaveBeenCalledWith(SAMPLE.url);
  });

  it("says so when the person can no longer see the document", async () => {
    fakeMediLab(refusal(404, "not_found", "Không tìm thấy gì ở địa chỉ này."));
    await renderSignedIn(<DocumentScreen />);

    expect(
      await screen.findByText("Bạn không còn xem được tài liệu này, hoặc tài liệu đã bị xoá."),
    ).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Mở trên web" })).toBeNull();
  });
});

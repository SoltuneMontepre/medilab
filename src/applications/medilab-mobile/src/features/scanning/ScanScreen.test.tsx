import { fireEvent, screen } from "@testing-library/react-native";
import { useCameraPermissions } from "expo-camera";
import { router } from "expo-router";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { sample } from "../../testing/sample";
import { ScanScreen } from "./ScanScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  // The screen is shown as soon as it opens.
  useFocusEffect: (effect: () => () => void) => jest.requireActual<typeof import("react")>("react").useEffect(effect, [effect]),
}));

const LOOKUP = "https://lab.example/medilab/api/v1/samples/lookup?code=";
const GRANTED = jest.mocked(useCameraPermissions).getMockImplementation();

describe("ScanScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(router.push).mockClear();
    jest.mocked(useCameraPermissions).mockImplementation(GRANTED);
  });

  it("opens the sample of a label the camera reads, once while the label stays in front of it", async () => {
    const mediLab = fakeMediLab({ status: 200, body: sample() });
    await renderSignedIn(<ScanScreen />);

    const camera = await screen.findByTestId("camera");
    await fireEvent(camera, "barcodeScanned", { data: "PTN.2026.0042", type: "qr" });
    await fireEvent(camera, "barcodeScanned", { data: "PTN.2026.0042", type: "qr" });

    expect(mediLab.sent.map((sent) => sent.url)).toEqual([`${LOOKUP}PTN.2026.0042`]);
    expect(router.push).toHaveBeenCalledWith({ pathname: "/samples/[id]", params: { id: "42" } });
  });

  it("opens the sample of a typed lab code when the label cannot be read", async () => {
    const mediLab = fakeMediLab({ status: 200, body: sample() });
    await renderSignedIn(<ScanScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Mở mẫu" }));
    expect(screen.getByText("Nhập mã PTN trên tem mẫu.")).toBeOnTheScreen();
    await fireEvent.changeText(screen.getByLabelText("Mã PTN"), " PTN.2026.0042 ");
    await fireEvent.press(screen.getByRole("button", { name: "Mở mẫu" }));

    expect(mediLab.sent[0].url).toBe(`${LOOKUP}PTN.2026.0042`);
    expect(router.push).toHaveBeenCalledWith({ pathname: "/samples/[id]", params: { id: "42" } });
  });

  it("says when no sample the person may see has the code", async () => {
    fakeMediLab(refusal(404, "not_found", "Không tìm thấy gì ở địa chỉ này."));
    await renderSignedIn(<ScanScreen />);

    await fireEvent.changeText(await screen.findByLabelText("Mã PTN"), "PTN.0000.0000");
    await fireEvent.press(screen.getByRole("button", { name: "Mở mẫu" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Không có mẫu nào bạn xem được có mã PTN PTN.0000.0000.");
    expect(router.push).not.toHaveBeenCalled();
  });

  it("asks for the camera and still takes a typed code without it", async () => {
    const requestPermission = jest.fn();
    jest.mocked(useCameraPermissions).mockReturnValue([
      { granted: false, canAskAgain: true, status: "undetermined", expires: "never" },
      requestPermission,
      jest.fn(),
    ] as never);
    fakeMediLab();
    await renderSignedIn(<ScanScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Cho phép dùng camera" }));

    expect(requestPermission).toHaveBeenCalled();
    expect(screen.queryByTestId("camera")).toBeNull();
    expect(screen.getByLabelText("Mã PTN")).toBeOnTheScreen();
  });
});

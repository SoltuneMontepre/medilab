import { fireEvent, screen } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";

import { result, sampleTest } from "../../testing/bench";
import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { SampleTestScreen } from "./SampleTestScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn(), replace: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const API = "https://lab.example/medilab/api/v1";

describe("SampleTestScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(router.replace).mockClear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "4" });
  });

  it("shows the test and enters its result as a number with the decimals typed and its conclusion", async () => {
    const mediLab = fakeMediLab({ status: 200, body: sampleTest() }, { status: 200, body: result() });
    await renderSignedIn(<SampleTestScreen />);

    expect(await screen.findByRole("header", { name: "PTN.2026.0042" })).toBeOnTheScreen();
    expect(screen.getByText("QCVN 6-1:2010/BYT")).toBeOnTheScreen();
    await fireEvent.changeText(screen.getByLabelText("Giá trị (mg/L)"), "0,0080");
    await fireEvent.press(screen.getByRole("button", { name: "Lưu kết quả" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Chọn đánh giá theo quy chuẩn.");
    await fireEvent.press(screen.getByRole("radio", { name: "Đạt" }));
    await fireEvent.press(screen.getByRole("button", { name: "Lưu kết quả" }));

    expect(mediLab.sent[1]).toMatchObject({
      method: "POST",
      url: `${API}/sample-tests/4/results`,
      body: { value: 0.008, decimals: 4, value_text: null, conclusion: "pass" },
    });
    expect(mediLab.sent[1].headers["Idempotency-Key"]).toBeTruthy();
    expect(router.replace).toHaveBeenCalledWith({ pathname: "/results/[id]", params: { id: "31" } });
  });

  it("enters a text result and refuses a value that is not a number", async () => {
    const mediLab = fakeMediLab(
      { status: 200, body: sampleTest({ comparison_requested: false, regulation: "" }) },
      { status: 200, body: result({ value: null, value_text: "Không phát hiện" }) },
    );
    await renderSignedIn(<SampleTestScreen />);

    await fireEvent.changeText(await screen.findByLabelText("Giá trị (mg/L)"), "0.0x");
    await fireEvent.press(screen.getByRole("button", { name: "Lưu kết quả" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nhập một số, ví dụ 0,010.");
    expect(screen.queryByRole("radio", { name: "Đạt" })).toBeNull();
    await fireEvent.press(screen.getByRole("radio", { name: "Chữ" }));
    await fireEvent.changeText(screen.getByLabelText("Kết quả dạng chữ"), " Không phát hiện ");
    await fireEvent.press(screen.getByRole("button", { name: "Lưu kết quả" }));

    expect(mediLab.sent[1].body).toEqual({ value_text: "Không phát hiện" });
  });

  it("shows MediLab's refusal and keeps the entry", async () => {
    fakeMediLab(
      { status: 200, body: sampleTest() },
      refusal(409, "action_refused", "Chỉ nhập kết quả cho mẫu đã nhận."),
    );
    await renderSignedIn(<SampleTestScreen />);

    await fireEvent.changeText(await screen.findByLabelText("Giá trị (mg/L)"), "0.008");
    await fireEvent.press(screen.getByRole("radio", { name: "Đạt" }));
    await fireEvent.press(screen.getByRole("button", { name: "Lưu kết quả" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Chỉ nhập kết quả cho mẫu đã nhận.");
    expect(screen.getByLabelText("Giá trị (mg/L)")).toHaveDisplayValue("0.008");
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("opens the reported result instead of entering another", async () => {
    fakeMediLab({ status: 200, body: sampleTest({ can_enter_result: false, result: result() }) });
    await renderSignedIn(<SampleTestScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Mở kết quả" }));

    expect(screen.queryByRole("button", { name: "Lưu kết quả" })).toBeNull();
    expect(router.push).toHaveBeenCalledWith({ pathname: "/results/[id]", params: { id: "31" } });
  });
});

import { fireEvent, screen } from "@testing-library/react-native";
import { useLocalSearchParams } from "expo-router";

import { result, sent } from "../../testing/bench";
import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { ResultScreen } from "./ResultScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn(), replace: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const API = "https://lab.example/medilab/api/v1";
const WARNING = "0,0095 mg/L nằm trong khoảng 10% của giới hạn quy chuẩn 0,010 mg/L.";
const AWAITING_HEAD = sent({ actions: { edit: false, sign: true, reject: true } });

describe("ResultScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "31" });
  });

  it("sends the result only from the confirmation step, after which it is read-only", async () => {
    const mediLab = fakeMediLab({ status: 200, body: result() }, { status: 200, body: sent() });
    await renderSignedIn(<ResultScreen />);

    expect(await screen.findByText("PTN.2026.0042 – Chì (Pb)")).toBeOnTheScreen();
    expect(screen.getByText("≤ 0,010 mg/L")).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Gửi duyệt" }));
    expect(mediLab.sent).toHaveLength(1);
    expect(screen.getByText(/Bạn ký và gửi kết quả PTN.2026.0042 – Chì \(Pb\)/)).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Ký" }));

    expect(mediLab.sent[1]).toMatchObject({ method: "POST", url: `${API}/results/31/sign`, body: { confirmed: true } });
    expect(await screen.findByText("Chờ duyệt")).toBeOnTheScreen();
    expect(
      screen.getByText("Kết quả đã được duyệt hoặc đang chờ người khác ký, nên bạn chỉ xem được."),
    ).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Gửi duyệt" })).toBeNull();
  });

  it("asks the tester to acknowledge the warnings before signing", async () => {
    const warned = result({ value_display: "0,0095 mg/L", warnings: [WARNING] });
    const mediLab = fakeMediLab({ status: 200, body: warned }, { status: 200, body: sent({ warned: true }) });
    await renderSignedIn(<ResultScreen />);

    expect(await screen.findByText(WARNING)).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Gửi duyệt" }));
    expect(screen.getByRole("button", { name: "Ký" })).toBeDisabled();
    await fireEvent.press(screen.getByRole("checkbox", { name: "Tôi đã kiểm tra các cảnh báo và vẫn gửi kết quả." }));
    await fireEvent.press(screen.getByRole("button", { name: "Ký" }));

    expect(mediLab.sent[1].body).toEqual({ confirmed: true, warnings_acknowledged: true });
  });

  it("changes a draft", async () => {
    const mediLab = fakeMediLab(
      { status: 200, body: result() },
      { status: 200, body: result({ value: 0.009, value_display: "0,009 mg/L" }) },
    );
    await renderSignedIn(<ResultScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Sửa kết quả" }));
    expect(screen.getByLabelText("Giá trị (mg/L)")).toHaveDisplayValue("0.008");
    await fireEvent.changeText(screen.getByLabelText("Giá trị (mg/L)"), "0.009");
    await fireEvent.press(screen.getByRole("button", { name: "Lưu kết quả" }));

    expect(mediLab.sent[1]).toMatchObject({
      method: "PATCH",
      url: `${API}/results/31`,
      body: { value: 0.009, decimals: 3, value_text: null, conclusion: "pass" },
    });
    expect(await screen.findByText("0,009 mg/L")).toBeOnTheScreen();
  });

  it("lets the head approve the result", async () => {
    const mediLab = fakeMediLab(
      { status: 200, body: AWAITING_HEAD },
      { status: 200, body: sent({ status: "approved", status_label: "Đã duyệt" }) },
    );
    await renderSignedIn(<ResultScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Duyệt" }));
    expect(screen.getByText("Bạn ký duyệt kết quả PTN.2026.0042 – Chì (Pb).")).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Ký" }));

    expect(mediLab.sent[1].body).toEqual({ confirmed: true });
    expect(await screen.findByText("Đã duyệt")).toBeOnTheScreen();
  });

  it("shows the refusal of a rejection without a reason, then rejects with one", async () => {
    const mediLab = fakeMediLab(
      { status: 200, body: AWAITING_HEAD },
      refusal(409, "action_refused", "Từ chối cần có lý do."),
      {
        status: 200,
        body: sent({ status: "rejected", status_label: "Bị từ chối", rejection_reason: "Hiệu chuẩn lại máy AAS." }),
      },
    );
    await renderSignedIn(<ResultScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Từ chối" }));
    await fireEvent.press(screen.getByRole("button", { name: "Từ chối kết quả" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Từ chối cần có lý do.");
    await fireEvent.changeText(screen.getByLabelText("Lý do từ chối"), "Hiệu chuẩn lại máy AAS.");
    await fireEvent.press(screen.getByRole("button", { name: "Từ chối kết quả" }));

    expect(mediLab.sent[2]).toMatchObject({
      method: "POST",
      url: `${API}/results/31/reject`,
      body: { reason: "Hiệu chuẩn lại máy AAS." },
    });
    expect(await screen.findByText("Bị từ chối")).toBeOnTheScreen();
  });

  it("says when the person can no longer see the result", async () => {
    fakeMediLab(refusal(404, "not_found", "Không tìm thấy gì ở địa chỉ này."));
    await renderSignedIn(<ResultScreen />);

    expect(await screen.findByText("Bạn không còn xem được kết quả này.")).toBeOnTheScreen();
  });
});

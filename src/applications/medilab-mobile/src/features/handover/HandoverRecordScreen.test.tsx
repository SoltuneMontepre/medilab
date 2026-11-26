import { fireEvent, screen } from "@testing-library/react-native";
import { useLocalSearchParams } from "expo-router";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { draftRecord, signedRecord } from "../../testing/handover";
import { memoryFiles } from "../../testing/memoryFiles";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { HandoverRecordScreen } from "./HandoverRecordScreen";
import { keepSignature } from "./signatureQueue";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const API = "https://lab.example/medilab/api/v1";
const UNSENT = "Chữ ký của khách hàng chưa được gửi.";

// The customer draws a stroke across the signature pad.
async function sign() {
  const pad = screen.getByLabelText("Khung chữ ký");
  await fireEvent(pad, "layout", { nativeEvent: { layout: { width: 300, height: 120 } } });
  await fireEvent(pad, "responderGrant", { nativeEvent: { locationX: 20, locationY: 60 } });
  await fireEvent(pad, "responderMove", { nativeEvent: { locationX: 280, locationY: 70 } });
}

describe("HandoverRecordScreen", () => {
  beforeEach(() => {
    kept().clear();
    memoryFiles.clear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "12" });
  });

  it("has the customer read the samples, sign by hand and confirm, after which the record is only shown", async () => {
    const mediLab = fakeMediLab({ status: 200, body: draftRecord() }, { status: 200, body: signedRecord() });
    await renderSignedIn(<HandoverRecordScreen />);

    expect(await screen.findByText("PTN.2026.0051 – Bắp cải lô A")).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Cho khách hàng ký" }));
    expect(screen.getByRole("button", { name: "Tiếp tục" })).toBeDisabled();
    await sign();
    await fireEvent.press(screen.getByRole("button", { name: "Tiếp tục" }));
    expect(screen.getByText(/Trần Văn Bình xác nhận đã giao các mẫu ghi trong biên bản BBGN.2026.0004/)).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Xác nhận và ký" }));

    expect(mediLab.sent[1]).toMatchObject({ method: "POST", url: `${API}/handover-records/12/sign` });
    expect(mediLab.sent[1].body).toEqual({ signature: expect.stringMatching(/^iVBORw0KGgo/), confirmed: true });
    expect(await screen.findByText("Pixel 8")).toBeOnTheScreen();
    expect(screen.getByText("Khách hàng đã ký biên bản này, nên bạn chỉ xem được.")).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Cho khách hàng ký" })).toBeNull();
    expect(memoryFiles.size).toBe(0);
  });

  it("shows the signature box and its buttons in place of the record, however long, while the customer signs", async () => {
    fakeMediLab({ status: 200, body: draftRecord() });
    await renderSignedIn(<HandoverRecordScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Cho khách hàng ký" }));

    expect(screen.queryByText("PTN.2026.0051 – Bắp cải lô A")).toBeNull();
    expect(screen.getByLabelText("Khung chữ ký")).toBeOnTheScreen();
    expect(screen.getByRole("button", { name: "Ký lại" })).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Huỷ" }));
    expect(screen.getByText("PTN.2026.0051 – Bắp cải lô A")).toBeOnTheScreen();
  });

  it("keeps a signature MediLab did not get on the phone and sends it again", async () => {
    const mediLab = fakeMediLab({ status: 200, body: draftRecord() }, "unreachable");
    await renderSignedIn(<HandoverRecordScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Cho khách hàng ký" }));
    await sign();
    await fireEvent.press(screen.getByRole("button", { name: "Tiếp tục" }));
    await fireEvent.press(screen.getByRole("button", { name: "Xác nhận và ký" }));

    expect(await screen.findByText(UNSENT)).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Cho khách hàng ký" })).toBeNull();
    const signature = mediLab.sent[1].body;
    mediLab.plan({ status: 200, body: signedRecord() });
    await fireEvent.press(screen.getByRole("button", { name: "Gửi chữ ký" }));

    expect(mediLab.sent[2].body).toEqual(signature);
    expect(await screen.findByText("Pixel 8")).toBeOnTheScreen();
    expect(screen.queryByText(UNSENT)).toBeNull();
  });

  it("discards a signature kept on the phone", async () => {
    await keepSignature(12, "iVBORw0KGgo=");
    fakeMediLab({ status: 200, body: draftRecord() });
    await renderSignedIn(<HandoverRecordScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Bỏ chữ ký" }));

    expect(screen.queryByText(UNSENT)).toBeNull();
    expect(screen.getByRole("button", { name: "Cho khách hàng ký" })).toBeOnTheScreen();
    expect(memoryFiles.size).toBe(0);
  });

  it("shows MediLab's refusal and keeps the signature", async () => {
    fakeMediLab(
      { status: 200, body: draftRecord() },
      refusal(409, "action_refused", "Biên bản giao nhận mẫu BBGN.2026.0004 đã được ký."),
    );
    await renderSignedIn(<HandoverRecordScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Cho khách hàng ký" }));
    await sign();
    await fireEvent.press(screen.getByRole("button", { name: "Tiếp tục" }));
    await fireEvent.press(screen.getByRole("button", { name: "Xác nhận và ký" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Biên bản giao nhận mẫu BBGN.2026.0004 đã được ký.");
    expect(screen.getByText(UNSENT)).toBeOnTheScreen();
  });

  it("only shows a record the person may not have signed", async () => {
    fakeMediLab({ status: 200, body: draftRecord({ can_sign: false }) });
    await renderSignedIn(<HandoverRecordScreen />);

    expect(await screen.findByRole("header", { name: "BBGN.2026.0004" })).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Cho khách hàng ký" })).toBeNull();
  });

  it("drops a kept signature once the record is signed", async () => {
    await keepSignature(12, "iVBORw0KGgo=");
    fakeMediLab({ status: 200, body: signedRecord() });
    await renderSignedIn(<HandoverRecordScreen />);

    expect(await screen.findByText("Pixel 8")).toBeOnTheScreen();
    expect(screen.queryByText(UNSENT)).toBeNull();
    expect(memoryFiles.size).toBe(0);
  });
});

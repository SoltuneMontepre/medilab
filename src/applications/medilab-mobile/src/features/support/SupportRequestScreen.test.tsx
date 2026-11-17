import { fireEvent, screen } from "@testing-library/react-native";
import { useLocalSearchParams } from "expo-router";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { QUESTION, supportDetail } from "../../testing/support";
import { SupportRequestScreen } from "./SupportRequestScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const API = "https://lab.example/medilab/api/v1/support-requests/5";
const ANSWER = "Kết quả có vào thứ Sáu.";
const ANSWERED = supportDetail({
  status: "answered",
  handled_by: "Nguyễn Thị Thu",
  messages: [
    ...supportDetail().messages,
    { id: 32, author: "Nguyễn Thị Thu", body: ANSWER, date: "2026-11-12T03:00:00+00:00", from_customer: false },
  ],
  actions: { take: false, answer: true },
});

describe("SupportRequestScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "5" });
  });

  it("shows the customer's question and takes the request", async () => {
    const taken = supportDetail({ handled_by: "Nguyễn Thị Thu", actions: { take: false, answer: true } });
    const mediLab = fakeMediLab({ status: 200, body: supportDetail() }, { status: 200, body: taken });
    await renderSignedIn(<SupportRequestScreen />);

    expect(await screen.findByText(QUESTION)).toBeOnTheScreen();
    expect(screen.getByText("Công ty Nước Sạch")).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Nhận xử lý" }));

    expect(await screen.findByText("Nguyễn Thị Thu")).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Nhận xử lý" })).toBeNull();
    expect(mediLab.sent[1]).toMatchObject({ method: "POST", url: `${API}/take` });
  });

  it("answers the customer once, with the same key when it is sent again after a lost answer", async () => {
    const mediLab = fakeMediLab({ status: 200, body: supportDetail() }, "unreachable", { status: 200, body: ANSWERED });
    await renderSignedIn(<SupportRequestScreen />);

    await fireEvent.changeText(await screen.findByLabelText("Câu trả lời"), ` ${ANSWER} `);
    await fireEvent.press(screen.getByRole("button", { name: "Gửi câu trả lời" }));
    await fireEvent.press(await screen.findByRole("button", { name: "Thử lại" }));

    expect(await screen.findByText(ANSWER)).toBeOnTheScreen();
    expect(screen.getByText("Đã trả lời")).toBeOnTheScreen();
    expect(screen.getByLabelText("Câu trả lời")).toHaveDisplayValue("");
    const [lost, sent] = mediLab.sent.slice(1);
    expect(sent).toMatchObject({ method: "POST", url: `${API}/answer`, body: { body: ANSWER } });
    expect(sent.headers["Idempotency-Key"]).toBe(lost.headers["Idempotency-Key"]);
  });

  it("says when someone else took the request first", async () => {
    fakeMediLab(
      { status: 200, body: supportDetail() },
      refusal(409, "already_taken", "HT.0005 Khi nào có kết quả mẫu nước đóng chai? đã có người nhận xử lý."),
    );
    await renderSignedIn(<SupportRequestScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Nhận xử lý" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/đã có người nhận xử lý/);
  });

  it("offers neither taking nor answering a closed request", async () => {
    fakeMediLab({ status: 200, body: supportDetail({ status: "closed", actions: { take: false, answer: false } }) });
    await renderSignedIn(<SupportRequestScreen />);

    expect(await screen.findByText("Đã đóng")).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Nhận xử lý" })).toBeNull();
    expect(screen.queryByLabelText("Câu trả lời")).toBeNull();
  });
});

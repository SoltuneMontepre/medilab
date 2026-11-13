import { fireEvent, screen } from "@testing-library/react-native";
import { useLocalSearchParams } from "expo-router";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { task } from "../../testing/home";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { LEAD, sample } from "../../testing/sample";
import { SampleScreen } from "./SampleScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const API = "https://lab.example/medilab/api/v1";
const ZINC = task({ id: 22, name: "PTN.2026.0042: Zinc (Zn)", status: "open", assignee: "", action: "test" });

describe("SampleScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "42" });
  });

  it("shows a tester the sample without its customer and records its receipt by their department", async () => {
    const received = sample({
      handover: { department: "Hoá", received_at: "2026-11-13T03:00:00+00:00", received_by: "Nguyễn Văn An", can_receive: false },
    });
    const mediLab = fakeMediLab({ status: 200, body: sample() }, { status: 200, body: received });
    await renderSignedIn(<SampleScreen />);

    expect(await screen.findByText("PTN.2026.0042")).toBeOnTheScreen();
    expect(screen.getByText("Chai PET 500 mL")).toBeOnTheScreen();
    expect(screen.queryByText("Khách hàng")).toBeNull();
    expect(screen.getByText("Hoá chưa nhận mẫu.")).toBeOnTheScreen();

    await fireEvent.press(screen.getByRole("button", { name: "Ghi nhận đã nhận mẫu" }));

    expect(mediLab.sent[1]).toMatchObject({
      method: "POST",
      url: `${API}/samples/receive`,
      body: { code: "PTN.2026.0042" },
    });
    expect(await screen.findByText(/^Hoá đã nhận lúc .*, bởi Nguyễn Văn An\.$/)).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Ghi nhận đã nhận mẫu" })).toBeNull();
  });

  it("says why a sample not handed over to the person's department has no receipt for them", async () => {
    fakeMediLab({
      status: 200,
      body: sample({ handover: null, tasks: [], customer: "Công ty An Phú", customer_sample_name: "Nước khoáng" }),
    });
    await renderSignedIn(<SampleScreen />);

    expect(
      await screen.findByText(
        "Mẫu này không được bàn giao cho phòng ban của bạn, nên bạn không ghi nhận đã nhận mẫu.",
      ),
    ).toBeOnTheScreen();
    expect(screen.getByText("Công ty An Phú")).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Ghi nhận đã nhận mẫu" })).toBeNull();
    expect(
      screen.getByText("Phòng ban của bạn không còn nhiệm vụ kiểm nghiệm nào chờ nhận trên mẫu này."),
    ).toBeOnTheScreen();
  });

  it("claims the chosen testing tasks of the person's department", async () => {
    const mediLab = fakeMediLab(
      { status: 200, body: sample({ tasks: [LEAD, ZINC] }) },
      { status: 200, body: sample({ tasks: [ZINC] }) },
    );
    await renderSignedIn(<SampleScreen />);

    const claim = await screen.findByRole("button", { name: "Nhận các nhiệm vụ đã chọn (0)" });
    expect(claim).toBeDisabled();
    await fireEvent.press(screen.getByRole("checkbox", { name: /Lead \(Pb\)/ }));
    await fireEvent.press(screen.getByRole("button", { name: "Nhận các nhiệm vụ đã chọn (1)" }));

    expect(mediLab.sent[1]).toMatchObject({ method: "POST", url: `${API}/samples/42/claim`, body: { task_ids: [21] } });
    expect(await screen.findByText("Đã nhận 1 nhiệm vụ.")).toBeOnTheScreen();
    expect(screen.queryByRole("checkbox", { name: /Lead \(Pb\)/ })).toBeNull();
    expect(screen.getByRole("checkbox", { name: /Zinc \(Zn\)/ })).toBeOnTheScreen();
  });

  it("tells the person when someone else claimed a task first", async () => {
    fakeMediLab(
      { status: 200, body: sample() },
      refusal(409, "already_claimed", "PTN.2026.0042: Lead (Pb) đã có người nhận."),
    );
    await renderSignedIn(<SampleScreen />);

    await fireEvent.press(await screen.findByRole("checkbox", { name: /Lead \(Pb\)/ }));
    await fireEvent.press(screen.getByRole("button", { name: "Nhận các nhiệm vụ đã chọn (1)" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("PTN.2026.0042: Lead (Pb) đã có người nhận.");
  });

  it("says when the person can no longer see the sample", async () => {
    fakeMediLab(refusal(404, "not_found", "Không tìm thấy gì ở địa chỉ này."));
    await renderSignedIn(<SampleScreen />);

    expect(await screen.findByText("Bạn không còn xem được mẫu này.")).toBeOnTheScreen();
  });
});

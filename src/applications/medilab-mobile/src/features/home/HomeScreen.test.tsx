import { fireEvent, screen } from "@testing-library/react-native";
import { router } from "expo-router";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { GREETING, day, home, me, modules, task } from "../../testing/home";
import { renderApp } from "../../testing/renderApp";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ router: { push: jest.fn() }, useFocusEffect: jest.fn() }));

const OVERDUE = task({ id: 9, name: "Update the chemical waste log", status: "in_progress" });
const PLANNED = task({ id: 10, name: "Internal audit briefing", planned_start: "2026-11-10T03:00:00+00:00" });
const SALES = { create_tasks: false, assign_tasks: false, take_support_requests: true };
const QUEUED = task({
  id: 11,
  name: "Lead (Pb)",
  status: "open",
  assignee: "",
  document: { model: "medilab.sample.test", id: 4, code: "MS-2026-0042", screen: "sample_test" },
});

describe("HomeScreen", () => {
  beforeEach(() => {
    kept().clear();
    kept().set("medilab.device_key", "device-key");
    jest.mocked(router.push).mockClear();
  });

  it("opens on the person's day: today's plan, the next tasks and the tasks waiting in their queues", async () => {
    const mediLab = fakeMediLab(
      me(),
      day({
        open_count: 2,
        overdue_count: 1,
        due_today_count: 1,
        claimable_count: 4,
        next_up: [OVERDUE],
        planned_today: [PLANNED],
        claimable: [QUEUED],
      }),
      modules(),
    );
    await renderApp();

    expect(await screen.findByText(GREETING)).toBeOnTheScreen();
    expect(screen.getByText("2 việc đang mở, 1 việc quá hạn, 1 việc đến hạn hôm nay")).toBeOnTheScreen();
    expect(screen.getByRole("header", { name: "Kế hoạch hôm nay" })).toBeOnTheScreen();
    expect(screen.getByRole("header", { name: "Đang chờ trong hàng đợi (4)" })).toBeOnTheScreen();
    expect(screen.getByRole("button", { name: /^Lead \(Pb\), MS-2026-0042, Chờ nhận/ })).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Tạo nhiệm vụ" })).toBeNull();
    expect(mediLab.sent.map((sent) => sent.headers.Authorization)).toEqual(Array(3).fill("Bearer device-key"));

    await fireEvent.press(screen.getByRole("button", { name: /^Update the chemical waste log/ }));
    expect(router.push).toHaveBeenCalledWith({ pathname: "/tasks/[id]", params: { id: "9" } });
    await fireEvent.press(screen.getByRole("button", { name: "Xem hàng đợi" }));
    expect(router.push).toHaveBeenLastCalledWith({ pathname: "/tasks", params: { list: "queue" } });
  });

  it("says when the person has nothing to do", async () => {
    fakeMediLab(...home());
    await renderApp();

    expect(await screen.findByText("Bạn không có việc nào đang mở.")).toBeOnTheScreen();
    expect(screen.queryByRole("header", { name: "Kế hoạch hôm nay" })).toBeNull();
  });

  it("opens the scanner of sample labels to those who receive or hand samples over", async () => {
    fakeMediLab(...home({ scan_samples: true }));
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Quét tem mẫu" }));
    expect(router.push).toHaveBeenCalledWith("/scan");
  });

  it("opens the results to sign to those whose signature results wait for", async () => {
    fakeMediLab(...home({ sign_results: true }));
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Kết quả chờ ký" }));
    expect(router.push).toHaveBeenCalledWith("/results");
  });

  it("hides the scanner and the results to sign from those who may not use them, such as sales", async () => {
    fakeMediLab(...home(SALES));
    await renderApp();

    expect(await screen.findByText(GREETING)).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Quét tem mẫu" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Kết quả chờ ký" })).toBeNull();
  });

  it("opens the person's conversations", async () => {
    fakeMediLab(...home());
    await renderApp();

    await fireEvent.press(await screen.findByTestId("home-conversations"));
    expect(router.push).toHaveBeenCalledWith("/conversations");
  });

  it("offers to create a task only with the permission", async () => {
    fakeMediLab(...home({ create_tasks: true, assign_tasks: true }));
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Tạo nhiệm vụ" }));
    expect(router.push).toHaveBeenCalledWith("/tasks/new");
  });

  it("offers the handover records only to those who read them", async () => {
    fakeMediLab(...home({ read_handover_records: true }));
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Biên bản giao nhận mẫu" }));
    expect(router.push).toHaveBeenCalledWith("/handover-records");
  });

  it("hides the handover records from those who do not read them", async () => {
    fakeMediLab(...home());
    await renderApp();

    expect(await screen.findByText(GREETING)).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Biên bản giao nhận mẫu" })).toBeNull();
  });

  it("offers the support requests to those who handle them with E-commerce installed", async () => {
    fakeMediLab(...home(SALES, modules("sol_commerce")));
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Yêu cầu hỗ trợ" }));
    expect(router.push).toHaveBeenCalledWith("/support");
  });

  it("hides the support requests without E-commerce", async () => {
    fakeMediLab(...home(SALES));
    await renderApp();

    expect(await screen.findByText(GREETING)).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Yêu cầu hỗ trợ" })).toBeNull();
  });

  it("returns to sign-in and removes the key MediLab refuses, such as a revoked phone's", async () => {
    const revoked = refusal(401, "invalid_key", "Thiết bị này chưa đăng nhập.");
    fakeMediLab(revoked, revoked, revoked);
    await renderApp();

    expect(await screen.findByRole("button", { name: "Đăng nhập" })).toBeOnTheScreen();
    expect(kept().has("medilab.device_key")).toBe(false);
  });

  it("signs out on MediLab and removes the key", async () => {
    const mediLab = fakeMediLab(...home(), { status: 204 });
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Đăng xuất" }));

    expect(await screen.findByRole("button", { name: "Đăng nhập" })).toBeOnTheScreen();
    expect(mediLab.sent[3]).toMatchObject({ method: "POST", url: "https://lab.example/medilab/api/v1/sign-out" });
    expect(kept().has("medilab.device_key")).toBe(false);
  });

  it("refuses to sign out without a connection and keeps the key", async () => {
    fakeMediLab(...home(), "unreachable");
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Đăng xuất" }));

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    expect(screen.getByText(GREETING)).toBeOnTheScreen();
    expect(kept().get("medilab.device_key")).toBe("device-key");
  });

  it("offers to retry when MediLab cannot be reached", async () => {
    const mediLab = fakeMediLab("unreachable", "unreachable", "unreachable");
    await renderApp();

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    mediLab.plan(...home());
    await fireEvent.press(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByText(GREETING)).toBeOnTheScreen();
  });
});

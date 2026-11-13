import { fireEvent, screen } from "@testing-library/react-native";
import { router } from "expo-router";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { GREETING, day, home, me, task } from "../../testing/home";
import { renderApp } from "../../testing/renderApp";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ router: { push: jest.fn() }, useFocusEffect: jest.fn() }));

const OVERDUE = task({ id: 9, name: "Update the chemical waste log", status: "in_progress" });
const PLANNED = task({ id: 10, name: "Internal audit briefing", planned_start: "2026-11-10T03:00:00+00:00" });
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
    );
    await renderApp();

    expect(await screen.findByText(GREETING)).toBeOnTheScreen();
    expect(screen.getByText("2 việc đang mở, 1 việc quá hạn, 1 việc đến hạn hôm nay")).toBeOnTheScreen();
    expect(screen.getByRole("header", { name: "Kế hoạch hôm nay" })).toBeOnTheScreen();
    expect(screen.getByRole("header", { name: "Đang chờ trong hàng đợi (4)" })).toBeOnTheScreen();
    expect(screen.getByRole("button", { name: /^Lead \(Pb\), MS-2026-0042, Chờ nhận/ })).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Tạo nhiệm vụ" })).toBeNull();
    expect(mediLab.sent.map((sent) => sent.headers.Authorization)).toEqual(["Bearer device-key", "Bearer device-key"]);

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

  it("opens the scanner of sample labels", async () => {
    fakeMediLab(...home());
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Quét tem mẫu" }));
    expect(router.push).toHaveBeenCalledWith("/scan");
  });

  it("offers to create a task only with the permission", async () => {
    fakeMediLab(...home({ create_tasks: true, assign_tasks: true }));
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Tạo nhiệm vụ" }));
    expect(router.push).toHaveBeenCalledWith("/tasks/new");
  });

  it("returns to sign-in and removes the key MediLab refuses, such as a revoked phone's", async () => {
    const revoked = refusal(401, "invalid_key", "Thiết bị này chưa đăng nhập.");
    fakeMediLab(revoked, revoked);
    await renderApp();

    expect(await screen.findByRole("button", { name: "Đăng nhập" })).toBeOnTheScreen();
    expect(kept().has("medilab.device_key")).toBe(false);
  });

  it("signs out on MediLab and removes the key", async () => {
    const mediLab = fakeMediLab(...home(), { status: 204 });
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Đăng xuất" }));

    expect(await screen.findByRole("button", { name: "Đăng nhập" })).toBeOnTheScreen();
    expect(mediLab.sent[2]).toMatchObject({ method: "POST", url: "https://lab.example/medilab/api/v1/sign-out" });
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
    const mediLab = fakeMediLab("unreachable", "unreachable");
    await renderApp();

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    mediLab.plan(...home());
    await fireEvent.press(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByText(GREETING)).toBeOnTheScreen();
  });
});

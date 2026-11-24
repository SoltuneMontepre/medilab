import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import { router } from "expo-router";

import { PersonProvider } from "../../person";
import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { GREETING, day, home, person, task } from "../../testing/home";
import { renderApp } from "../../testing/renderApp";
import { HomeScreen } from "./HomeScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ router: { push: jest.fn() }, useFocusEffect: jest.fn() }));

const UNDER_WAY = task({ id: 9, name: "Update the chemical waste log", status: "in_progress" });
const GIVEN = task({ id: 8, name: "Calibrate the pH meter", status: "assigned" });
const PLANNED = task({
  id: 10,
  name: "Internal audit briefing",
  planned_start: "2026-11-10T03:00:00+00:00",
  planned_end: "2026-11-10T04:00:00+00:00",
});
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

  it("opens on the person's day: today's plan, the next tasks, the queues and the finished work", async () => {
    const mediLab = fakeMediLab(
      day({
        open_count: 2,
        overdue_count: 1,
        due_today_count: 1,
        claimable_count: 4,
        finished_count: 12,
        finished_week_count: 3,
        next_up: [UNDER_WAY],
        planned_today: [PLANNED],
        claimable: [QUEUED],
      }),
    );
    await renderApp();

    expect(await screen.findByText(GREETING)).toBeOnTheScreen();
    expect(screen.getByText("2 việc đang mở, 1 việc quá hạn, 1 việc đến hạn hôm nay")).toBeOnTheScreen();
    expect(screen.getByRole("header", { name: "Kế hoạch hôm nay" })).toBeOnTheScreen();
    expect(screen.getByRole("button", { name: /^Internal audit briefing/ })).toBeOnTheScreen();
    expect(screen.getByRole("button", { name: /^Lead \(Pb\), MS-2026-0042, Chờ nhận/ })).toBeOnTheScreen();
    expect(screen.getByText("Tổng cộng 12 việc đã xong.")).toBeOnTheScreen();
    expect(mediLab.sent.map((sent) => sent.headers.Authorization)).toEqual(["Bearer device-key"]);

    await fireEvent.press(screen.getByRole("button", { name: /^Update the chemical waste log/ }));
    expect(router.push).toHaveBeenCalledWith({ pathname: "/tasks/[id]", params: { id: "9" } });
    await fireEvent.press(screen.getByTestId("home-todo"));
    expect(router.push).toHaveBeenLastCalledWith({ pathname: "/tasks", params: { list: "open" } });
    await fireEvent.press(screen.getByRole("button", { name: "Hàng đợi" }));
    expect(router.push).toHaveBeenLastCalledWith({ pathname: "/tasks", params: { list: "queue" } });
    await fireEvent.press(screen.getByRole("button", { name: "Đã xong" }));
    expect(router.push).toHaveBeenLastCalledWith({ pathname: "/tasks", params: { list: "finished" } });
  });

  it("offers on each next task the action the web's day offers", async () => {
    fakeMediLab(...home({ next_up: [GIVEN, UNDER_WAY, task({ id: 12, status: "in_progress", closed_by_system: true })] }));
    await renderApp();

    expect(await screen.findByRole("button", { name: "Bắt đầu" })).toBeOnTheScreen();
    expect(screen.getAllByRole("button", { name: "Đánh dấu xong" })).toHaveLength(1);
  });

  it("starts a task from the day and reads the day again", async () => {
    const mediLab = fakeMediLab(...home({ next_up: [GIVEN] }), { status: 200, body: {} }, ...home());
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Bắt đầu" }));

    expect(await screen.findByText("Bạn không có việc nào đang mở.")).toBeOnTheScreen();
    expect(mediLab.sent[1]).toMatchObject({ method: "POST", url: "https://lab.example/medilab/api/v1/tasks/8/start" });
    expect(mediLab.sent[2].url).toBe("https://lab.example/medilab/api/v1/tasks/today");
  });

  it("claims a task waiting in the queue, and says when someone claimed it first", async () => {
    const mediLab = fakeMediLab(
      ...home({ claimable_count: 1, claimable: [QUEUED] }),
      refusal(409, "already_claimed", "Nhiệm vụ đã được người khác nhận."),
    );
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Nhận việc" }));

    expect(await screen.findByText("Nhiệm vụ đã được người khác nhận.")).toBeOnTheScreen();
    expect(mediLab.sent[1]).toMatchObject({ method: "POST", url: "https://lab.example/medilab/api/v1/tasks/11/claim" });
  });

  it("says when the person has nothing planned and nothing to do", async () => {
    fakeMediLab(...home());
    await renderApp();

    expect(await screen.findByText("Bạn không có việc nào đang mở.")).toBeOnTheScreen();
    expect(screen.getByText("Hôm nay chưa có việc nào lên kế hoạch.")).toBeOnTheScreen();
  });

  it("returns to sign-in and removes the key MediLab refuses, such as a revoked phone's", async () => {
    fakeMediLab(refusal(401, "invalid_key", "Thiết bị này chưa đăng nhập."));
    await renderApp();

    expect(await screen.findByRole("button", { name: "Đăng nhập" })).toBeOnTheScreen();
    expect(kept().has("medilab.device_key")).toBe(false);
  });

  it("reads the person again on retry when MediLab could not be reached at start", async () => {
    const mediLab = fakeMediLab("unreachable", "unreachable", "unreachable");
    await renderApp(
      <PersonProvider>
        <HomeScreen />
      </PersonProvider>,
    );

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    mediLab.plan(...home(), ...person());
    await fireEvent.press(screen.getByRole("button", { name: "Thử lại" }));

    expect(await screen.findByText(GREETING)).toBeOnTheScreen();
    await waitFor(() => expect(mediLab.sent).toHaveLength(6));
    expect(mediLab.sent.slice(3).map((sent) => sent.url)).toEqual([
      "https://lab.example/medilab/api/v1/tasks/today",
      "https://lab.example/medilab/api/v1/me",
      "https://lab.example/medilab/api/v1/modules",
    ]);
  });

  it("offers to retry when MediLab cannot be reached", async () => {
    const mediLab = fakeMediLab("unreachable");
    await renderApp();

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    mediLab.plan(...home());
    await fireEvent.press(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByText(GREETING)).toBeOnTheScreen();
  });
});

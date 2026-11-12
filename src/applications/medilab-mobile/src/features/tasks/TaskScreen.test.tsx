import { fireEvent, screen } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";

import type { TaskDetail } from "../../api";
import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { task } from "../../testing/home";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { TaskScreen } from "./TaskScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const NO_ACTIONS = { claim: false, start: false, done: false, assign: false };

function detail(values: Partial<TaskDetail> = {}): TaskDetail {
  return {
    ...task({ id: 11, name: "Lead (Pb)", status: "open", assignee: "" }),
    note: "",
    reassign_reason: "",
    assigned_by: "",
    steps: [],
    actions: NO_ACTIONS,
    ...values,
  };
}

const QUEUED = detail({
  closed_by_system: true,
  action: "test",
  document: { model: "medilab.sample.test", id: 4, code: "MS-2026-0042", screen: "sample_test" },
  steps: [
    { minutes: 15, instruction: "Weigh the test portion.", note: "", location: "Balance room" },
    { minutes: 480, instruction: "Ash the test portion.", note: "Raise the temperature gradually.", location: "" },
  ],
  actions: { ...NO_ACTIONS, claim: true },
});

describe("TaskScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(router.push).mockClear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "11" });
  });

  it("shows a testing task with its method's steps and claims it", async () => {
    const claimed = { ...QUEUED, status: "assigned" as const, assignee: "Nguyễn Văn An", actions: NO_ACTIONS };
    const mediLab = fakeMediLab({ status: 200, body: QUEUED }, { status: 200, body: claimed });
    await renderSignedIn(<TaskScreen />);

    expect(await screen.findByText("Bước 1 · 15 phút")).toBeOnTheScreen();
    expect(screen.getByText("Ash the test portion.")).toBeOnTheScreen();
    expect(screen.getByText("Tại: Balance room")).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Đánh dấu xong" })).toBeNull();

    await fireEvent.press(screen.getByRole("button", { name: "Nhận việc" }));

    expect(mediLab.sent[1]).toMatchObject({ method: "POST", url: "https://lab.example/medilab/api/v1/tasks/11/claim" });
    expect(await screen.findByText("Nguyễn Văn An")).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Nhận việc" })).toBeNull();
  });

  it("tells the second person to claim a task that it is already claimed", async () => {
    fakeMediLab(
      { status: 200, body: QUEUED },
      refusal(409, "already_claimed", "Lead (Pb) đã có người nhận."),
    );
    await renderSignedIn(<TaskScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Nhận việc" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Lead (Pb) đã có người nhận.");
  });

  it("starts a task created by hand and marks it done", async () => {
    const mine = detail({ status: "assigned", actions: { ...NO_ACTIONS, start: true, done: true } });
    const started = { ...mine, status: "in_progress" as const, actions: { ...NO_ACTIONS, done: true } };
    const done = { ...mine, status: "done" as const, actions: NO_ACTIONS };
    const mediLab = fakeMediLab(
      { status: 200, body: mine },
      { status: 200, body: started },
      { status: 200, body: done },
    );
    await renderSignedIn(<TaskScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Bắt đầu" }));
    expect(await screen.findByText("Đang làm")).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Đánh dấu xong" }));

    expect(await screen.findByText("Đã xong")).toBeOnTheScreen();
    expect(mediLab.sent.map((sent) => sent.url.split("/").pop())).toEqual(["11", "start", "done"]);
  });

  it("opens the task's document at its action, and assigns it with the permission", async () => {
    fakeMediLab({ status: 200, body: { ...QUEUED, actions: { ...NO_ACTIONS, assign: true } } });
    await renderSignedIn(<TaskScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Mở MS-2026-0042" }));
    expect(router.push).toHaveBeenCalledWith({
      pathname: "/documents/[model]/[id]",
      params: { model: "medilab.sample.test", id: "4" },
    });
    await fireEvent.press(screen.getByRole("button", { name: "Giao việc" }));
    expect(router.push).toHaveBeenLastCalledWith({ pathname: "/tasks/[id]/assign", params: { id: "11" } });
  });

  it("says when the person can no longer see the task", async () => {
    fakeMediLab(refusal(404, "not_found", "Không tìm thấy gì ở địa chỉ này."));
    await renderSignedIn(<TaskScreen />);

    expect(await screen.findByText("Bạn không còn xem được nhiệm vụ này, hoặc nhiệm vụ đã bị xoá.")).toBeOnTheScreen();
  });

  it("keeps the task as it was when an action cannot reach MediLab", async () => {
    const mediLab = fakeMediLab({ status: 200, body: QUEUED }, "unreachable");
    await renderSignedIn(<TaskScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Nhận việc" }));

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    mediLab.plan({ status: 200, body: { ...QUEUED, actions: NO_ACTIONS } });
    await fireEvent.press(screen.getByRole("button", { name: "Thử lại" }));
    expect(mediLab.sent[2].url).toBe("https://lab.example/medilab/api/v1/tasks/11/claim");
  });
});

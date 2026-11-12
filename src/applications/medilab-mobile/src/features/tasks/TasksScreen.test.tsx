import { fireEvent, screen } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";

import { fakeMediLab, kept } from "../../testing/fakeMediLab";
import { task } from "../../testing/home";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { TasksScreen } from "./TasksScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const OVERDUE = task({ id: 1, name: "Update the chemical waste log", deadline: "2026-11-09T09:00:00+00:00" });
const LATER = task({ id: 2, name: "Review the method sheet", deadline: "2026-11-14T09:00:00+00:00" });
const DONE = task({ id: 3, name: "Clean fume hood 1", status: "done", done_at: "2026-11-07T09:00:00+00:00" });
const API = "https://lab.example/medilab/api/v1";

function names() {
  return screen.getAllByRole("button", { name: /Hạn|Xong lúc/ }).map((row) => row.props.accessibilityLabel.split(",")[0]);
}

describe("TasksScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(router.push).mockClear();
    jest.mocked(useLocalSearchParams).mockReturnValue({});
  });

  it("lists the open tasks in MediLab's order, soonest deadline first, and opens one", async () => {
    const mediLab = fakeMediLab({ status: 200, body: { tasks: [OVERDUE, LATER], next_after: null } });
    await renderSignedIn(<TasksScreen />);

    expect(await screen.findByText("Update the chemical waste log")).toBeOnTheScreen();
    expect(names()).toEqual(["Update the chemical waste log", "Review the method sheet"]);
    expect(mediLab.sent[0].url).toBe(`${API}/tasks?list=open`);
    expect(screen.getByRole("tab", { name: "Đang mở" }).props.accessibilityState).toEqual({ selected: true });

    await fireEvent.press(screen.getByRole("button", { name: /^Review the method sheet/ }));
    expect(router.push).toHaveBeenCalledWith({ pathname: "/tasks/[id]", params: { id: "2" } });
  });

  it("switches to the finished tasks and to the queue", async () => {
    const mediLab = fakeMediLab(
      { status: 200, body: { tasks: [OVERDUE], next_after: null } },
      { status: 200, body: { tasks: [DONE], next_after: null } },
      { status: 200, body: { tasks: [], next_after: null } },
    );
    await renderSignedIn(<TasksScreen />);
    await screen.findByText("Update the chemical waste log");

    await fireEvent.press(screen.getByRole("tab", { name: "Đã xong" }));
    expect(await screen.findByRole("button", { name: /^Clean fume hood 1, Đã xong, Xong lúc/ })).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("tab", { name: "Hàng đợi" }));
    expect(await screen.findByText("Không có việc nào đang chờ nhận.")).toBeOnTheScreen();
    expect(mediLab.sent.map((sent) => sent.url)).toEqual([
      `${API}/tasks?list=open`,
      `${API}/tasks?list=finished`,
      `${API}/tasks?list=queue`,
    ]);
  });

  it("opens on the list it is given and shows the next page", async () => {
    jest.mocked(useLocalSearchParams).mockReturnValue({ list: "queue" });
    const mediLab = fakeMediLab(
      { status: 200, body: { tasks: [OVERDUE], next_after: 1 } },
      { status: 200, body: { tasks: [LATER], next_after: null } },
    );
    await renderSignedIn(<TasksScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Xem thêm" }));

    expect(await screen.findByText("Review the method sheet")).toBeOnTheScreen();
    expect(mediLab.sent[1].url).toBe(`${API}/tasks?list=queue&after=1`);
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
  });

  it("offers to retry when MediLab cannot be reached", async () => {
    const mediLab = fakeMediLab("unreachable");
    await renderSignedIn(<TasksScreen />);

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    mediLab.plan({ status: 200, body: { tasks: [LATER], next_after: null } });
    await fireEvent.press(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByText("Review the method sheet")).toBeOnTheScreen();
  });
});

import { fireEvent, screen } from "@testing-library/react-native";
import { router } from "expo-router";

import { fakeMediLab, kept } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { NotificationsScreen } from "./NotificationsScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ router: { push: jest.fn() } }));

const UNREAD = {
  id: 31,
  event: "task.reminder",
  title: "Nhắc việc",
  date: "2026-11-10T08:00:00+00:00",
  read: false,
  document: { model: "medilab.task", id: 4, code: "MT-2026-0012" },
};
const READ = { ...UNREAD, id: 30, read: true, document: { model: "medilab.task", id: 5, code: "MT-2026-0010" } };

describe("NotificationsScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(router.push).mockClear();
  });

  it("lists the notifications unread first, as MediLab gives them", async () => {
    fakeMediLab({ status: 200, body: { notifications: [UNREAD, READ], next_after: null } });
    await renderSignedIn(<NotificationsScreen />);

    expect(await screen.findByRole("button", { name: "Nhắc việc, MT-2026-0012, Chưa đọc" })).toBeOnTheScreen();
    expect(screen.getByRole("button", { name: "Nhắc việc, MT-2026-0010" })).toBeOnTheScreen();
    expect(screen.getAllByRole("button").map((item) => item.props.accessibilityLabel)).toEqual([
      "Nhắc việc, MT-2026-0012, Chưa đọc",
      "Nhắc việc, MT-2026-0010",
    ]);
  });

  it("marks a notification read and opens its document", async () => {
    const mediLab = fakeMediLab({ status: 200, body: { notifications: [UNREAD], next_after: null } }, { status: 204 });
    await renderSignedIn(<NotificationsScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Nhắc việc, MT-2026-0012, Chưa đọc" }));

    expect(mediLab.sent[1]).toMatchObject({
      method: "POST",
      url: "https://lab.example/medilab/api/v1/notifications/31/read",
    });
    expect(router.push).toHaveBeenCalledWith({ pathname: "/tasks/[id]", params: { id: "4" } });
    expect(await screen.findByRole("button", { name: "Nhắc việc, MT-2026-0012" })).toBeOnTheScreen();
  });

  it("opens a notification already read without marking it again", async () => {
    const mediLab = fakeMediLab({ status: 200, body: { notifications: [READ], next_after: null } });
    await renderSignedIn(<NotificationsScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Nhắc việc, MT-2026-0010" }));

    expect(mediLab.sent).toHaveLength(1);
    expect(router.push).toHaveBeenCalledTimes(1);
  });

  it("shows the next page after the last one it has", async () => {
    const mediLab = fakeMediLab(
      { status: 200, body: { notifications: [UNREAD], next_after: 77 } },
      { status: 200, body: { notifications: [READ], next_after: null } },
    );
    await renderSignedIn(<NotificationsScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Xem thêm" }));

    expect(await screen.findByRole("button", { name: "Nhắc việc, MT-2026-0010" })).toBeOnTheScreen();
    expect(mediLab.sent[1].url).toBe("https://lab.example/medilab/api/v1/notifications?after=77");
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
  });

  it("says when there are none", async () => {
    fakeMediLab({ status: 200, body: { notifications: [], next_after: null } });
    await renderSignedIn(<NotificationsScreen />);

    expect(await screen.findByText("Chưa có thông báo nào.")).toBeOnTheScreen();
  });

  it("offers to retry when MediLab cannot be reached", async () => {
    const mediLab = fakeMediLab("unreachable");
    await renderSignedIn(<NotificationsScreen />);

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    mediLab.plan({ status: 200, body: { notifications: [READ], next_after: null } });
    await fireEvent.press(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByRole("button", { name: "Nhắc việc, MT-2026-0010" })).toBeOnTheScreen();
  });
});

import { fireEvent, screen } from "@testing-library/react-native";
import { router } from "expo-router";

import { fakeMediLab, kept } from "../../testing/fakeMediLab";
import { task } from "../../testing/home";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { NewTaskScreen } from "./NewTaskScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ router: { replace: jest.fn() } }));

const FOUND = { status: 200, body: { people: [{ id: 21, name: "Phạm Thị Dung", department: "Hoá" }], departments: [] } };
const CREATED = { status: 200, body: { ...task({ id: 40, name: "Calibrate the pH meter" }) } };

async function fill() {
  await fireEvent.changeText(await screen.findByLabelText("Tên nhiệm vụ"), "Calibrate the pH meter");
  await fireEvent.changeText(screen.getByLabelText("Hạn chót"), "2026-12-01 09:00");
  await fireEvent.changeText(screen.getByLabelText("Tìm theo tên"), "Dung");
  await fireEvent.press(screen.getByRole("button", { name: "Tìm" }));
  await fireEvent.press(await screen.findByRole("radio", { name: "Phạm Thị Dung (Hoá)" }));
}

describe("NewTaskScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(router.replace).mockClear();
  });

  it("creates a task for a person with a deadline and opens it", async () => {
    const mediLab = fakeMediLab(FOUND, CREATED);
    await renderSignedIn(<NewTaskScreen />);

    await fill();
    await fireEvent.press(screen.getByRole("button", { name: "Tạo" }));

    expect(mediLab.sent[1]).toMatchObject({
      method: "POST",
      url: "https://lab.example/medilab/api/v1/tasks",
      body: {
        name: "Calibrate the pH meter",
        assignee_id: 21,
        deadline: new Date(2026, 11, 1, 9, 0).toISOString(),
      },
    });
    expect(mediLab.sent[1].headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    expect(router.replace).toHaveBeenCalledWith({ pathname: "/tasks/[id]", params: { id: "40" } });
  });

  it("sends a task again with the same key after a lost answer", async () => {
    const mediLab = fakeMediLab(FOUND, "unreachable", CREATED);
    await renderSignedIn(<NewTaskScreen />);

    await fill();
    await fireEvent.press(screen.getByRole("button", { name: "Tạo" }));
    await fireEvent.press(await screen.findByRole("button", { name: "Thử lại" }));

    expect(router.replace).toHaveBeenCalled();
    expect(mediLab.sent[2].headers["Idempotency-Key"]).toBe(mediLab.sent[1].headers["Idempotency-Key"]);
  });

  it("asks for a name, an assignee and a real deadline before sending anything", async () => {
    const mediLab = fakeMediLab();
    await renderSignedIn(<NewTaskScreen />);

    await fireEvent.press(await screen.findByRole("button", { name: "Tạo" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Nhập tên nhiệm vụ và chọn người thực hiện.");

    mediLab.plan(FOUND);
    await fill();
    await fireEvent.changeText(screen.getByLabelText("Hạn chót"), "2026-02-30 09:00");
    await fireEvent.press(screen.getByRole("button", { name: "Tạo" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Hạn chót không phải ngày giờ hợp lệ.");
    expect(mediLab.sent).toHaveLength(1);
  });
});

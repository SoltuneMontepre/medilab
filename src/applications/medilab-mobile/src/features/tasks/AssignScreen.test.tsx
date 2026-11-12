import { fireEvent, screen } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { task } from "../../testing/home";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { AssignScreen } from "./AssignScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ router: { back: jest.fn() }, useLocalSearchParams: jest.fn() }));

const TASK = {
  status: 200,
  body: {
    ...task({ id: 5 }),
    note: "",
    reassign_reason: "",
    assigned_by: "",
    steps: [],
    actions: { claim: false, start: false, done: false, assign: true },
  },
};
const FOUND = {
  status: 200,
  body: { people: [{ id: 21, name: "Phạm Thị Dung", department: "Hoá" }], departments: [{ id: 3, name: "Vi sinh" }] },
};

async function choose(name: string) {
  await fireEvent.changeText(await screen.findByLabelText("Tìm theo tên"), "Dung");
  await fireEvent.press(screen.getByRole("button", { name: "Tìm" }));
  await fireEvent.press(await screen.findByRole("radio", { name }));
}

describe("AssignScreen", () => {
  beforeEach(() => {
    kept().clear();
    jest.mocked(router.back).mockClear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "5" });
  });

  it("refuses a reassignment without a reason with MediLab's message, then reassigns with one", async () => {
    const mediLab = fakeMediLab(
      TASK,
      FOUND,
      refusal(409, "action_refused", "Hãy nêu lý do chuyển Sort retained samples sang người hoặc phòng ban khác."),
      { status: 200, body: TASK.body },
    );
    await renderSignedIn(<AssignScreen />);

    await choose("Phạm Thị Dung (Hoá)");
    await fireEvent.press(screen.getByRole("button", { name: "Giao" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Hãy nêu lý do/);
    expect(router.back).not.toHaveBeenCalled();
    expect(mediLab.sent[1].url).toBe("https://lab.example/medilab/api/v1/tasks/assignees?q=Dung");
    expect(mediLab.sent[2].body).toEqual({ assignee_id: 21 });

    await fireEvent.changeText(screen.getByLabelText("Lý do"), "An nghỉ phép");
    await fireEvent.press(screen.getByRole("button", { name: "Giao" }));

    expect(mediLab.sent[3]).toMatchObject({
      method: "POST",
      url: "https://lab.example/medilab/api/v1/tasks/5/assign",
      body: { assignee_id: 21, reason: "An nghỉ phép" },
    });
    expect(router.back).toHaveBeenCalled();
  });

  it("moves a task to a department's queue", async () => {
    const mediLab = fakeMediLab(TASK, FOUND, { status: 204 });
    await renderSignedIn(<AssignScreen />);

    await choose("Hàng đợi Vi sinh");
    await fireEvent.changeText(screen.getByLabelText("Lý do"), "Cần kiểm tra vi sinh");
    await fireEvent.press(screen.getByRole("button", { name: "Giao" }));

    expect(mediLab.sent[2].body).toEqual({ department_id: 3, assignee_id: null, reason: "Cần kiểm tra vi sinh" });
    expect(router.back).toHaveBeenCalled();
  });
});

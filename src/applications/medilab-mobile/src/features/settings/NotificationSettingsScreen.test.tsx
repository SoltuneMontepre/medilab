import { fireEvent, screen } from "@testing-library/react-native";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { NotificationSettingsScreen } from "./NotificationSettingsScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));

const REMINDER = { event: "task.reminder", name: "Nhắc việc", mandatory: false, push: true };
const REJECTED = { event: "test_result.rejected", name: "Kết quả bị từ chối", mandatory: true, push: true };
const PREFERENCES = { status: 200, body: { preferences: [REMINDER, REJECTED] } };

describe("NotificationSettingsScreen", () => {
  beforeEach(() => kept().clear());

  it("shows each event's push, with mandatory events locked on", async () => {
    fakeMediLab(PREFERENCES);
    await renderSignedIn(<NotificationSettingsScreen />);

    const reminder = await screen.findByLabelText("Nhắc việc");
    const rejected = screen.getByLabelText("Kết quả bị từ chối");
    expect(reminder.props.value).toBe(true);
    expect(rejected.props.value).toBe(true);
    expect(rejected.props.disabled).toBe(true);
    expect(screen.getByText("Bắt buộc")).toBeOnTheScreen();
  });

  it("turns an event's push off on MediLab, which the web's preferences show", async () => {
    const mediLab = fakeMediLab(PREFERENCES, { status: 200, body: { ...REMINDER, push: false } });
    await renderSignedIn(<NotificationSettingsScreen />);

    await fireEvent(await screen.findByLabelText("Nhắc việc"), "valueChange", false);

    expect(mediLab.sent[1]).toMatchObject({
      method: "PUT",
      url: "https://lab.example/medilab/api/v1/notification-preferences/task.reminder",
      body: { push: false },
    });
    expect((await screen.findByLabelText("Nhắc việc")).props.value).toBe(false);
  });

  it("shows MediLab's refusal and keeps the push on", async () => {
    fakeMediLab(PREFERENCES, refusal(422, "mandatory_event", "Không thể tắt sự kiện bắt buộc."));
    await renderSignedIn(<NotificationSettingsScreen />);

    await fireEvent(await screen.findByLabelText("Kết quả bị từ chối"), "valueChange", false);

    expect(await screen.findByText("Không thể tắt sự kiện bắt buộc.")).toBeOnTheScreen();
    expect(screen.getByLabelText("Kết quả bị từ chối").props.value).toBe(true);
  });
});

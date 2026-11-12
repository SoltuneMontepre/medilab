import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { router } from "expo-router";

import { PushOpener } from "./features/documents/PushOpener";
import { SessionProvider } from "./session";
import { fakeMediLab, kept } from "./testing/fakeMediLab";
import { renderApp } from "./testing/renderApp";

// The test-only controls of the mocked Firebase Cloud Messaging.
const messaging = jest.requireMock("@react-native-firebase/messaging");

jest.mock("@react-native-firebase/messaging");
jest.mock("./config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ router: { push: jest.fn() } }));

const SIGNED_IN = {
  status: 200,
  body: { key: "device-key", device: { id: 7, name: "Pixel 8", platform: "android", status: "signed_in" } },
};
const MODULES = { status: 200, body: { modules: ["sol_laboratory"] } };
const SAMPLE_PUSH = { data: { event: "sample.insufficient", model: "medilab.sample", id: "12", code: "MS-2026-0042" } };
const OPENED = { pathname: "/documents/[model]/[id]", params: { model: "medilab.sample", id: "12" } };

function renderOpener() {
  return render(
    <SessionProvider>
      <PushOpener />
    </SessionProvider>,
  );
}

describe("Pushes", () => {
  beforeEach(() => {
    kept().clear();
    messaging.resetMessaging();
    jest.mocked(router.push).mockClear();
  });

  it("registers the phone's Firebase token at sign-in and again when Firebase changes it", async () => {
    messaging.givePushToken("fcm-token");
    const mediLab = fakeMediLab(SIGNED_IN, MODULES, { status: 204 });
    await renderApp();

    await fireEvent.changeText(await screen.findByLabelText("Tên đăng nhập"), "demo.tester");
    await fireEvent.changeText(screen.getByLabelText("Mật khẩu"), "typed");
    await fireEvent.press(screen.getByRole("button", { name: "Đăng nhập" }));

    await waitFor(() => expect(mediLab.sent).toHaveLength(3));
    expect(mediLab.sent[2]).toMatchObject({
      method: "PUT",
      url: "https://lab.example/medilab/api/v1/push-token",
      headers: { Authorization: "Bearer device-key" },
      body: { token: "fcm-token" },
    });

    mediLab.plan({ status: 204 });
    await act(async () => messaging.refreshPushToken("new-token"));
    await waitFor(() => expect(mediLab.sent).toHaveLength(4));
    expect(mediLab.sent[3].body).toEqual({ token: "new-token" });
  });

  it("registers nothing on a build without Firebase", async () => {
    const mediLab = fakeMediLab(MODULES);
    kept().set("medilab.device_key", "device-key");
    await renderApp();

    expect(await screen.findByText("Đã đăng nhập")).toBeOnTheScreen();
    expect(mediLab.sent.map((sent) => sent.url)).toEqual(["https://lab.example/medilab/api/v1/modules"]);
  });

  it("opens the document of a tapped push, also the one that started the app", async () => {
    kept().set("medilab.device_key", "device-key");
    messaging.startFromPush(SAMPLE_PUSH);
    await renderOpener();

    await waitFor(() => expect(router.push).toHaveBeenCalledWith(OPENED));
    await act(async () => messaging.tapPush({ data: { ...SAMPLE_PUSH.data, id: "13" } }));
    expect(router.push).toHaveBeenLastCalledWith({ ...OPENED, params: { model: "medilab.sample", id: "13" } });
    await act(async () => messaging.tapPush({ data: {} }));
    expect(router.push).toHaveBeenCalledTimes(2);
  });

  it("opens no push while the phone is signed out", async () => {
    messaging.startFromPush(SAMPLE_PUSH);
    await renderOpener();

    await act(async () => undefined);
    expect(router.push).not.toHaveBeenCalled();
  });
});

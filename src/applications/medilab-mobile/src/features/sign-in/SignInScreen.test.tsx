import { fireEvent, screen } from "@testing-library/react-native";
import { Platform } from "react-native";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { renderApp } from "../../testing/renderApp";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));

const SIGNED_IN = {
  status: 200,
  body: {
    key: "device-key",
    device: { id: 7, name: "Pixel 8", platform: "android", status: "signed_in", last_seen_at: null, revoked_at: null, current: true },
  },
};

// What the person types as their password; the test makes it up, so no secret is written here.
const TYPED = `typed-${Math.random().toString(36).slice(2)}`;

async function signIn(login = "demo.tester", password = TYPED) {
  await fireEvent.changeText(await screen.findByLabelText("Tên đăng nhập"), login);
  await fireEvent.changeText(screen.getByLabelText("Mật khẩu"), password);
  await fireEvent.press(screen.getByRole("button", { name: "Đăng nhập" }));
}

describe("SignInScreen", () => {
  beforeEach(() => kept().clear());

  it("keeps the device key in secure storage and never the password", async () => {
    const mediLab = fakeMediLab(SIGNED_IN, { status: 200, body: { modules: ["sol_laboratory"] } });
    await renderApp();

    await signIn();

    expect(await screen.findByText("Đã đăng nhập")).toBeOnTheScreen();
    expect(mediLab.sent[0].body).toMatchObject({ login: "demo.tester", name: "Pixel 8", platform: Platform.OS });
    expect(kept().get("medilab.device_key")).toBe("device-key");
    expect([...kept().values()].join(" ")).not.toContain(TYPED);
    expect(mediLab.sent[1].headers.Authorization).toBe("Bearer device-key");
  });

  it("signs in again with the same installation id", async () => {
    const mediLab = fakeMediLab(SIGNED_IN, { status: 200, body: { modules: [] } });
    kept().set("medilab.installation_id", "kept-installation");
    await renderApp();

    await signIn();

    expect(mediLab.sent[0].body).toMatchObject({ client_uid: "kept-installation" });
  });

  it("shows MediLab's refusal and keeps nothing", async () => {
    fakeMediLab(refusal(403, "permission_denied", "Chỉ nhân viên phòng thí nghiệm đăng nhập trên Medilab Mobile."));
    await renderApp();

    await signIn("customer");

    expect(await screen.findByText("Chỉ nhân viên phòng thí nghiệm đăng nhập trên Medilab Mobile.")).toBeOnTheScreen();
    expect(kept().has("medilab.device_key")).toBe(false);
    expect(screen.getByLabelText("Mật khẩu").props.value).toBe("");
  });

  it("refuses without a connection, changes nothing and signs in on retry", async () => {
    fakeMediLab("unreachable", SIGNED_IN, { status: 200, body: { modules: [] } });
    await renderApp();

    await signIn();

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    expect(kept().has("medilab.device_key")).toBe(false);
    await fireEvent.press(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByText("Đã đăng nhập")).toBeOnTheScreen();
  });

  it("keeps the language chosen for the next start", async () => {
    fakeMediLab();
    const first = await renderApp();

    await fireEvent.press(await screen.findByRole("radio", { name: "English" }));

    expect(await screen.findByRole("button", { name: "Sign in" })).toBeOnTheScreen();
    expect(kept().get("medilab.language")).toBe("en");
    await first.unmount();
    await renderApp();
    expect(await screen.findByLabelText("Password")).toBeOnTheScreen();
  });

  it("asks for an address MediLab can be reached at", async () => {
    const mediLab = fakeMediLab();
    await renderApp();

    await fireEvent.changeText(await screen.findByLabelText("Địa chỉ MediLab"), "lab.example");
    await signIn();

    expect(screen.getByText(/Địa chỉ MediLab phải bắt đầu bằng/)).toBeOnTheScreen();
    expect(mediLab.sent).toHaveLength(0);
  });

  it("keeps the edited server address", async () => {
    const mediLab = fakeMediLab(SIGNED_IN, { status: 200, body: { modules: [] } });
    await renderApp();

    await fireEvent.changeText(await screen.findByLabelText("Địa chỉ MediLab"), "https://other.example/");
    await signIn();

    expect(mediLab.sent[0].url).toBe("https://other.example/medilab/api/v1/sign-in");
    expect(kept().get("medilab.server_url")).toBe("https://other.example");
  });
});

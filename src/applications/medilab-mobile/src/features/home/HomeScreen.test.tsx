import { fireEvent, screen } from "@testing-library/react-native";

import { fakeMediLab, kept, refusal } from "../../testing/fakeMediLab";
import { renderApp } from "../../testing/renderApp";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));

const MODULES = { status: 200, body: { modules: ["sol_laboratory"] } };

describe("HomeScreen", () => {
  beforeEach(() => {
    kept().clear();
    kept().set("medilab.device_key", "device-key");
  });

  it("opens signed in with the kept key", async () => {
    const mediLab = fakeMediLab(MODULES);
    await renderApp();

    expect(await screen.findByText("Đã đăng nhập")).toBeOnTheScreen();
    expect(screen.getByText("Máy chủ: https://lab.example")).toBeOnTheScreen();
    expect(mediLab.sent[0].headers.Authorization).toBe("Bearer device-key");
  });

  it("returns to sign-in and removes the key MediLab refuses, such as a revoked phone's", async () => {
    fakeMediLab(refusal(401, "invalid_key", "Thiết bị này chưa đăng nhập."));
    await renderApp();

    expect(await screen.findByRole("button", { name: "Đăng nhập" })).toBeOnTheScreen();
    expect(kept().has("medilab.device_key")).toBe(false);
  });

  it("signs out on MediLab and removes the key", async () => {
    const mediLab = fakeMediLab(MODULES, { status: 204 });
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Đăng xuất" }));

    expect(await screen.findByRole("button", { name: "Đăng nhập" })).toBeOnTheScreen();
    expect(mediLab.sent[1]).toMatchObject({ method: "POST", url: "https://lab.example/medilab/api/v1/sign-out" });
    expect(kept().has("medilab.device_key")).toBe(false);
  });

  it("refuses to sign out without a connection and keeps the key", async () => {
    fakeMediLab(MODULES, "unreachable");
    await renderApp();

    await fireEvent.press(await screen.findByRole("button", { name: "Đăng xuất" }));

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    expect(screen.getByText("Đã đăng nhập")).toBeOnTheScreen();
    expect(kept().get("medilab.device_key")).toBe("device-key");
  });

  it("offers to retry when MediLab cannot be reached", async () => {
    const mediLab = fakeMediLab("unreachable");
    await renderApp();

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    mediLab.then(MODULES);
    await fireEvent.press(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByText("Đã đăng nhập")).toBeOnTheScreen();
  });
});

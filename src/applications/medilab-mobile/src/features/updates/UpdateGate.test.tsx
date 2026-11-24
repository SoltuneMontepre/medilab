import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { startActivityAsync } from "expo-intent-launcher";
import * as Updates from "expo-updates";
import { AppState, Platform, Text, type AppStateStatus } from "react-native";

import { SessionProvider } from "../../session";
import { fakeMediLab, refusal } from "../../testing/fakeMediLab";
import { memoryDownloads, memoryFiles } from "../../testing/memoryFiles";
import { UpdateGate } from "./UpdateGate";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-constants", () => ({ expoConfig: { version: "1.0.0" } }));

const RELEASE_URL = "https://lab.example/medilab/api/v1/mobile/release/android/runtime-1/1.0.0";
const APK_URL = "https://release.example/mobile/android/1.1.0/medilab-1.1.0.apk";
const APK = "the signed APK of MediLab 1.1.0";
// The global holding React Native's __DEV__, true in a development build.
const runtime = globalThis as unknown as { __DEV__: boolean };

async function sha256(text: string): Promise<string> {
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
  return Array.from(hash, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function openApp() {
  return render(
    <SessionProvider>
      <UpdateGate>
        <Text>The app</Text>
      </UpdateGate>
    </SessionProvider>,
  );
}

describe("updates", () => {
  let foreground: (state: AppStateStatus) => void;

  beforeEach(() => {
    jest.replaceProperty(runtime, "__DEV__", false);
    jest.replaceProperty(Platform, "OS", "android");
    jest.spyOn(AppState, "addEventListener").mockImplementation((_event, handler) => {
      foreground = handler;
      return { remove: jest.fn() } as never;
    });
    jest.mocked(Updates.fetchUpdateAsync).mockReset();
    jest.mocked(Updates.reloadAsync).mockReset();
    jest.mocked(startActivityAsync).mockClear();
    memoryFiles.clear();
    memoryDownloads.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("opens a phone that runs a version MediLab serves", async () => {
    const mediLab = fakeMediLab({ status: 204 });
    await openApp();

    expect(await screen.findByText("The app")).toBeOnTheScreen();
    expect(mediLab.sent[0]).toMatchObject({ method: "GET", url: RELEASE_URL });
  });

  it("keeps a phone with a code update shut until it restarts into the update", async () => {
    fakeMediLab({ status: 200, body: { action: "code", version: "1.1.0" } });
    jest.mocked(Updates.fetchUpdateAsync).mockResolvedValue({ isNew: true, isRollBackToEmbedded: false } as never);
    await openApp();

    expect(await screen.findByText("Đang tải phiên bản 1.1.0. Ứng dụng tự khởi động lại khi tải xong.")).toBeOnTheScreen();
    await waitFor(() => expect(Updates.reloadAsync).toHaveBeenCalled());
    expect(screen.queryByText("The app")).not.toBeOnTheScreen();
    expect(screen.queryByTestId("update-retry")).not.toBeOnTheScreen();
  });

  it("refuses an unsigned update and keeps the version the phone has, still shut", async () => {
    const mediLab = fakeMediLab({ status: 200, body: { action: "code", version: "1.1.0" } });
    jest.mocked(Updates.fetchUpdateAsync).mockRejectedValue(new Error("Manifest signature is invalid"));
    await openApp();

    expect(await screen.findByRole("alert")).toHaveTextContent(/ứng dụng giữ phiên bản hiện tại/);
    expect(Updates.reloadAsync).not.toHaveBeenCalled();
    expect(screen.queryByText("The app")).not.toBeOnTheScreen();

    mediLab.plan({ status: 200, body: { action: "code", version: "1.1.0" } });
    jest.mocked(Updates.fetchUpdateAsync).mockResolvedValue({ isNew: true, isRollBackToEmbedded: false } as never);
    await fireEvent.press(screen.getByTestId("update-retry"));
    await waitFor(() => expect(Updates.reloadAsync).toHaveBeenCalled());
  });

  it("downloads a new install, checks it and opens Android's installer", async () => {
    fakeMediLab({ status: 200, body: { action: "install", version: "1.1.0", url: APK_URL, sha256: await sha256(APK) } });
    memoryDownloads.set(APK_URL, APK);
    await openApp();

    expect(await screen.findByTestId("update-retry")).toHaveTextContent("Mở lại trình cài đặt");
    await waitFor(() =>
      expect(startActivityAsync).toHaveBeenCalledWith("android.intent.action.VIEW", {
        data: "content:///cache/medilab-1.1.0.apk",
        type: "application/vnd.android.package-archive",
        flags: 1,
      }),
    );
    expect(screen.queryByText("The app")).not.toBeOnTheScreen();
  });

  it("refuses an altered APK without opening the installer", async () => {
    fakeMediLab({ status: 200, body: { action: "install", version: "1.1.0", url: APK_URL, sha256: await sha256(APK) } });
    memoryDownloads.set(APK_URL, `${APK}, altered`);
    await openApp();

    expect(await screen.findByRole("alert")).toBeOnTheScreen();
    expect(startActivityAsync).not.toHaveBeenCalled();
    expect(memoryFiles.has("file:///cache/medilab-1.1.0.apk")).toBe(false);
  });

  it("shows only the updating screen on a version older than the oldest MediLab serves", async () => {
    fakeMediLab({ status: 200, body: { action: "unavailable" } });
    await openApp();

    expect(await screen.findByText(/MediLab không còn hỗ trợ phiên bản này/)).toBeOnTheScreen();
    expect(screen.queryByText("The app")).not.toBeOnTheScreen();
  });

  it("checks again when the person comes back to the app after a minute away", async () => {
    const now = jest.spyOn(Date, "now").mockReturnValue(1_000_000);
    const mediLab = fakeMediLab({ status: 204 });
    jest.mocked(Updates.fetchUpdateAsync).mockResolvedValue({ isNew: true, isRollBackToEmbedded: false } as never);
    await openApp();
    expect(await screen.findByText("The app")).toBeOnTheScreen();

    mediLab.plan({ status: 200, body: { action: "code", version: "1.1.0" } });
    await act(async () => foreground("background"));
    now.mockReturnValue(1_060_000);
    await act(async () => foreground("active"));

    expect(await screen.findByTestId("updating-screen")).toBeOnTheScreen();
    expect(screen.queryByText("The app")).not.toBeOnTheScreen();
    expect(mediLab.sent).toHaveLength(2);
  });

  it("keeps the screen when a permission dialog or the camera the app opened closes", async () => {
    const now = jest.spyOn(Date, "now").mockReturnValue(1_000_000);
    const mediLab = fakeMediLab({ status: 204 });
    await openApp();
    expect(await screen.findByText("The app")).toBeOnTheScreen();

    mediLab.plan({ status: 200, body: { action: "install", version: "1.1.1", url: APK_URL, sha256: "0" } });
    await act(async () => foreground("background"));
    now.mockReturnValue(1_020_000);
    await act(async () => foreground("active"));

    expect(screen.getByText("The app")).toBeOnTheScreen();
    expect(mediLab.sent).toHaveLength(1);
  });

  it("opens the app when MediLab cannot answer, as every other call is refused then too", async () => {
    fakeMediLab(refusal(503, "update_unavailable", "Updates are unavailable."), "unreachable");
    await openApp();

    expect(await screen.findByText("The app")).toBeOnTheScreen();
    await act(async () => foreground("active"));
    expect(screen.getByText("The app")).toBeOnTheScreen();
  });

  it("asks nothing in a build without the update certificate", async () => {
    jest.replaceProperty(Updates, "isEnabled", false);
    const mediLab = fakeMediLab();
    await openApp();

    expect(screen.getByText("The app")).toBeOnTheScreen();
    expect(mediLab.sent).toHaveLength(0);
  });

  it("asks nothing in a development build, whose launcher reports updates on", async () => {
    jest.replaceProperty(runtime, "__DEV__", true);
    const mediLab = fakeMediLab();
    await openApp();

    expect(screen.getByText("The app")).toBeOnTheScreen();
    expect(mediLab.sent).toHaveLength(0);
  });
});

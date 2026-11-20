import { fireEvent, screen } from "@testing-library/react-native";
import { router } from "expo-router";

import { PersonProvider } from "../../person";
import { fakeMediLab, kept } from "../../testing/fakeMediLab";
import { PERSON, modules, person } from "../../testing/home";
import { renderApp } from "../../testing/renderApp";
import { MenuScreen } from "./MenuScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({ router: { push: jest.fn() }, useFocusEffect: jest.fn() }));

const SALES = { create_tasks: false, assign_tasks: false, take_support_requests: true };

function renderMenu() {
  return renderApp(
    <PersonProvider>
      <MenuScreen />
    </PersonProvider>,
  );
}

describe("MenuScreen", () => {
  beforeEach(() => {
    kept().clear();
    kept().set("medilab.device_key", "device-key");
    jest.mocked(router.push).mockClear();
  });

  it("shows the person's account with the server", async () => {
    const mediLab = fakeMediLab(...person());
    await renderMenu();

    expect(await screen.findByText(PERSON)).toBeOnTheScreen();
    expect(screen.getByText("https://lab.example")).toBeOnTheScreen();
    expect(mediLab.sent.map((sent) => sent.url)).toEqual([
      "https://lab.example/medilab/api/v1/me",
      "https://lab.example/medilab/api/v1/modules",
    ]);
    await fireEvent.press(screen.getByRole("button", { name: "Cài đặt thông báo" }));
    expect(router.push).toHaveBeenCalledWith("/notification-settings");
  });

  it("opens the results to sign to those whose signature results wait for", async () => {
    fakeMediLab(...person({ sign_results: true }));
    await renderMenu();

    await fireEvent.press(await screen.findByRole("button", { name: "Kết quả chờ ký" }));
    expect(router.push).toHaveBeenCalledWith("/results");
  });

  it("opens the handover records to those who read them", async () => {
    fakeMediLab(...person({ read_handover_records: true }));
    await renderMenu();

    await fireEvent.press(await screen.findByRole("button", { name: "Biên bản giao nhận mẫu" }));
    expect(router.push).toHaveBeenCalledWith("/handover-records");
  });

  it("offers the support requests to those who handle them with E-commerce installed", async () => {
    fakeMediLab(...person(SALES, modules("sol_commerce")));
    await renderMenu();

    await fireEvent.press(await screen.findByRole("button", { name: "Yêu cầu hỗ trợ" }));
    expect(router.push).toHaveBeenCalledWith("/support");
  });

  it("shows no apps the person may not use, such as support requests without E-commerce", async () => {
    fakeMediLab(...person(SALES));
    await renderMenu();

    expect(await screen.findByText(PERSON)).toBeOnTheScreen();
    expect(screen.queryByText("Ứng dụng")).toBeNull();
    expect(screen.queryByRole("button", { name: "Yêu cầu hỗ trợ" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Kết quả chờ ký" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Biên bản giao nhận mẫu" })).toBeNull();
  });

  it("changes the language of the app", async () => {
    fakeMediLab(...person());
    await renderMenu();

    await fireEvent.press(await screen.findByTestId("menu-language-en"));

    expect(await screen.findByRole("button", { name: "Sign out" })).toBeOnTheScreen();
    expect(kept().get("medilab.language")).toBe("en");
  });

  it("signs out on MediLab and removes the key", async () => {
    const mediLab = fakeMediLab(...person(), { status: 204 });
    await renderMenu();

    await fireEvent.press(await screen.findByRole("button", { name: "Đăng xuất" }));

    expect(await screen.findByRole("button", { name: "Đăng nhập" })).toBeOnTheScreen();
    expect(mediLab.sent[2]).toMatchObject({ method: "POST", url: "https://lab.example/medilab/api/v1/sign-out" });
    expect(kept().has("medilab.device_key")).toBe(false);
  });

  it("refuses to sign out without a connection and keeps the key", async () => {
    fakeMediLab(...person(), "unreachable");
    await renderMenu();

    await fireEvent.press(await screen.findByRole("button", { name: "Đăng xuất" }));

    expect(await screen.findByText(/Không kết nối được MediLab/)).toBeOnTheScreen();
    expect(screen.getByText(PERSON)).toBeOnTheScreen();
    expect(kept().get("medilab.device_key")).toBe("device-key");
  });
});

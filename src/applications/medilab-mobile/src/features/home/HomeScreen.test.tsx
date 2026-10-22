import { render, screen } from "@testing-library/react-native";

import { LocaleProvider } from "../../locale";
import { HomeScreen } from "./HomeScreen";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));

describe("HomeScreen", () => {
  it("shows the server address in the locale", async () => {
    await render(
      <LocaleProvider locale="en">
        <HomeScreen />
      </LocaleProvider>,
    );
    expect(screen.getByText("Server: https://lab.example")).toBeOnTheScreen();
  });
});

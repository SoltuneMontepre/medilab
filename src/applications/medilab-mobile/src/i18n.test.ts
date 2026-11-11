import { translate } from "./i18n";

describe("translate", () => {
  it("translates into Vietnamese and English", () => {
    expect(translate("vi", "home.server", { url: "https://lab.example" })).toBe("Máy chủ: https://lab.example");
    expect(translate("en", "home.server", { url: "https://lab.example" })).toBe("Server: https://lab.example");
  });
});

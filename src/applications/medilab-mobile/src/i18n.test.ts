import { translate } from "./i18n";

describe("translate", () => {
  it("translates into Vietnamese and English", () => {
    expect(translate("vi", "signIn.serverIs", { url: "https://lab.example" })).toBe("Máy chủ: https://lab.example");
    expect(translate("en", "signIn.serverIs", { url: "https://lab.example" })).toBe("Server: https://lab.example");
  });
});

import { normalizeServerUrl, serverUrlError } from "./server";

describe("server address", () => {
  it("takes only HTTPS in a production build", () => {
    expect(serverUrlError("https://lab.example", true)).toBeNull();
    expect(serverUrlError("http://lab.example", true)).toBe("server.invalid");
    expect(serverUrlError("lab.example", true)).toBe("server.invalid");
  });

  it("takes HTTP too in a development build", () => {
    expect(serverUrlError("http://10.0.2.2:8069", false)).toBeNull();
    expect(serverUrlError("ftp://lab.example", false)).toBe("server.invalidDevelopment");
  });

  it("keeps the address without spaces or trailing slashes", () => {
    expect(normalizeServerUrl(" https://lab.example/ ")).toBe("https://lab.example");
  });
});

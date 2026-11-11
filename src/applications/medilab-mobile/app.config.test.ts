import appConfig, { DEFAULT_SERVER_URL } from "./app.config";

describe("app config", () => {
  const original = process.env.MEDILAB_URL;
  afterEach(() => {
    if (original === undefined) {
      delete process.env.MEDILAB_URL;
    } else {
      process.env.MEDILAB_URL = original;
    }
  });

  it("builds in the server address from MEDILAB_URL", () => {
    process.env.MEDILAB_URL = "https://lab.example";
    expect(appConfig({ config: {} } as never).extra?.serverUrl).toBe("https://lab.example");
  });

  it("falls back to the local app", () => {
    delete process.env.MEDILAB_URL;
    expect(appConfig({ config: {} } as never).extra?.serverUrl).toBe(DEFAULT_SERVER_URL);
  });
});

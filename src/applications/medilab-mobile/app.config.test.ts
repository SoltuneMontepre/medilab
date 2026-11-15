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

  it("lets a build made for an HTTP server reach it", () => {
    process.env.MEDILAB_URL = "http://localhost:8069";
    const config = appConfig({ config: {} } as never);
    expect(config.extra?.allowsHttp).toBe(true);
    expect(config.plugins).toContainEqual([
      "expo-build-properties",
      { ios: { useFrameworks: "dynamic" }, android: { usesCleartextTraffic: true } },
    ]);
  });

  it("keeps a build made for an HTTPS server on HTTPS", () => {
    process.env.MEDILAB_URL = "https://lab.example";
    const config = appConfig({ config: {} } as never);
    expect(config.extra?.allowsHttp).toBe(false);
    expect(config.plugins).toContainEqual(["expo-build-properties", { ios: { useFrameworks: "dynamic" }, android: {} }]);
  });
});

import appConfig, { DEFAULT_SERVER_URL, DEFAULT_VERSION, versionCode } from "./app.config";

describe("app config", () => {
  const original = { ...process.env };
  afterEach(() => {
    process.env = { ...original };
  });

  it("builds a local build with the default version and no runtime version", () => {
    delete process.env.MEDILAB_MOBILE_VERSION;
    delete process.env.MEDILAB_MOBILE_RUNTIME_VERSION;
    const config = appConfig({ config: {} } as never);
    expect(config.version).toBe(DEFAULT_VERSION);
    expect(config.runtimeVersion).toBeUndefined();
    expect(config.android?.versionCode).toBe(1_000);
  });

  it("builds a release with the pipeline's version and runtime version", () => {
    process.env.MEDILAB_MOBILE_VERSION = "1.2.3";
    process.env.MEDILAB_MOBILE_RUNTIME_VERSION = "7b04";
    const config = appConfig({ config: {} } as never);
    expect(config.version).toBe("1.2.3");
    expect(config.runtimeVersion).toBe("7b04");
    expect(config.android?.versionCode).toBe(1_002_003);
  });

  it("orders version codes as the versions", () => {
    expect(versionCode("1.10.0")).toBeGreaterThan(versionCode("1.9.999"));
    expect(versionCode("2.0.0")).toBeGreaterThan(versionCode("1.999.999"));
  });

  it("refuses a version Android cannot order", () => {
    expect(() => versionCode("1.2.3-beta.1")).toThrow("is not a version such as 1.2.3");
    expect(() => versionCode("1.1000.0")).toThrow("is not a version such as 1.2.3");
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
    expect(config.ios?.infoPlist).toEqual({ NSAppTransportSecurity: { NSAllowsArbitraryLoads: true } });
    expect(config.plugins).toContainEqual([
      "expo-build-properties",
      { ios: { useFrameworks: "dynamic" }, android: { usesCleartextTraffic: true } },
    ]);
  });

  it("keeps a build made for an HTTPS server on HTTPS", () => {
    process.env.MEDILAB_URL = "https://lab.example";
    const config = appConfig({ config: {} } as never);
    expect(config.extra?.allowsHttp).toBe(false);
    expect(config.ios?.infoPlist).toBeUndefined();
    expect(config.plugins).toContainEqual(["expo-build-properties", { ios: { useFrameworks: "dynamic" }, android: {} }]);
  });
});

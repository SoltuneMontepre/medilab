import appConfig, { DEFAULT_SERVER_URL } from "./app.config";

describe("app config", () => {
  const original = { ...process.env };
  afterEach(() => {
    process.env = { ...original };
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

  it("takes updates signed with the update key from the MediLab it was built for", () => {
    process.env.MEDILAB_URL = "https://lab.example";
    process.env.MEDILAB_MOBILE_UPDATE_CERTIFICATE = "./certs/update.pem";
    expect(appConfig({ config: {} } as never).updates).toEqual({
      enabled: true,
      url: "https://lab.example/medilab/api/v1/mobile/updates",
      checkAutomatically: "NEVER",
      codeSigningCertificate: "./certs/update.pem",
      codeSigningMetadata: { keyid: "main", alg: "rsa-v1_5-sha256" },
    });
  });

  it("takes no update in a build without the update certificate", () => {
    delete process.env.MEDILAB_MOBILE_UPDATE_CERTIFICATE;
    expect(appConfig({ config: {} } as never).updates).toEqual({ enabled: false });
  });
});

import { ApiError, callApi, UnreachableError } from "./api";
import { fakeMediLab, refusal } from "./testing/fakeMediLab";

describe("callApi", () => {
  it("sends the key and the language and answers the JSON", async () => {
    const mediLab = fakeMediLab({ status: 200, body: { modules: ["sol_laboratory"] } });

    const answer = await callApi("https://lab.example", "en", "/modules", { key: "device-key" });

    expect(answer).toEqual({ modules: ["sol_laboratory"] });
    expect(mediLab.sent[0].url).toBe("https://lab.example/medilab/api/v1/modules");
    expect(mediLab.sent[0].headers).toMatchObject({ Authorization: "Bearer device-key", "Accept-Language": "en" });
  });

  it("answers null for an answer without content", async () => {
    fakeMediLab({ status: 204 });

    expect(await callApi("https://lab.example", "vi", "/sign-out", { method: "POST" })).toBeNull();
  });

  it("raises MediLab's refusal with its code and message", async () => {
    fakeMediLab(refusal(401, "invalid_key", "Thiết bị này chưa đăng nhập."));

    const call = callApi("https://lab.example", "vi", "/modules", { key: "gone" });

    await expect(call).rejects.toEqual(new ApiError("invalid_key", "Thiết bị này chưa đăng nhập.", 401));
  });

  it("counts a failed connection or another server's answer as unreachable", async () => {
    fakeMediLab("unreachable", { status: 502 });

    await expect(callApi("https://lab.example", "vi", "/modules")).rejects.toBeInstanceOf(UnreachableError);
    await expect(callApi("https://lab.example", "vi", "/modules")).rejects.toBeInstanceOf(UnreachableError);
  });
});

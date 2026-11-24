import { expect, test } from "bun:test";
import { connectServer } from "./connectLink";

const link = (server: string) => `medilab-sync://connect?server=${encodeURIComponent(server)}`;

test("a connect link gives its MediLab address", () => {
  expect(connectServer(link("https://lims.example.com"))).toBe("https://lims.example.com");
  expect(connectServer(link("https://lims.example.com/"))).toBe("https://lims.example.com");
  expect(connectServer(link("http://localhost:8069/odoo/?x=1#y"))).toBe("http://localhost:8069/odoo");
});

test("any other link gives no address", () => {
  for (const other of [
    "",
    "medilab-sync://connect",
    "medilab-sync://open?server=https%3A%2F%2Flims.example.com",
    "other://connect?server=https%3A%2F%2Flims.example.com",
    link("javascript:alert(1)"),
    link("file:///etc/passwd"),
    link("https://user:secret@lims.example.com"),
    link("not an address"),
  ]) {
    expect(connectServer(other)).toBeNull();
  }
});

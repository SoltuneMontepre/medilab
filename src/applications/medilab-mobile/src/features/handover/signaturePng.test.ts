/// <reference types="node" />

import { inflateSync } from "node:zlib";

import { PNG_HEIGHT, PNG_WIDTH, signaturePng } from "./signaturePng";

// The PNG's bytes, its picture's rows once inflated, and whether the pixel is ink.
function decoded(base64: string) {
  const png = Buffer.from(base64, "base64");
  const width = png.readUInt32BE(16);
  const height = png.readUInt32BE(20);
  const idatLength = png.readUInt32BE(33);
  const pixels = inflateSync(png.subarray(41, 41 + idatLength));
  const rowBytes = Math.ceil(width / 8) + 1;
  const ink = (x: number, y: number) => (pixels[y * rowBytes + 1 + (x >> 3)] & (0x80 >> (x & 7))) === 0;
  return { png, width, height, ink };
}

describe("signaturePng", () => {
  it("draws the strokes as black ink on white in a valid PNG", () => {
    // A pad half the picture's size: a stroke across its middle, and a dot.
    const { png, width, height, ink } = decoded(
      signaturePng(
        [
          [
            { x: 10, y: 60 },
            { x: 290, y: 60 },
          ],
          [{ x: 150, y: 100 }],
        ],
        300,
        120,
      ),
    );

    expect([...png.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    expect([width, height]).toEqual([PNG_WIDTH, PNG_HEIGHT]);
    expect(ink(20, 120)).toBe(true);
    expect(ink(300, 120)).toBe(true);
    expect(ink(580, 120)).toBe(true);
    expect(ink(300, 200)).toBe(true);
    expect(ink(300, 30)).toBe(false);
    expect(ink(5, 5)).toBe(false);
    expect(png.length).toBeLessThan(1024 * 1024);
  });
});

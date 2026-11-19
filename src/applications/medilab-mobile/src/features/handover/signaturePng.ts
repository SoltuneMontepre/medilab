/** A point of a stroke, in the signature pad's own coordinates. */
export interface Point {
  x: number;
  y: number;
}

/** A line drawn without lifting the finger. */
export type Stroke = Point[];

/** A piece of a stroke, from a point to the next, named by its stroke and its point. */
export interface Segment {
  id: string;
  from: Point;
  to: Point;
}

/** The pieces of the strokes; a stroke's first piece is the dot it starts with. */
export function segments(strokes: Stroke[]): Segment[] {
  return strokes.flatMap((stroke, drawn) =>
    stroke.map((to, at) => ({ id: `${drawn}.${at}`, from: stroke[Math.max(at - 1, 0)], to })),
  );
}

// The signature's picture: black ink on white, one bit a pixel, which keeps it far under MediLab's 1 MiB.
export const PNG_WIDTH = 600;
export const PNG_HEIGHT = 240;
// The ink's half width, in the picture's pixels.
const INK_RADIUS = 2;
// The largest block a stored deflate block holds.
const STORED_BLOCK = 65535;

/** The strokes drawn on a pad of the size, as a PNG in base64. */
export function signaturePng(strokes: Stroke[], padWidth: number, padHeight: number): string {
  const scale = Math.min(PNG_WIDTH / padWidth, PNG_HEIGHT / padHeight);
  // Each row starts with its filter byte, 0 for none; every other bit is 1, white.
  const stride = Math.ceil(PNG_WIDTH / 8) + 1;
  const pixels = new Uint8Array(stride * PNG_HEIGHT).fill(0xff);
  for (let row = 0; row < PNG_HEIGHT; row += 1) {
    pixels[row * stride] = 0;
  }
  const ink = (x: number, y: number) => {
    for (let dy = -INK_RADIUS; dy <= INK_RADIUS; dy += 1) {
      for (let dx = -INK_RADIUS; dx <= INK_RADIUS; dx += 1) {
        const px = Math.round(x + dx);
        const py = Math.round(y + dy);
        if (dx * dx + dy * dy <= INK_RADIUS * INK_RADIUS && px >= 0 && py >= 0 && px < PNG_WIDTH && py < PNG_HEIGHT) {
          pixels[py * stride + 1 + (px >> 3)] &= ~(0x80 >> (px & 7));
        }
      }
    }
  };
  for (const { from, to } of segments(strokes)) {
    const steps = Math.max(1, Math.ceil(Math.hypot(to.x - from.x, to.y - from.y) * scale * 2));
    for (let step = 0; step <= steps; step += 1) {
      ink((from.x + ((to.x - from.x) * step) / steps) * scale, (from.y + ((to.y - from.y) * step) / steps) * scale);
    }
  }
  const header = new Uint8Array(13);
  const view = new DataView(header.buffer);
  view.setUint32(0, PNG_WIDTH);
  view.setUint32(4, PNG_HEIGHT);
  // Bit depth 1, greyscale, deflate, no filter method, no interlace.
  header.set([1, 0, 0, 0, 0], 8);
  const png = concat([
    Uint8Array.of(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a),
    chunk("IHDR", header),
    chunk("IDAT", zlibStored(pixels)),
    chunk("IEND", new Uint8Array(0)),
  ]);
  return base64(png);
}

function chunk(type: string, data: Uint8Array): Uint8Array {
  const typed = concat([Uint8Array.from(type, (letter) => letter.codePointAt(0) ?? 0), data]);
  const framed = new Uint8Array(typed.length + 8);
  const view = new DataView(framed.buffer);
  view.setUint32(0, data.length);
  framed.set(typed, 4);
  view.setUint32(typed.length + 4, crc32(typed));
  return framed;
}

/** The data in a zlib stream of stored deflate blocks: a signature is mostly white, and small enough uncompressed. */
function zlibStored(data: Uint8Array): Uint8Array {
  const parts: Uint8Array[] = [Uint8Array.of(0x78, 0x01)];
  for (let start = 0; start < data.length; start += STORED_BLOCK) {
    const block = data.subarray(start, start + STORED_BLOCK);
    // Each block says whether it is the last, then its length and the length's complement, low byte first.
    const last = start + STORED_BLOCK >= data.length ? 1 : 0;
    const size = block.length;
    parts.push(Uint8Array.of(last, size & 0xff, size >> 8, ~size & 0xff, (~size >> 8) & 0xff), block);
  }
  const adler = new Uint8Array(4);
  new DataView(adler.buffer).setUint32(0, adler32(data));
  parts.push(adler);
  return concat(parts);
}

function concat(parts: Uint8Array[]): Uint8Array {
  const joined = new Uint8Array(parts.reduce((size, part) => size + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    joined.set(part, offset);
    offset += part.length;
  }
  return joined;
}

const CRC_TABLE = Array.from({ length: 256 }, (_, byte) => {
  let crc = byte;
  for (let bit = 0; bit < 8; bit += 1) {
    crc = crc & 1 ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1;
  }
  return crc >>> 0;
});

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function adler32(data: Uint8Array): number {
  let a = 1;
  let b = 0;
  for (const byte of data) {
    a = (a + byte) % 65521;
    b = (b + a) % 65521;
  }
  return ((b << 16) | a) >>> 0;
}

function base64(data: Uint8Array): string {
  let binary = "";
  // Converted in slices, as a call takes a limited number of arguments.
  for (let start = 0; start < data.length; start += 0x8000) {
    binary += String.fromCodePoint(...data.subarray(start, start + 0x8000));
  }
  return btoa(binary);
}

// Generates the PNG app icons (public/icons/icon-{192,512}.png) with plain Node (zlib), no deps.
// Simplified raster of icons/icon.svg: navy tile, yellow sun, white house.
import { writeFileSync } from 'node:fs';
import { deflateSync } from 'node:zlib';

const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
const crc32 = (buf) => { let c = 0xffffffff; for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
function png(size) {
  const s = size / 512;
  const raw = Buffer.alloc((size * 4 + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0;
    for (let x = 0; x < size; x++) {
      const X = x / s, Y = y / s;
      let c = [0x1d, 0x35, 0x57, 255];
      if ((X - 360) ** 2 + (Y - 150) ** 2 < 62 ** 2) c = [0xff, 0xd4, 0x00, 255];
      const roofY = 240 - (144 - Math.abs(X - 256)) * (104 / 144);
      if (X >= 112 && X <= 400 && Y <= 400 && Y >= roofY) c = [0xf1, 0xfa, 0xee, 255];
      if (X >= 216 && X <= 296 && Y >= 290 && Y <= 400) c = [0x1d, 0x35, 0x57, 255];
      raw.set(c, y * (size * 4 + 1) + 1 + x * 4);
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4); ihdr[8] = 8; ihdr[9] = 6;
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}
for (const n of [192, 512]) writeFileSync(new URL(`../public/icons/icon-${n}.png`, import.meta.url), png(n));
console.log('icons written');

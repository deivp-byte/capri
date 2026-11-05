/** Regenerates the completely offline preview from the current PNG atlases. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const pack = path.resolve(here, '..');
const manifest = JSON.parse(await fs.readFile(path.join(pack, 'animations.json'), 'utf8'));
const images = {};
for (const [id, sheet] of Object.entries(manifest.sheets)) {
  const bytes = await fs.readFile(path.resolve(pack, sheet.file));
  images[id] = 'data:image/png;base64,' + bytes.toString('base64');
}
const safeJson = value => JSON.stringify(value).replace(/</g, '\\u003c');
const player = await fs.readFile(path.join(pack, 'runtime', 'sprite-player.js'), 'utf8');
let html = await fs.readFile(path.join(here, 'preview.template.html'), 'utf8');
html = html.replace('/*__SPRITE_PLAYER_CODE__*/', () => player.replace(/<\/script/gi, '<\\/script'));
html = html.replace('/*__MANIFEST_JSON__*/', () => safeJson(manifest));
html = html.replace('/*__IMAGE_SOURCES_JSON__*/', () => safeJson(images));
const output = path.join(here, 'preview.html');
await fs.writeFile(output, html);
console.log(JSON.stringify({ output, bytes: Buffer.byteLength(html), animations: Object.keys(manifest.animations).length, sheets: Object.keys(images).length }));

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const distDirectory = fileURLToPath(new URL("../dist/", import.meta.url));
const indexPath = resolve(distDirectory, "index.html");

if (!existsSync(indexPath)) {
  throw new Error(`Frontend build is missing ${indexPath}`);
}

const html = readFileSync(indexPath, "utf8");
const references = [
  ...html.matchAll(/(?:src|href)="(\/assets\/[^"]+\.(?:js|css))"/g),
].map((match) => match[1]);

if (!references.some((asset) => asset.endsWith(".js"))) {
  throw new Error("Frontend index.html does not reference a JavaScript bundle");
}

if (!references.some((asset) => asset.endsWith(".css"))) {
  throw new Error("Frontend index.html does not reference a CSS bundle");
}

for (const asset of references) {
  const assetPath = resolve(distDirectory, `.${asset}`);
  if (!existsSync(assetPath)) {
    throw new Error(`Frontend bundle references missing asset ${asset}`);
  }
}

console.log(`Verified frontend HTML and ${references.length} referenced assets.`);

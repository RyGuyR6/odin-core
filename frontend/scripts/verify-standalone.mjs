import { access } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const required = [
  ".next/standalone/server.js",
  ".next/standalone/.next/static",
];

for (const relativePath of required) {
  const target = path.join(root, relativePath);
  try {
    await access(target);
    console.log(`[verify] OK ${relativePath}`);
  } catch {
    console.error(`[verify] MISSING ${relativePath}`);
    process.exitCode = 1;
  }
}

if (!process.exitCode) {
  console.log("[verify] Standalone production assets are packaged correctly.");
}

import { cp, mkdir, rm, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(scriptDirectory, "..");
const nextRoot = path.join(frontendRoot, ".next");
const standaloneRoot = path.join(nextRoot, "standalone");

async function exists(target) {
  try {
    await stat(target);
    return true;
  } catch (error) {
    if (error && error.code === "ENOENT") return false;
    throw error;
  }
}

async function copyDirectory(source, destination, { required = false } = {}) {
  if (!(await exists(source))) {
    if (required) {
      throw new Error(`Required build directory is missing: ${source}`);
    }
    console.log(`[standalone] Skipping missing optional directory: ${source}`);
    return;
  }

  await rm(destination, { recursive: true, force: true });
  await mkdir(path.dirname(destination), { recursive: true });
  await cp(source, destination, { recursive: true, force: true });
  console.log(`[standalone] Copied ${source} -> ${destination}`);
}

async function main() {
  if (!(await exists(path.join(standaloneRoot, "server.js")))) {
    throw new Error(
      "Next.js standalone server was not generated. Confirm next.config.ts contains output: 'standalone'.",
    );
  }

  await copyDirectory(
    path.join(nextRoot, "static"),
    path.join(standaloneRoot, ".next", "static"),
    { required: true },
  );

  await copyDirectory(
    path.join(frontendRoot, "public"),
    path.join(standaloneRoot, "public"),
  );

  console.log("[standalone] Production bundle is ready.");
}

main().catch((error) => {
  console.error(`[standalone] ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});

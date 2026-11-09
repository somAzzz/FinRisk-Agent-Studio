import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

// This exporter only knows about the reviewed public fixture, never the upload directory.
export function annualSamplePlugin(): Plugin {
  let files: Record<string, unknown> | undefined;
  function getFiles() {
    if (!files)
      files = JSON.parse(
        execFileSync("python3", ["-m", "scripts.annual_demo_assets"], {
          cwd: fileURLToPath(new URL("..", import.meta.url)),
          encoding: "utf8",
          maxBuffer: 10 * 1024 * 1024,
        }),
      );
    return files!;
  }
  return {
    name: "archived-annual-sample",
    apply: () => process.env.VITE_STATIC_DEMO === "1",
    configureServer(server) {
      server.middlewares.use("/annual-sample", (req, res) => {
        const key = (req.url || "").slice(1);
        const data = Object.hasOwn(getFiles(), key)
          ? getFiles()[key]
          : undefined;
        res.statusCode = data ? 200 : 404;
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(data || null));
      });
    },
    generateBundle() {
      for (const [filename, value] of Object.entries(getFiles()))
        this.emitFile({
          type: "asset",
          fileName: "annual-sample/" + filename,
          source: JSON.stringify(value),
        });
    },
  };
}

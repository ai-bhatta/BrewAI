const { spawnSync } = require("node:child_process");
const path = require("node:path");

const cli = require.resolve("@playwright/test/cli");
const result = spawnSync(process.execPath, [cli, "test"], {
  cwd: path.resolve(__dirname, ".."),
  stdio: "inherit",
  env: { ...process.env, BREWAI_CAPTURE_SCREENSHOTS: "1" },
});

if (result.error) throw result.error;
process.exit(result.status ?? 1);

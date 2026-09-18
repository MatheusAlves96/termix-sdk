/** Phase 0: bootstrap — resolve the Termix release tag and obtain a working tree to mine. */

import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const REPO = "Termix-SSH/Termix";
const REPO_URL = `https://github.com/${REPO}.git`;

export interface CloneResult {
  /** Absolute path to the working tree (backend + frontend source). */
  repoPath: string;
  tag: string;
  commit: string;
  /** True when repoPath is a temp dir this process owns and should clean up. */
  isTemp: boolean;
}

async function resolveLatestTag(): Promise<string> {
  const res = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`, {
    headers: { "User-Agent": "termix-sdk-spec-gen" },
  });
  if (!res.ok) {
    throw new Error(
      `Failed to resolve latest Termix release tag: GitHub API returned ${res.status}`,
    );
  }
  const data = (await res.json()) as { tag_name?: string };
  if (!data.tag_name) {
    throw new Error("GitHub API response for latest release had no tag_name");
  }
  return data.tag_name;
}

function run(cmd: string, args: string[], cwd: string): string {
  // On Windows, npm (unlike git) is a .cmd shim: spawning it needs a shell even when given
  // its exact filename. Args here are always hardcoded literals (never interpolated from
  // untrusted input), so shell:true carries no injection risk in this specific call.
  const needsShell = process.platform === "win32" && cmd === "npm";
  return execFileSync(cmd, args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], shell: needsShell });
}

/**
 * Obtains a Termix working tree to mine.
 *
 * - `opts.repoPath`: reuse an existing checkout as-is (dev/test mode). Its current
 *   HEAD is read for `commit`/`tag` metadata; no clone or npm install happens.
 * - `opts.tag`: shallow-clone this exact tag into a temp dir.
 * - neither: resolve the latest release tag from GitHub, then shallow-clone it.
 *
 * `opts.installDeps` (default true when cloning) runs `npm ci --ignore-scripts`
 * so the ts-morph type checker can resolve express/drizzle-orm/multer/busboy types.
 */
export async function obtainTermixSource(opts: {
  repoPath?: string;
  tag?: string;
  installDeps?: boolean;
}): Promise<CloneResult> {
  if (opts.repoPath) {
    if (!existsSync(opts.repoPath)) {
      throw new Error(`--repo path does not exist: ${opts.repoPath}`);
    }
    let commit = "unknown";
    let tag = opts.tag ?? "unknown";
    try {
      commit = run("git", ["rev-parse", "HEAD"], opts.repoPath).trim();
    } catch {
      /* not a git repo; leave as unknown */
    }
    try {
      tag = run("git", ["describe", "--tags", "--exact-match"], opts.repoPath).trim();
    } catch {
      /* HEAD isn't exactly a tag; keep whatever was passed in or "unknown" */
    }
    return { repoPath: opts.repoPath, tag, commit, isTemp: false };
  }

  const tag = opts.tag ?? (await resolveLatestTag());
  const workDir = mkdtempSync(join(tmpdir(), "termix-spec-gen-"));
  const dest = join(workDir, "Termix");

  try {
    run("git", ["clone", "--depth", "1", "--branch", tag, "--quiet", REPO_URL, dest], workDir);
    const commit = run("git", ["rev-parse", "HEAD"], dest).trim();

    if (opts.installDeps !== false) {
      run("npm", ["ci", "--ignore-scripts", "--no-audit", "--no-fund"], dest);
    }

    return { repoPath: dest, tag, commit, isTemp: true };
  } catch (err) {
    // Clean up on failure too — otherwise a broken clone/npm-ci run orphans a full checkout
    // (and its node_modules) in the OS temp dir, since the caller's `clone` variable never
    // gets assigned when this function throws, so its own cleanup-on-exit never runs.
    rmSync(workDir, { recursive: true, force: true });
    throw err;
  }
}

export function cleanupClone(result: CloneResult): void {
  if (!result.isTemp) return;
  // repoPath is <workDir>/Termix; remove the parent temp dir entirely.
  const workDir = join(result.repoPath, "..");
  rmSync(workDir, { recursive: true, force: true });
}
